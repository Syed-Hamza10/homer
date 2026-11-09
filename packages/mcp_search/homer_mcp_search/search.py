import asyncio
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlsplit

from homer_mcp_search.settings import LogFn
from homer_mcp_search.untrusted import wrap
from homer_net import Allowlist, AllowlistedClient

SEARCH_HOST = "html.duckduckgo.com"
SEARCH_URL = f"https://{SEARCH_HOST}/html/"
ALLOWLIST = Allowlist([SEARCH_HOST])
USER_AGENT = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/128 Safari/537.36"
TIMEOUT_SECONDS = 10
RETRY_SECONDS = 2.0
CHALLENGE = re.compile(r"bots use DuckDuckGo|anomaly-modal|challenge-form", re.IGNORECASE)


def real_url(href: str) -> str:
    """Decodes DuckDuckGo's `//duckduckgo.com/l/?uddg=...` redirect links to the target URL."""
    parts = urlsplit(href)
    if parts.path == "/l/" and (parts.hostname or "").endswith("duckduckgo.com"):
        return parse_qs(parts.query).get("uddg", [href])[0]
    return href


def is_duckduckgo(url: str) -> bool:
    return (urlsplit(url).hostname or "").endswith("duckduckgo.com")


def clean(text: str) -> str:
    return " ".join(text.split())


class ResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._field: str | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._field is not None:
            self._depth += 1
            return
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "a" and "result__a" in classes:
            url = real_url(attributes.get("href") or "")
            self.results.append({"title": "", "url": url, "snippet": ""})
            self._field = "title"
        elif "result__snippet" in classes and self.results:
            self._field = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if self._field is None:
            return
        if self._depth == 0:
            self._field = None
        else:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._field is not None:
            self.results[-1][self._field] += data


def parse_results(html: str) -> list[dict[str, str]]:
    parser = ResultParser()
    parser.feed(html)
    parser.close()
    return [
        {"title": wrap(clean(r["title"])), "url": r["url"], "snippet": wrap(clean(r["snippet"]))}
        for r in parser.results
        if r["url"] and not is_duckduckgo(r["url"])
    ]


def blocked(status: int, html: str) -> bool:
    """DuckDuckGo's bot check: HTTP 202 with a 'select the ducks' page instead of results."""
    return status == 202 or bool(CHALLENGE.search(html))


async def post_query(query: str, log: LogFn) -> tuple[int, str]:
    headers = {"User-Agent": USER_AGENT}
    async with AllowlistedClient(ALLOWLIST, log, timeout=TIMEOUT_SECONDS, headers=headers) as c:
        response = await c.post(SEARCH_URL, data={"q": query, "kl": "us-en"})
    return response.status_code, response.text


async def web_search(query: str, max_results: int, log: LogFn) -> dict[str, Any]:
    """One retry after a short pause when DuckDuckGo shows its bot check, then a clear
    `search_blocked` error."""
    for attempt in range(2):
        try:
            status, html = await post_query(query, log)
        except Exception as error:
            return {"error": "search_failed", "detail": f"{type(error).__name__}: {error}"}
        if not blocked(status, html):
            break
        if attempt == 0:
            await asyncio.sleep(RETRY_SECONDS)
    else:
        return {"error": "search_blocked", "detail": "DuckDuckGo answered with its bot check"}
    if status != 200:
        return {"error": "search_failed", "status": status}
    return {"results": parse_results(html)[:max_results]}
