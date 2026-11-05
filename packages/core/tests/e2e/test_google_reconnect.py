import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from homer_core.services.jobs.turn import RECONNECT

from .conftest import REQUEST_TIMEOUT, login, post_chat, require_ollama
from .real_stack import Stack, real_stack

pytestmark = pytest.mark.e2e


def revoke(home: Path) -> None:
    path = home / "credentials" / "google_token.json"
    token = json.loads(path.read_text())
    path.write_text(json.dumps({**token, "token": "stale", "refresh_token": ""}))


@pytest.fixture(scope="module")
def revoked(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    with real_stack(tmp_path_factory.mktemp("homer-revoked-home")) as running:
        revoke(running.home)
        yield running


@pytest.fixture
def client(revoked: Stack) -> Iterator[httpx.Client]:
    headers = {"Origin": revoked.url}
    with httpx.Client(base_url=revoked.url, timeout=REQUEST_TIMEOUT, headers=headers) as http:
        login(http)
        yield http


@pytest.mark.parametrize(
    "message",
    [
        "What's on my calendar tomorrow?",
        "Summarise my latest emails from Maya",
        "Email Maya that the demo is ready",
    ],
)
def test_revoked_token_asks_to_reconnect(client: httpx.Client, message: str) -> None:
    frames = post_chat(client, {"message": message})
    said = "".join(data["text"] for name, data in frames if name == "token")
    assert said == RECONNECT, frames
    assert [data for name, data in frames if name == "google_reconnect"] == [{"url": "/settings"}]


def test_status_reports_expired(client: httpx.Client) -> None:
    body = client.get("/api/google/status").json()
    assert body["state"] == "expired"
