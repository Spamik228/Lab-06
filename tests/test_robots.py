import httpx
import pytest
from crawler.robots import RobotsCache


@pytest.mark.asyncio
async def test_robots_parser_allowed():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            content = b"User-agent: *\nDisallow: /private/\n"
            return httpx.Response(200, content=content)
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    cache = RobotsCache(client)

    assert await cache.allowed("http://example.com/public/page") is True
    assert await cache.allowed("http://example.com/private/secret") is False
    await client.aclose()