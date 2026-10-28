from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


def canonicalize_url(url: str, base_url: str | None = None) -> str | None:
    try:
        if base_url:
            url = str(httpx.URL(base_url).join(url)) if 'httpx' in globals() else url

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None

        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path

        # Normalize trailing slash (keep root slash, strip others if present)
        if path and path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        # Sort query parameters for consistency
        query_params = parse_qsl(parsed.query, keep_blank_values=True)
        sorted_query = sorted(query_params)
        query = urlencode(sorted_query)

        # Strip fragment
        return urlunparse((scheme, netloc, path, parsed.params, query, ""))
    except Exception:
        return None