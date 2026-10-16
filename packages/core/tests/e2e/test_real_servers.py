"""The real stack: achilles serve, the real MCP servers, the Google simulator and the live model."""

import json
import sqlite3
import subprocess
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
from playwright.sync_api import Page, expect

from achilles_mcp_google.messages import build_raw
from achilles_sim.state import DEFAULT_SEED, KNOWN_TOKEN

from .conftest import (
    OLLAMA_URL,
    REQUEST_TIMEOUT,
    STARTUP_TIMEOUT,
    VENV_BIN,
    Frames,
    create_pending_approval,
    free_port,
    login,
    post_chat,
    process_env,
    require_ollama,
    running_server,
    unlock,
)

pytestmark = pytest.mark.e2e

TOMORROW_EVENT = {
    "id": "evt_e2e",
    "start": "10:00",
    "end": "11:00",
    "summary": "Studio visit with Elena Marchetti",
    "location": "Studio",
    "description": "",
    "attendees": ["elena.marchetti@example.test"],
}
CALENDAR_PROMPT = "What is on my calendar tomorrow?"
REPLY_PROMPT = (
    "Draft a reply to the latest email from {name} saying {text}, and send it. "
    "Use mail_search to find the email, mail_draft to write the reply and mail_send to send it."
)
SEND_FOLLOW_UP = "Send that draft now with mail_send."
Chat = Callable[[dict[str, Any]], Frames]


@dataclass(frozen=True)
class Stack:
    home: Path
    url: str
    sim_url: str

    @property
    def hosts(self) -> set[str]:
        return {urlsplit(OLLAMA_URL).netloc, urlsplit(self.sim_url).netloc}

    def sent_count(self) -> int:
        return httpx.get(f"{self.sim_url}/_sim/state").json()["sent"]

    def logged_hosts(self) -> set[str]:
        with sqlite3.connect(self.home / "data" / "achilles.db") as connection:
            rows = connection.execute("SELECT DISTINCT host FROM outbound_log").fetchall()
        return {host for (host,) in rows}

    def create_draft(self, to: str, subject: str, body: str) -> str:
        response = httpx.post(
            f"{self.sim_url}/gmail/v1/users/me/drafts",
            json={"message": {"raw": build_raw(to, subject, body, None)}},
            headers={"Authorization": f"Bearer {KNOWN_TOKEN}"},
        )
        response.raise_for_status()
        return response.json()["id"]


def tomorrow_offset() -> int:
    """Days from this week's Monday to tomorrow: the simulator's `weekday` for tomorrow."""
    now = datetime.now(UTC)
    return ((now + timedelta(days=1)).date() - (now - timedelta(days=now.weekday())).date()).days


def seeded_events() -> list[dict[str, Any]]:
    seed = json.loads(DEFAULT_SEED.read_text())
    return [*seed["events"], {**TOMORROW_EVENT, "weekday": tomorrow_offset()}]


def tomorrow_titles() -> list[str]:
    return [e["summary"] for e in seeded_events() if e["weekday"] == tomorrow_offset()]


def write_seed(home: Path) -> Path:
    seed = {**json.loads(DEFAULT_SEED.read_text()), "events": seeded_events()}
    path = home / "seed.json"
    path.write_text(json.dumps(seed))
    return path


def write_google_token(home: Path) -> None:
    path = home / "credentials" / "google_token.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    token = {
        "token": KNOWN_TOKEN,
        "refresh_token": "sim-refresh-token",
        "client_id": "sim-client-id",
        "client_secret": "sim-client-secret",
        "scopes": [],
    }
    path.write_text(json.dumps(token))


def wait_for_simulator(process: subprocess.Popen[bytes], url: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"simulator exited with {process.returncode}")
        try:
            httpx.get(f"{url}/_sim/state", timeout=1.0).raise_for_status()
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"simulator not up after {STARTUP_TIMEOUT}s")


def running_simulator(seed: Path) -> tuple[subprocess.Popen[bytes], str]:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    command = [str(VENV_BIN / "achilles-sim"), "--port", str(port), "--seed", str(seed)]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_for_simulator(process, url)
    return process, url


def of(frames: Frames, name: str) -> list[dict[str, Any]]:
    return [data for event, data in frames if event == name]


def tool_calls(frames: Frames) -> list[str]:
    return [call["name"] for call in of(frames, "tool_call")]


def answer(frames: Frames) -> str:
    return "".join(data["text"] for data in of(frames, "token"))


