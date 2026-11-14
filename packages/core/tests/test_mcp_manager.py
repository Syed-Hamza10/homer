from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pydantic_ai.models.test import TestModel

from homer_core.config import Settings
from homer_core.main import create_app
from homer_core.mcp import manager as manager_module
from homer_core.mcp.manager import McpManager, ServerUnavailable, server_env, stdio_toolset


def make_settings(tmp_path: Path) -> Settings:
    return Settings(homer_home=tmp_path / "home", homer_passphrase=SecretStr("p"), _env_file=None)


def test_server_env_carries_home_and_google_settings(tmp_path: Path) -> None:
    env = server_env(make_settings(tmp_path))
    assert env == {
        "HOMER_HOME": str(tmp_path / "home"),
        "GOOGLE_API_BASE": "https://www.googleapis.com",
        "GOOGLE_TOKEN_URL": "https://oauth2.googleapis.com/token",
        "WEB_SEARCH": "true",
        "SEARCH_PROVIDER": "duckduckgo",
        "SEARCH_API_PROVIDER": "brave",
        "SEARCH_API_KEY": "",
        "SEARCH_FALLBACK": "true",
    }


def test_discover_skips_missing_servers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manager_module, "find_executable", lambda name: None)
    assert McpManager.discover(make_settings(tmp_path)).toolsets == {}


async def test_start_drops_a_server_that_fails_to_launch(tmp_path: Path) -> None:
    manager = McpManager({"google": stdio_toolset("google", str(tmp_path / "missing"), {})})
    await manager.start()
    assert manager.toolsets == {}
    with pytest.raises(ServerUnavailable):
        await manager.call("google", "execute", {})
    await manager.stop()


def test_app_runs_with_no_servers(tmp_path: Path) -> None:
    app = create_app(
        make_settings(tmp_path), model=TestModel(custom_output_text="hi"), mcp=McpManager({})
    )
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert app.state.runtime.manager.toolsets == {}
