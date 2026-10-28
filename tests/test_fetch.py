import asyncio
import httpx
import pytest
from crawler.fetch import fetch


@pytest.mark.asyncio
async def test_fetch_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"Hello World", headers={"Content-Type": "text/plain"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await fetch(client, "http://example.com/page")

    assert result.status == 200
    assert result.body == b"Hello World"
    assert result.error is None
    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_retry_on_500():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(500, content=b"Error")
        return httpx.Response(200, content=b"Success")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await fetch(client, "http://example.com/retry", base_delay=0.01)

    assert attempts == 3
    assert result.status == 200
    assert result.body == b"Success"
    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_retry_after_header():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0.05"})
        return httpx.Response(200, content=b"Rate limit passed")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await fetch(client, "http://example.com/rate-limited", base_delay=1.0)

    assert attempts == 2
    assert result.status == 200
    await client.aclose()