import time

from homer_mcp_search.throttle import RateLimiter, TtlCache


async def test_rate_limiter_spaces_same_key() -> None:
    gate = RateLimiter(0.2)
    started = time.perf_counter()
    await gate.wait("a")
    await gate.wait("a")
    await gate.wait("a")
    assert time.perf_counter() - started >= 0.4


async def test_rate_limiter_keys_are_independent() -> None:
    gate = RateLimiter(0.5)
    started = time.perf_counter()
    await gate.wait("a")
    await gate.wait("b")
    assert time.perf_counter() - started < 0.2


def test_cache_returns_same_object_until_expiry() -> None:
    cache = TtlCache(0.2)
    key = TtlCache.key("web_search", {"query": "q", "max_results": 5})
    value = {"results": []}
    cache.put(key, value)
    assert cache.get(key) is value
    assert cache.get(TtlCache.key("web_search", {"max_results": 5, "query": "q"})) is value
    time.sleep(0.25)
    assert cache.get(key) is None
