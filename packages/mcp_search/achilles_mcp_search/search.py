import time
from collections.abc import Callable
from typing import Any

from ddgs import DDGS
from ddgs.exceptions import DDGSException

from achilles_mcp_search.settings import LogFn
from achilles_mcp_search.untrusted import wrap
from achilles_net import OutboundCall

BACKEND = "duckduckgo"
TIMEOUT_SECONDS = 10
ENDPOINTS = {
    "text": ("POST", "html.duckduckgo.com", "/html/"),
    "news": ("GET", "duckduckgo.com", "/news.js"),
}

Search = Callable[..., list[dict[str, Any]]]


def to_result(row: dict[str, Any]) -> dict[str, str]:
    result = {
        "title": wrap(row.get("title", "")),
        "url": row.get("href") or row.get("url", ""),
        "snippet": wrap(row.get("body", "")),
    }
    if "date" in row:
        result["date"] = row["date"]
    if "source" in row:
        result["source"] = wrap(row["source"])
    return result


class Searcher:
    def __init__(self, log: LogFn) -> None:
        self._ddgs = DDGS(timeout=TIMEOUT_SECONDS)
        self._log = log

    def text(self, query: str, max_results: int) -> dict[str, Any]:
        return self._run("text", self._ddgs.text, query, max_results)

    def news(self, query: str, max_results: int) -> dict[str, Any]:
        return self._run("news", self._ddgs.news, query, max_results)

    def _run(self, category: str, search: Search, query: str, max_results: int) -> dict[str, Any]:
        """Runs one search through the pinned DuckDuckGo engine and writes one outbound_log row."""
        started_at = time.perf_counter()
        status: int | None = None
        try:
            rows = search(query, max_results=max_results, backend=BACKEND)
            status = 200
            return {"results": [to_result(row) for row in rows]}
        except DDGSException as error:
            return {"error": "search_failed", "detail": str(error)}
        finally:
            method, host, path = ENDPOINTS[category]
            duration_ms = round((time.perf_counter() - started_at) * 1000)
            self._log(OutboundCall(method, host, path, status, duration_ms))
