import json
import sys
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import FastMCP
from fastmcp.client import Client
from pydantic_ai.mcp import MCPToolset

from homer_core.config import Settings
from homer_core.doctor import google_check
from homer_core.mcp.manager import McpManager
from homer_core.services import google_account
from homer_core.services.google_account import (
    consent_time,
    first_link,
    status_at,
    token_path,
)

CONSENT = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def write_token(settings: Settings, connected_at: datetime | None) -> Path:
    path = token_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = {"token": "t", "refresh_token": "r"}
    if connected_at is not None:
        token["connected_at"] = connected_at.isoformat()
    path.write_text(json.dumps(token))
    return path


@pytest.mark.parametrize(
    ("elapsed", "state", "days_left"),
    [
        (timedelta(0), "connected", 7),
        (timedelta(days=4, hours=23), "connected", 3),
        (timedelta(days=5), "expiring", 2),
        (timedelta(days=6, hours=12), "expiring", 1),
        (timedelta(days=7), "expired", 0),
        (timedelta(days=30), "expired", 0),
    ],
)
def test_day_math(elapsed: timedelta, state: str, days_left: int) -> None:
    status = status_at(CONSENT, CONSENT + elapsed)
    assert (status.state, status.days_left) == (state, days_left)


def test_no_token_is_not_connected(settings: Settings) -> None:
    assert consent_time(token_path(settings)) is None
    assert status_at(None, CONSENT).state == "not_connected"


def test_consent_time_from_the_stamp_or_the_mtime(settings: Settings) -> None:
    assert consent_time(write_token(settings, CONSENT)) == CONSENT
    path = write_token(settings, None)
    found = consent_time(path)
    assert found is not None and abs(datetime.now(UTC) - found) < timedelta(minutes=1)


def test_doctor_warns_from_day_five(settings: Settings) -> None:
    write_token(settings, CONSENT)
    fine = google_check(settings, CONSENT + timedelta(days=1))
    assert fine.ok and not fine.required
    warned = google_check(settings, CONSENT + timedelta(days=5, hours=12))
    assert not warned.ok and "disconnects in 2 days" in warned.detail
    assert "expired" in google_check(settings, CONSENT + timedelta(days=8)).detail


def test_status_not_connected(logged_in: TestClient) -> None:
    body = logged_in.get("/api/google/status").json()
    assert body["state"] == "not_connected" and body["connecting"] is False
    assert body["client_secret_found"] is False
    assert body["client_secret_path"].endswith("credentials/client_secret.json")


def test_status_connected_shows_the_account(logged_in: TestClient, settings: Settings) -> None:
    write_token(settings, datetime.now(UTC) - timedelta(days=1))
    body = logged_in.get("/api/google/status").json()
    assert body["state"] == "connected"
    assert body["email"] == "tester@example.test"
    assert body["days_left"] == 6


def test_status_expiring(logged_in: TestClient, settings: Settings) -> None:
    write_token(settings, datetime.now(UTC) - timedelta(days=5, hours=1))
    body = logged_in.get("/api/google/status").json()
    assert (body["state"], body["days_left"]) == ("expiring", 2)


def test_today_carries_the_google_status(logged_in: TestClient, settings: Settings) -> None:
    write_token(settings, datetime.now(UTC) - timedelta(days=6, hours=1))
    google = logged_in.get("/api/today").json()["google"]
    assert (google["state"], google["days_left"]) == ("expiring", 1)


def test_connect_needs_the_client_secret(logged_in: TestClient, origin: dict[str, str]) -> None:
    response = logged_in.post("/api/google/connect", headers=origin)
    assert response.status_code == 409
    assert "client_secret.json" in response.json()["detail"]


