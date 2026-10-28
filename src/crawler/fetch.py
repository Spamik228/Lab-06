import asyncio
import random
from dataclasses import dataclass, field
import time
import httpx


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    body: bytes
    elapsed: float
    error: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


async def fetch(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float = 10.0,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> FetchResult:
    attempt = 0
    start_total = time.perf_counter()

    while True:
        attempt += 1
        start_time = time.perf_counter()
        try:
            async with asyncio.timeout(timeout):
                response = await client.get(url, follow_redirects=True)
                elapsed = time.perf_counter() - start_time

                # Retry on 429 or 5xx
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt <= max_retries:
                        delay = _calculate_backoff(response, attempt, base_delay)
                        await asyncio.sleep(delay)
                        continue

                return FetchResult(
                    url=str(response.url),
                    status=response.status_code,
                    body=response.content,
                    elapsed=elapsed,
                    headers=dict(response.headers),
                )

        except (asyncio.TimeoutError, httpx.TimeoutException, httpx.TransportError) as exc:
            elapsed = time.perf_counter() - start_time
            if attempt <= max_retries:
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
                continue
            return FetchResult(
                url=url,
                status=0,
                body=b"",
                elapsed=elapsed,
                error=str(exc) or type(exc).__name__,
            )


def _calculate_backoff(response: httpx.Response, attempt: int, base_delay: float) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass  # Fallback to exponential backoff if parsing fails

    # Exponential backoff with random jitter (0 to 0.5s)
    return base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)