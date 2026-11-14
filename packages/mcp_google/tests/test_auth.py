import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from homer_mcp_google import auth
from homer_mcp_google.settings import Settings


class FakeCredentials:
    def to_json(self) -> str:
        return json.dumps({"token": "t", "refresh_token": "r"})


class FakeFlow:
    calls: list[dict[str, Any]] = []

    @classmethod
    def from_client_secrets_file(cls, path: str, scopes: list[str]) -> "FakeFlow":
        return cls()

    def run_local_server(self, port: int, **options: Any) -> FakeCredentials:
        FakeFlow.calls.append(options)
        return FakeCredentials()


def test_connect_stamps_the_consent_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from google_auth_oauthlib import flow

    monkeypatch.setattr(flow, "InstalledAppFlow", FakeFlow)
    settings = Settings(home=tmp_path, api_base="http://x", token_url="http://x/token")
    path = auth.connect(settings)
    token: dict[str, Any] = json.loads(path.read_text())
    assert token["refresh_token"] == "r"
    stamped = datetime.fromisoformat(token["connected_at"])
    assert (datetime.now(UTC) - stamped).total_seconds() < 60
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_connect_without_a_browser_prints_only_the_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from google_auth_oauthlib import flow

    monkeypatch.setattr(flow, "InstalledAppFlow", FakeFlow)
    monkeypatch.setattr(FakeFlow, "calls", [])
    settings = Settings(home=tmp_path, api_base="http://x", token_url="http://x/token")
    auth.connect(settings)
    auth.connect(settings, open_browser=False)
    assert FakeFlow.calls == [
        {},
        {"open_browser": False, "authorization_prompt_message": "{url}"},
    ]


@pytest.mark.parametrize(("argv", "open_browser"), [([], True), (["--no-browser"], False)])
def test_setup_opens_a_browser_unless_told_not_to(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, argv: list[str], open_browser: bool
) -> None:
    seen: list[bool] = []
    monkeypatch.setattr(auth.sys, "argv", ["homer-mcp-google-setup", *argv])
    monkeypatch.setattr(
        auth, "connect", lambda settings, open_browser: seen.append(open_browser) or tmp_path
    )
    auth.setup()
    assert seen == [open_browser]


def test_missing_token_needs_a_reconnect(tmp_path: Path) -> None:
    with pytest.raises(auth.ReconnectRequired):
        auth.TokenStore(tmp_path / "none.json").load()


def test_contacts_use_the_people_host_against_real_google(monkeypatch: pytest.MonkeyPatch) -> None:
    from homer_mcp_google.settings import GOOGLE_PEOPLE_API_BASE

    monkeypatch.delenv("GOOGLE_API_BASE", raising=False)
    monkeypatch.delenv("GOOGLE_PEOPLE_API_BASE", raising=False)
    assert Settings.from_env().people_api == GOOGLE_PEOPLE_API_BASE


def test_contacts_follow_a_simulator_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_BASE", "http://127.0.0.1:9999")
    monkeypatch.delenv("GOOGLE_PEOPLE_API_BASE", raising=False)
    assert Settings.from_env().people_api == "http://127.0.0.1:9999"
