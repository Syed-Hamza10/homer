import html
import re
from typing import Any

from homer_mcp_search.settings import KEYED_HOSTS, LogFn
from homer_mcp_search.untrusted import wrap
from homer_net import Allowlist, AllowlistedClient

BRAVE_URL = f"https://{KEYED_HOSTS['brave']}/res/v1/web/search"
TAVILY_URL = f"https://{KEYED_HOSTS['tavily']}/search"
TIMEOUT_SECONDS = 10
MAX_RESULTS = 20
INVALID_KEY = {401, 403}
LIMITED = {429, 432, 433}
TAG = re.compile(r"<[^>]+>")


def plain(text: str) -> str:
    return " ".join(html.unescape(TAG.sub("", text)).split())


def result(title: str, url: str, snippet: str, published: str | None) -> dict[str, str]:
    found = {"title": wrap(plain(title)), "url": url, "snippet": wrap(plain(snippet))}
    if published:
        found["published"] = published
    return found


def brave_results(body: dict[str, Any]) -> list[dict[str, str]]:
    items = (body.get("web") or {}).get("results") or []
    return [
        result(r.get("title", ""), r["url"], r.get("description", ""), r.get("page_age"))
        for r in items
        if r.get("url")
    ]


def tavily_results(body: dict[str, Any]) -> list[dict[str, str]]:
    items = body.get("results") or []
    return [
        result(r.get("title", ""), r["url"], r.get("content", ""), r.get("published_date"))
        for r in items
        if r.get("url")
    ]


def failure(status: int, text: str) -> dict[str, Any]:
    """Brave reports a bad key as 422 SUBSCRIPTION_TOKEN_INVALID; Tavily as 401."""
    if status in INVALID_KEY or "TOKEN_INVALID" in text:
        return {"error": "search_invalid_key", "status": status}
    if status in LIMITED:
        return {"error": "search_limited", "status": status}
    return {"error": "search_failed", "status": status}


async def send(provider: str, log: LogFn, **request: Any) -> tuple[int, Any]:
    allowlist = Allowlist([KEYED_HOSTS[provider]])
    async with AllowlistedClient(allowlist, log, timeout=TIMEOUT_SECONDS) as c:
        response = await c.request(**request)
    if response.status_code != 200:
        return response.status_code, response.text
    return 200, response.json()


async def keyed_search(
    provider: str, query: str, max_results: int, key: str, log: LogFn
) -> dict[str, Any]:
    count = max(1, min(max_results, MAX_RESULTS))
    if provider == "brave":
        request = {
            "method": "GET",
            "url": BRAVE_URL,
            "params": {"q": query, "count": count},
            "headers": {"X-Subscription-Token": key, "Accept": "application/json"},
        }
    else:
        request = {
            "method": "POST",
            "url": TAVILY_URL,
            "json": {"query": query, "max_results": count, "search_depth": "basic"},
            "headers": {"Authorization": f"Bearer {key}"},
        }
    try:
        status, body = await send(provider, log, **request)
    except Exception as error:
        return {"error": "search_failed", "detail": type(error).__name__}
    if status != 200:
        return failure(status, body)
    parse = brave_results if provider == "brave" else tavily_results
    return {"results": parse(body)[:max_results]}
