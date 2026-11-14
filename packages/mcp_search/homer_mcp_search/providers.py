from typing import Any

from homer_mcp_search import search
from homer_mcp_search.keyed import keyed_search
from homer_mcp_search.settings import DUCKDUCKGO, KEYED_HOSTS, LogFn, SearchConfig

PROBE_QUERY = "weather forecast"
PROBE_STATUS = {
    "search_blocked": "blocked",
    "search_invalid_key": "invalid_key",
    "search_limited": "limited",
}


def hosts(config: SearchConfig) -> tuple[str, ...]:
    found = [search.SEARCH_HOST if config.primary == DUCKDUCKGO else KEYED_HOSTS[config.primary]]
    if config.backup:
        found.append(KEYED_HOSTS[config.backup])
    return tuple(found)


async def run(provider: str, query: str, max_results: int, key: str, log: LogFn) -> dict[str, Any]:
    if provider == DUCKDUCKGO:
        return await search.web_search(query, max_results, log)
    return await keyed_search(provider, query, max_results, key, log)


async def web_search(
    query: str, max_results: int, config: SearchConfig, log: LogFn
) -> dict[str, Any]:
    """Searches with the primary service; when DuckDuckGo is blocked and a key is set,
    asks the keyed service once."""
    found = await run(config.primary, query, max_results, config.api_key, log)
    if found.get("error") == "search_blocked" and config.backup:
        return await run(config.backup, query, max_results, config.api_key, log)
    return found


async def probe(config: SearchConfig, log: LogFn) -> dict[str, Any]:
    """Runs one fixed query against the keyed service when a key is set, else DuckDuckGo."""
    provider = config.key_provider if config.api_key else DUCKDUCKGO
    found = await run(provider, PROBE_QUERY, 3, config.api_key, log)
    error = found.get("error")
    status = "ok" if error is None else PROBE_STATUS.get(str(error), "failed")
    return {"status": status, "provider": provider, "results": len(found.get("results", []))}
