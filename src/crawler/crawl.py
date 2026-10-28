import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import httpx
from selectolax.parser import HTMLParser

from crawler.fetch import fetch
from crawler.robots import RobotsCache


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    text: str
    fetched_at: float


def canonicalize_url(url: str, base_url: str | None = None) -> str | None:
    try:
        if base_url:
            parsed_base = httpx.URL(base_url)
            url = str(parsed_base.join(url))

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None

        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path

        if path and path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        query_params = parse_qsl(parsed.query, keep_blank_values=True)
        sorted_query = sorted(query_params)
        query = urlencode(sorted_query)

        return urlunparse((scheme, netloc, path, parsed.params, query, ""))
    except Exception:
        return None


class HostLimiter:
    def __init__(self, per_host_concurrency: int, min_delay: float):
        self.concurrency = per_host_concurrency
        self.min_delay = min_delay
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._last_fetched: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, host: str):
        async with self._lock:
            if host not in self._semaphores:
                self._semaphores[host] = asyncio.Semaphore(self.concurrency)
            sem = self._semaphores[host]

        await sem.acquire()

        # Enforce minimum delay per host
        async with self._lock:
            now = time.monotonic()
            last = self._last_fetched.get(host, 0.0)
            elapsed = now - last
            if elapsed < self.min_delay:
                wait_time = self.min_delay - elapsed
                self._last_fetched[host] = now + wait_time
            else:
                self._last_fetched[host] = now
                wait_time = 0.0

        if wait_time > 0:
            await asyncio.sleep(wait_time)

    def release(self, host: str):
        if host in self._semaphores:
            self._semaphores[host].release()


async def crawl(
        seeds: list[str],
        *,
        max_pages: int,
        concurrency: int,
        per_host: int = 1,
        per_host_delay: float = 0.5,
        allowed_domains: list[str] | None = None,
) -> AsyncIterator[Page]:
    client = httpx.AsyncClient(headers={"User-Agent": "MyAsyncCrawler/1.0 (+https://github.com/example/async-crawler)"})
    robots_cache = RobotsCache(client)
    frontier: asyncio.Queue[str] = asyncio.Queue()
    seen: set[str] = set()
    host_limiter = HostLimiter(per_host_concurrency=per_host, min_delay=per_host_delay)
    global_sem = asyncio.Semaphore(concurrency)

    pages_yielded = 0
    active_workers = 0
    worker_lock = asyncio.Lock()

    # Initialize frontier
    for seed in seeds:
        canonical = canonicalize_url(seed)
        if canonical and canonical not in seen:
            seen.add(canonical)
            await frontier.put(canonical)

    stop_event = asyncio.Event()

    async def worker():
        nonlocal pages_yielded
        while not stop_event.is_set():
            try:
                try:
                    url = await asyncio.wait_for(frontier.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if active_workers == 0 and frontier.empty():
                        break
                    continue

                parsed_url = urlparse(url)
                host = parsed_url.netloc

                # Check allowed domains
                if allowed_domains and not any(host == d or host.endswith("." + d) for d in allowed_domains):
                    frontier.task_done()
                    continue

                # Check robots.txt
                if not await robots_cache.allowed(url):
                    frontier.task_done()
                    continue

                async with worker_lock:
                    if pages_yielded >= max_pages:
                        frontier.task_done()
                        break
                    active_workers += 1

                try:
                    async with global_sem:
                        await host_limiter.acquire(host)
                        try:
                            result = await fetch(client, url)
                        finally:
                            host_limiter.release(host)

                    if result.status == 200 and result.body:
                        # Parse HTML content using selectolax
                        tree = HTMLParser(result.body.decode("utf-8", errors="ignore"))

                        title_node = tree.css_first("title")
                        title = title_node.text(strip=True) if title_node else ""

                        for tag in tree.css("script, style"):
                            tag.decompose()
                        body_node = tree.css_first("body")
                        text = body_node.text(separator=" ", strip=True) if body_node else tree.text(separator=" ",
                                                                                                     strip=True)

                        async with worker_lock:
                            if pages_yielded < max_pages:
                                pages_yielded += 1
                                yield Page(url=url, title=title, text=text, fetched_at=time.time())

                        # Extract links
                        for node in tree.css("a[href]"):
                            href = node.attributes.get("href")
                            if href:
                                next_url = canonicalize_url(href, base_url=url)
                                if next_url and next_url not in seen:
                                    # Domain restriction check before putting into frontier
                                    next_host = urlparse(next_url).netloc
                                    if not allowed_domains or any(
                                            next_host == d or next_host.endswith("." + d) for d in allowed_domains):
                                        seen.add(next_url)
                                        await frontier.put(next_url)

                finally:
                    async with worker_lock:
                        active_workers -= 1
                    frontier.task_done()

            except Exception:
                pass

    try:
        async with asyncio.TaskGroup() as tg:
            workers = [tg.create_task(worker()) for _ in range(concurrency)]

            # Monitor max_pages or completion
            while pages_yielded < max_pages:
                if all(w.done() for w in workers) and frontier.empty():
                    break
                await asyncio.sleep(0.05)

            stop_event.set()
    finally:
        # Drain queue and close client cleanly
        while not frontier.empty():
            try:
                frontier.get_nowait()
                frontier.task_done()
            except asyncio.QueueEmpty:
                break
        await client.aclose()