import argparse
import asyncio
import json
import logging
from pathlib import Path
import time
from rich.live import Live
from rich.table import Table

from crawler.crawl import crawl


def setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("crawler_logger")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def generate_display(stats: dict) -> Table:
    table = Table(title="[bold cyan]Async Crawler Live Status[/bold cyan]", show_header=True,
                  header_style="bold magenta")
    table.add_column("Metric", style="dim", width=25)
    table.add_column("Value", justify="right", style="bold green")

    elapsed = max(time.time() - stats["start_time"], 0.001)
    pages_per_sec = stats["fetched"] / elapsed

    table.add_row("Pages Fetched", str(stats["fetched"]))
    table.add_row("Throughput", f"{pages_per_sec:.2f} pages/s")
    table.add_row("In-Flight / Active", str(stats["active"]))
    table.add_row("Errors", str(stats["errors"]), style="bold red" if stats["errors"] > 0 else "green")
    table.add_row("Queue Depth", str(stats["queue_depth"]))
    table.add_row("Elapsed Time", f"{elapsed:.1f}s")
    return table


async def async_main(args):
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    log_path = Path("crawl.log")
    logger = setup_logger(log_path)

    stats = {
        "fetched": 0,
        "active": 0,
        "errors": 0,
        "queue_depth": 0,
        "start_time": time.time(),
    }

    seeds = [args.seed_url]

    # Live display setup
    live = Live(generate_display(stats), refresh_per_second=4)
    live.start()

    try:
        with open(out_path, "w", encoding="utf-8") as f_out:
            # We wrap the crawl generator to update stats and write streaming JSON lines
            async for page in crawl(
                    seeds,
                    max_pages=args.max_pages,
                    concurrency=args.concurrency,
                    per_host=args.per_host,
            ):
                stats["fetched"] += 1

                # Stream write JSON line immediately
                record = {
                    "url": page.url,
                    "title": page.title,
                    "text": page.text,
                    "fetched_at": page.fetched_at,
                }
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                f_out.flush()  # Ensure it hits disk immediately

                logger.info(f"FETCHED: {page.url} | Title: {page.title[:50]}")
                live.update(generate_display(stats))
    except Exception as exc:
        logger.error(f"Crawl aborted with error: {exc}")
        raise
    finally:
        live.stop()
        print(f"\n[+] Crawling completed. Saved {stats['fetched']} pages to {out_path}")
        print(f"[+] Detailed log recorded in {log_path}")


def main():
    parser = argparse.ArgumentParser(description="Findex Async Web Crawler CLI")
    parser.add_argument("seed_url", type=str, help="Starting URL for the crawler")
    parser.add_argument("--max-pages", type=int, default=500, help="Maximum pages to crawl")
    parser.add_argument("--concurrency", type=int, default=10, help="Global concurrency limit")
    parser.add_argument("--per-host", type=int, default=2, help="Per-host concurrency limit")
    parser.add_argument("--out", type=str, default="data/crawl.jsonl", help="Output JSONL path")

    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()