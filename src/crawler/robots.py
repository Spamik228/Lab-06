from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx

USER_AGENT = "MyAsyncCrawler/1.0 (+https://github.com/example/async-crawler)"


class RobotsCache:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._cache: dict[str, RobotFileParser] = {}

    async def _get_parser(self, parsed_url) -> RobotFileParser:
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
        if origin in self._cache:
            return self._cache[origin]

        parser = RobotFileParser()
        robots_url = f"{origin}/robots.txt"
        parser.set_url(robots_url)

        try:
            response = await self._client.get(robots_url, follow_redirects=True)
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            elif response.status_code >= 400:
                # If robots.txt is missing/forbidden (4xx), assume allowed
                parser.allow_all = True
        except Exception:
            # On network error, default to allowed or disallowed depending on policy (here: allowed)
            parser.allow_all = True

        self._cache[origin] = parser
        return parser

    async def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        parser = await self._get_parser(parsed)

        if getattr(parser, "allow_all", False):
            return True

        return parser.can_fetch(USER_AGENT, url)