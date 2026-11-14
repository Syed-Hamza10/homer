import json
import stat
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from fastmcp.client import Client
from pydantic import SecretStr
from pydantic_ai.mcp import MCPToolset

from homer_core.config import Settings
from homer_core.mcp.manager import McpManager
from homer_core.privacy_hosts import privacy_markdown
from homer_core.services.search_settings import SearchSettings, key_hint, load_search
from homer_mcp_search import providers
from homer_mcp_search.keyed import BRAVE_URL, TAVILY_URL
from homer_mcp_search.server import mcp as search_server
from homer_mcp_search.settings import SearchConfig

KEY = "test-key-0000abcd"
BRAVE_OK = {
    "web": {"results": [{"title": "Sun", "url": "https://w.example.test/", "description": "Sunny"}]}
}


@pytest.fixture
def mcp(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> McpManager:
    monkeypatch.setenv("HOMER_HOME", str(settings.homer_home))
    monkeypatch.setenv("WEB_SEARCH", "true")
    toolset = MCPToolset(Client(search_server), id="search", tool_error_behavior="failed")
    return McpManager({"search": toolset})


def put(client: TestClient, origin: dict[str, str], **body: object) -> httpx.Response:
    defaults = {"provider": "duckduckgo", "api_provider": "brave", "fallback": True}
    return client.put("/api/settings/search", json={**defaults, **body}, headers=origin)


def test_no_key_means_duckduckgo_only(logged_in: TestClient) -> None:
    assert logged_in.get("/api/settings/search").json() == {
        "provider": "duckduckgo",
        "api_provider": "brave",
        "fallback": True,
        "key_hint": None,
        "hosts": ["html.duckduckgo.com"],
    }
    assert logged_in.get("/api/privacy/hosts").json()["search_hosts"] == ["html.duckduckgo.com"]


def test_the_key_is_saved_privately_and_only_its_last_four_are_shown(
    logged_in: TestClient, origin: dict[str, str], settings: Settings
) -> None:
    saved = put(logged_in, origin, provider="brave", api_key=f"  {KEY} ")
    assert saved.status_code == 200
    assert KEY not in saved.text
    assert saved.json()["key_hint"] == "…abcd"
    assert saved.json()["hosts"] == ["api.search.brave.com"]
    path = settings.homer_home / "credentials" / "search.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text())["api_key"] == KEY

    kept = put(logged_in, origin, provider="tavily")
    assert kept.json()["key_hint"] == "…abcd"
    assert kept.json()["hosts"] == ["api.tavily.com"]
    assert KEY not in logged_in.get("/api/settings/search").text
    assert logged_in.get("/api/privacy/hosts").json()["search_hosts"] == ["api.tavily.com"]

    cleared = put(logged_in, origin, provider="tavily", api_key="")
    assert cleared.json()["key_hint"] is None
    assert cleared.json()["hosts"] == ["html.duckduckgo.com"]


def test_an_unknown_provider_is_refused(logged_in: TestClient, origin: dict[str, str]) -> None:
    assert put(logged_in, origin, provider="bing").status_code == 422


@respx.mock
def test_the_search_test_reports_ok_and_invalid_key(
    logged_in: TestClient, origin: dict[str, str]
) -> None:
    put(logged_in, origin, provider="brave", api_key=KEY)
    respx.get(BRAVE_URL).mock(return_value=httpx.Response(200, json=BRAVE_OK))
    ok = logged_in.post("/api/settings/search/test", headers=origin)
    assert ok.json() == {"status": "ok", "provider": "brave", "results": 1}

    put(logged_in, origin, provider="tavily", api_key="wrong-key")
    respx.post(TAVILY_URL).mock(return_value=httpx.Response(401, json={"detail": "no"}))
    bad = logged_in.post("/api/settings/search/test", headers=origin)
    assert bad.json() == {"status": "invalid_key", "provider": "tavily", "results": 0}


def test_search_settings_require_login(client: TestClient, origin: dict[str, str]) -> None:
    assert client.get("/api/settings/search").status_code == 401
    assert client.post("/api/settings/search/test", headers=origin).status_code == 401


def test_env_settings_apply_without_a_saved_file(tmp_path: Path) -> None:
    settings = Settings(
        homer_home=tmp_path,
        homer_passphrase=SecretStr("p"),
        search_provider="tavily",
        search_api_key=SecretStr(KEY),
        _env_file=None,
    )
    assert load_search(settings).hosts() == ("api.tavily.com",)
    assert KEY not in repr(settings)


def test_key_hint_shows_only_the_last_four() -> None:
    assert key_hint(KEY) == "…abcd"
    assert key_hint("") is None


@pytest.mark.parametrize("provider", ["duckduckgo", "brave", "tavily"])
@pytest.mark.parametrize("api_provider", ["brave", "tavily"])
@pytest.mark.parametrize("api_key", ["", "k"])
@pytest.mark.parametrize("fallback", [True, False])
def test_core_hosts_match_the_search_server(
    provider: str, api_provider: str, api_key: str, fallback: bool
) -> None:
    core = SearchSettings.model_validate(
        {
            "provider": provider,
            "api_provider": api_provider,
            "api_key": api_key,
            "fallback": fallback,
        }
    )
    server = SearchConfig(provider, api_provider, api_key, fallback)
    assert core.hosts() == providers.hosts(server)


def test_privacy_markdown_marks_the_keyed_hosts_optional() -> None:
    text = privacy_markdown()
    for host in ("api.search.brave.com", "api.tavily.com"):
        assert f"| `{host}` |" in text
    assert text.count("only if you add a key") >= 2
