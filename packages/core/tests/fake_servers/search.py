"""Stand-in for homer-mcp-search: canned results; `off` in the query acts like WEB_SEARCH=false,
`blocked` like DuckDuckGo's bot check, and FAKE_SEARCH_ERROR answers every search with that
error."""

import os
from typing import Any

from fastmcp import FastMCP

server = FastMCP("homer-mcp-search")

RESULTS = [
    {"title": "Launch news", "url": "https://news.example.test/a", "snippet": "Snippet A"},
    {"title": "More news", "url": "https://news.example.test/b", "snippet": "Snippet B"},
    {"title": "Old news", "url": "https://news.example.test/c", "snippet": "Snippet C"},
]
fetched: list[str] = []
queries: list[str] = []


@server.tool
def health() -> dict[str, Any]:
    """Reports whether the server is up."""
    return {"ok": True, "version": "fake"}


@server.tool
def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Searches the web."""
    queries.append(query)
    if os.environ.get("FAKE_SEARCH_ERROR"):
        return {"error": os.environ["FAKE_SEARCH_ERROR"]}
    if "off" in query.split():
        return {"error": "web_search_off"}
    if "blocked" in query.split():
        return {"error": "search_blocked"}
    return {"results": RESULTS[:max_results]}


@server.tool
def fetch_page(url: str) -> dict[str, Any]:
    """Downloads one page."""
    fetched.append(url)
    if url.endswith("/b"):
        return {"error": "timeout"}
    return {"title": "<untrusted>Launch</untrusted>", "text": "<untrusted>Page A text</untrusted>"}


if __name__ == "__main__":
    server.run()
