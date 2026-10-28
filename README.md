🕷️ Async Web Crawler & Findex Integration
📊 M4 — Benchmark Results & Scalability Analysis
The benchmark was conducted on a fixed set of seed URLs, with a target limit of 200 pages (max_pages=200)
across varying global concurrency levels, while maintaining stable per-host constraints (per_host=2, min_delay=0.5s).

| Concurrency | Pages  | Wall Time (s) | Pages/s | Errors | Peak RSS |
|:-----------:|:------:|:-------------:|:-------:|:------:|:--------:|
|   **1**     |  200   |     48.4s     |  4.13   |   0    | 34.2 MB  |
|    **5**    |  200   |     12.1s     |  16.53  |   0    | 38.6 MB  |
|   **20**    |  200   |     3.6s      |  55.55  |   0    | 45.1 MB  |

Architectural Insights
1. Why Async Concurrency Beats Thread/Process Approaches for I/O Workloads?
For network scanning workloads where over 99% of execution time is spent waiting on I/O (TCP handshakes, TLS termination, and HTTP responses),
cooperative multitasking via asyncio drastically outperforms OS threads or processes:
1. Lightweight Context Switching: OS threads allocate a fixed stack (typically 1–8 MB) and impose heavy scheduler overhead. 
asyncio coroutines consume only dozens of bytes and switch in user-space without expensive kernel transitions.
2. Bypassing the GIL: Because the tasks are purely I/O-bound, the absence of GIL contention combined with an event loop allows managing thousands of 
sockets concurrently within a single thread with minimal memory overhead.