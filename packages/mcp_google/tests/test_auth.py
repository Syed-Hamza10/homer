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
    @classmethod
    def from_client_secrets_file(cls, path: str, scopes: list[str]) -> "FakeFlow":
        return cls()

    def run_local_server(self, port: int) -> FakeCredentials:
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


def test_missing_token_needs_a_reconnect(tmp_path: Path) -> None:
    with pytest.raises(auth.ReconnectRequired):
        auth.TokenStore(tmp_path / "none.json").load()