def request_send(chat: Chat, name: str, text: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Asks the model to draft and send; allows one follow-up if it only drafted."""
    frames = chat({"message": REPLY_PROMPT.format(name=name, text=text)})
    assert frames[-1][0] == "done", frames
    calls, requested = tool_calls(frames), of(frames, "approval_required")
    if not requested:
        conversation_id = frames[0][1]["conversation_id"]
        frames = chat({"conversation_id": conversation_id, "message": SEND_FOLLOW_UP})
        assert frames[-1][0] == "done", frames
        calls += tool_calls(frames)
        requested = of(frames, "approval_required")
    assert requested, (calls, answer(frames))
    return calls, requested


@pytest.fixture(scope="session")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    home = tmp_path_factory.mktemp("achilles-real-home")
    write_google_token(home)
    simulator, sim_url = running_simulator(write_seed(home))
    env = process_env(
        home,
        free_port(),
        GOOGLE_API_BASE=sim_url,
        GOOGLE_TOKEN_URL=f"{sim_url}/token",
        WEB_SEARCH="false",
    )
    try:
        with running_server(home, env) as url:
            yield Stack(home, url, sim_url)
    finally:
        simulator.terminate()
        simulator.wait(timeout=10)


@pytest.fixture
def client(stack: Stack) -> Iterator[httpx.Client]:
    with httpx.Client(
        base_url=stack.url, timeout=REQUEST_TIMEOUT, headers={"Origin": stack.url}
    ) as http_client:
        login(http_client)
        yield http_client


@pytest.fixture
def chat(client: httpx.Client) -> Chat:
    return lambda body: post_chat(client, body)


def test_servers_healthy(stack: Stack) -> None:
    health = httpx.get(f"{stack.url}/api/health").json()
    assert health["ollama"] == "ok"
    assert health["servers"] == {"google": "ok", "search": "ok", "system": "ok"}


def test_calendar_question(chat: Chat) -> None:
    frames = chat({"message": CALENDAR_PROMPT})
    assert frames[-1][0] == "done", frames
    calls = tool_calls(frames)
    assert "cal_list" in calls, (calls, answer(frames))
    said = answer(frames).lower()
    assert any(title.lower() in said for title in tomorrow_titles()), (calls, said)


def test_draft_reply_needs_approval(stack: Stack, client: httpx.Client, chat: Chat) -> None:
    sent_before = stack.sent_count()
    calls, requested = request_send(chat, "Maya", "I'll confirm by Friday")
    assert "mail_draft" in calls, calls
    assert "mail_search" in calls or "mail_thread" in calls, calls
    assert requested[0]["action"] == "mail_send"
    assert "maya.lindqvist@example.test" in requested[0]["preview"]
    assert stack.sent_count() == sent_before

    approved = client.post(f"/api/approvals/{requested[0]['approval_id']}/approve").json()
    assert approved["status"] == "done", approved
    assert approved["result"]["sent"] is True
    assert stack.sent_count() == sent_before + 1
    assert stack.logged_hosts() == stack.hosts


def test_reject_sends_nothing(stack: Stack, client: httpx.Client, chat: Chat) -> None:
    sent_before = stack.sent_count()
    _, requested = request_send(chat, "Tomas", "the invoice is paid")
    rejected = client.post(f"/api/approvals/{requested[0]['approval_id']}/reject").json()
    assert rejected["status"] == "rejected"
    assert stack.sent_count() == sent_before


def test_approvals_page_in_browser(page: Page, stack: Stack) -> None:
    draft_id = stack.create_draft("priya.natarajan@example.test", "Re: Weekend support", "On it.")
    approval_id = create_pending_approval(stack.home, draft_id)
    sent_before = stack.sent_count()
    unlock(page, stack.url)

    page.get_by_role("link", name="Approvals").click()
    card = page.get_by_test_id(f"approval-{approval_id}")
    expect(card).to_contain_text(f"Send draft {draft_id}")
    card.get_by_role("button", name="Approve").click()
    expect(page.get_by_test_id(f"decided-{approval_id}")).to_contain_text("done")
    assert stack.sent_count() == sent_before + 1

    page.get_by_role("link", name="Privacy").click()
    rows = page.locator("tbody tr")
    expect(rows).to_have_count(2)
    for host in stack.hosts:
        expect(page.get_by_role("cell", name=host, exact=True)).to_be_visible()
