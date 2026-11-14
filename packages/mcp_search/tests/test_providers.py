import json
from pathlib import Path
from typing import Any

import pytest

from homer_mcp_search import providers
from homer_mcp_search.settings import SearchConfig, search_config
from homer_net.client import no_log

OK = {"results": [{"title": "t", "url": "https://example.test/", "snippet": "s"}]}
BLOCKED = {"error": "search_blocked", "detail": "bot check"}


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    answers = {"duckduckgo": BLOCKED, "brave": OK, "tavily": OK}

    async def run(provider: str, query: str, max_results: int, key: str, log: Any) -> Any:
        seen.append(provider)
        return answers[provider]

    monkeypatch.setattr(providers, "run", run)
    return seen


async def test_a_blocked_duckduckgo_search_is_retried_once_with_the_key(calls: list[str]) -> None:
    config = SearchConfig(api_provider="tavily", api_key="k")
    assert await providers.web_search("q", 5, config, no_log) == OK
    assert calls == ["duckduckgo", "tavily"]


@pytest.mark.parametrize(
    "config",
    [SearchConfig(), SearchConfig(api_key="k", fallback=False)],
    ids=["no key", "fallback off"],
)
async def test_without_a_usable_key_a_block_is_reported(
    calls: list[str], config: SearchConfig
) -> None:
    assert await providers.web_search("q", 5, config, no_log) == BLOCKED
    assert calls == ["duckduckgo"]


async def test_a_keyed_primary_skips_duckduckgo(calls: list[str]) -> None:
    assert await providers.web_search("q", 5, SearchConfig("brave", api_key="k"), no_log) == OK
    assert calls == ["brave"]


@pytest.mark.parametrize(
    ("config", "hosts"),
    [
        (SearchConfig(), ("html.duckduckgo.com",)),
        (SearchConfig("brave"), ("html.duckduckgo.com",)),
        (SearchConfig("brave", api_key="k"), ("api.search.brave.com",)),
        (SearchConfig("tavily", api_key="k"), ("api.tavily.com",)),
        (SearchConfig(api_key="k"), ("html.duckduckgo.com", "api.search.brave.com")),
        (
            SearchConfig(api_provider="tavily", api_key="k"),
            ("html.duckduckgo.com", "api.tavily.com"),
        ),
        (SearchConfig(api_key="k", fallback=False), ("html.duckduckgo.com",)),
    ],
)
def test_hosts_follow_the_configured_provider(config: SearchConfig, hosts: tuple[str, ...]) -> None:
    assert providers.hosts(config) == hosts


@pytest.mark.parametrize(
    ("answer", "status"),
    [(OK, "ok"), (BLOCKED, "blocked"), ({"error": "search_invalid_key"}, "invalid_key")],
)
async def test_probe_reports_a_plain_status(
    monkeypatch: pytest.MonkeyPatch, answer: dict[str, Any], status: str
) -> None:
    async def run(provider: str, *args: Any) -> dict[str, Any]:
        return answer

    monkeypatch.setattr(providers, "run", run)
    found = await providers.probe(SearchConfig(api_key="k"), no_log)
    assert found["status"] == status
    assert found["provider"] == "brave"


async def test_probe_uses_duckduckgo_without_a_key(calls: list[str]) -> None:
    found = await providers.probe(SearchConfig("tavily"), no_log)
    assert found == {"status": "blocked", "provider": "duckduckgo", "results": 0}


def test_config_comes_from_env_then_from_the_saved_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOMER_HOME", str(tmp_path))
    monkeypatch.setenv("SEARCH_PROVIDER", "Brave")
    monkeypatch.setenv("SEARCH_API_KEY", "env-key")
    monkeypatch.setenv("SEARCH_FALLBACK", "false")
    assert search_config() == SearchConfig("brave", "brave", "env-key", False)
    saved = tmp_path / "credentials" / "search.json"
    saved.parent.mkdir()
    saved.write_text(
        json.dumps(
            {"provider": "duckduckgo", "api_provider": "tavily", "api_key": "k", "fallback": True}
        )
    )
    assert search_config() == SearchConfig("duckduckgo", "tavily", "k", True)
