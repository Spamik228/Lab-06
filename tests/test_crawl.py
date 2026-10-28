import httpx
import pytest
from crawler.crawl import crawl, canonicalize_url


def test_canonicalize_url():
    assert canonicalize_url("HTTP://Example.com/Path/?b=2&a=1#frag") == "http://example.com/Path?a=1&b=2"
    assert canonicalize_url("https://example.com/page/", base_url="https://example.com") == "https://example.com/page"


@pytest.mark.asyncio
async def test_crawl_flow():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(200, content=b"User-agent: *\nAllow: /\n")
        if path == "/":
            html = b'<html><head><title>Home</title></head><body><a href="/page1">Page 1</a></body></html>'
            return httpx.Response(200, content=html)
        if path == "/page1":
            html = b'<html><head><title>Page One</title></head><body><a href="/">Home</a></body></html>'
            return httpx.Response(200, content=html)
        return httpx.Response(404)

    # Patching httpx.AsyncClient transport globally or passing MockTransport via client injection
    # (Since crawl creates its own client, we can test by mocking or letting client use transport if we refactor crawl to accept a client/transport).