def test_connect_starts_the_setup_flow(
    logged_in: TestClient,
    settings: Settings,
    origin: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = google_account.client_secret_path(settings)
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("{}")
    started: list[str] = []
    monkeypatch.setattr(
        google_account, "find_executable", lambda name: started.append(name) or sys.executable
    )
    response = logged_in.post("/api/google/connect", headers=origin)
    assert response.status_code == 202
    assert response.json()["connecting"] is True
    assert response.json()["client_secret_found"] is True
    assert started == ["homer-mcp-google-setup"]


FAKE_SETUP = """
    import json, os, sys, time
    from datetime import UTC, datetime
    from pathlib import Path

    home = Path(os.environ["HOMER_HOME"])
    if "--no-browser" not in sys.argv or "{link}" == "":
        sys.exit(1)
    print("{link}")
    deadline = time.monotonic() + 10
    while not (home / "go").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    token = {{"token": "t", "refresh_token": "r", "connected_at": datetime.now(UTC).isoformat()}}
    (home / "credentials" / "google_token.json").write_text(json.dumps(token))
"""
LINK = (
    "https://accounts.google.com/o/oauth2/auth?client_id=test&redirect_uri=http%3A%2F%2Flocalhost"
)


def fake_setup(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link: str
) -> list[str]:
    secret = google_account.client_secret_path(settings)
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("{}")
    script = tmp_path / "fake-setup"
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent(FAKE_SETUP.format(link=link)))
    script.chmod(0o755)
    started: list[str] = []
    monkeypatch.setattr(
        google_account, "find_executable", lambda name: started.append(name) or str(script)
    )
    return started


def test_first_link_skips_other_output() -> None:
    assert first_link(["starting\n", f"{LINK}\n", "later\n"]) == LINK
    assert first_link(["no link here\n"]) is None


@pytest.mark.parametrize(
    ("consented", "before"),
    [(None, "not_connected"), (datetime.now(UTC) - timedelta(days=8), "expired")],
)
def test_connect_without_a_browser_returns_the_link_until_the_token_lands(
    app: FastAPI,
    logged_in: TestClient,
    settings: Settings,
    origin: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    consented: datetime | None,
    before: str,
) -> None:
    if consented is not None:
        write_token(settings, consented)
    started = fake_setup(settings, tmp_path, monkeypatch, LINK)
    response = logged_in.post("/api/google/connect?no_browser=1", headers=origin)
    assert response.status_code == 202
    assert started == ["homer-mcp-google-setup"]
    assert (response.json()["state"], response.json()["auth_url"]) == (before, LINK)

    waiting = logged_in.get("/api/google/status").json()
    assert (waiting["state"], waiting["connecting"], waiting["auth_url"]) == (before, True, LINK)

    (settings.homer_home / "go").touch()
    process = app.state.google_connector.process
    assert process is not None and process.wait(timeout=10) == 0

    done = logged_in.get("/api/google/status").json()
    assert (done["state"], done["connecting"], done["auth_url"]) == ("connected", False, None)
    assert done["email"] == "tester@example.test"


def test_connect_without_a_browser_fails_when_no_link_appears(
    logged_in: TestClient,
    settings: Settings,
    origin: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_setup(settings, tmp_path, monkeypatch, "")
    response = logged_in.post("/api/google/connect?no_browser=1", headers=origin)
    assert response.status_code == 409
    assert "did not start" in response.json()["detail"]
    assert logged_in.get("/api/google/status").json()["auth_url"] is None


class TestRevoked:
    @pytest.fixture
    def mcp(self) -> McpManager:
        server = FastMCP("revoked-google")

        @server.tool
        def mail_profile() -> dict[str, str]:
            """Returns the reconnect error."""
            return {"error": "google_reconnect_required"}

        toolset = MCPToolset(Client(server), id="google", tool_error_behavior="failed")
        return McpManager({"google": toolset})

    def test_status_expired_when_google_refuses(
        self, logged_in: TestClient, settings: Settings
    ) -> None:
        write_token(settings, datetime.now(UTC) - timedelta(days=1))
        body = logged_in.get("/api/google/status").json()
        assert (body["state"], body["days_left"]) == ("expired", 0)
