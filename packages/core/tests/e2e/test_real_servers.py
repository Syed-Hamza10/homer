"""The real stack: achilles serve, the real MCP servers, the Google simulator and the live model."""

import json
import re
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
from sqlmodel import Session

from achilles_core.db.models import FollowUp
from achilles_core.db.session import make_engine
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
ACCOUNT_EMAIL = "jordan.reyes@example.test"
AMBIGUOUS_PROMPT = "Email Sara and tell her the invoice is approved"
SARAS = {
    "Sara Whitfield": "sara.whitfield@example.test",
    "Sara Mbeki": "sara.mbeki@example.test",
}
INVOICE_MESSAGE = "aed89caf9a7af277"
PROPOSAL_MESSAGE = "81b178b5ebec82bd"
REVIEW_DECK_MESSAGE = "5cc2f1f78a46377d"
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
        return self.counts()["sent"]

    def counts(self) -> dict[str, int]:
        return httpx.get(f"{self.sim_url}/_sim/state").json()

    def gmail(self, path: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.sim_url}/gmail/v1/users/me{path}",
            headers={"Authorization": f"Bearer {KNOWN_TOKEN}"},
        )
        response.raise_for_status()
        return response.json()

    def label_names(self, message_id: str) -> set[str]:
        names = {label["id"]: label["name"] for label in self.gmail("/labels")["labels"]}
        return {names[label] for label in self.gmail(f"/messages/{message_id}")["labelIds"]}

    def brief_rows(self) -> list[tuple[str, str]]:
        with sqlite3.connect(self.home / "data" / "achilles.db") as connection:
            return connection.execute("SELECT kind, content FROM daily_briefs").fetchall()

    def make_due(self, followup_id: int) -> None:
        with Session(make_engine(self.home)) as session:
            followup = session.get(FollowUp, followup_id)
            assert followup is not None
            followup.due_at = datetime.now(UTC) - timedelta(hours=1)
            session.add(followup)
            session.commit()

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


def request_send(chat: Chat, name: str, text: str) -> Frames:
    """Asks the model to draft and send; allows one follow-up if it only drafted."""
    frames = chat({"message": REPLY_PROMPT.format(name=name, text=text)})
    assert frames[-1][0] == "done", frames
    if not of(frames, "approval_required"):
        conversation_id = frames[0][1]["conversation_id"]
        follow_up = chat({"conversation_id": conversation_id, "message": SEND_FOLLOW_UP})
        assert follow_up[-1][0] == "done", follow_up
        frames += follow_up
    assert of(frames, "approval_required"), (tool_calls(frames), answer(frames))
    return frames


def returned_draft_ids(frames: Frames) -> list[str]:
    results = [r["summary"] for r in of(frames, "tool_result") if r["name"] == "mail_draft"]
    return [json.loads(summary)["draft_id"] for summary in results]


def sent_draft_ids(frames: Frames) -> list[str]:
    return [c["args"].get("draft_id") for c in of(frames, "tool_call") if c["name"] == "mail_send"]


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
    frames = request_send(chat, "Maya", "I'll confirm by Friday")
    calls, requested = tool_calls(frames), of(frames, "approval_required")
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
    requested = of(request_send(chat, "Tomas", "the invoice is paid"), "approval_required")
    rejected = client.post(f"/api/approvals/{requested[0]['approval_id']}/reject").json()
    assert rejected["status"] == "rejected"
    assert stack.sent_count() == sent_before


def test_send_carries_the_draft_id_that_mail_draft_returned(
    stack: Stack, client: httpx.Client, chat: Chat
) -> None:
    frames = request_send(chat, "Priya", "the weekend cover is sorted")
    returned = returned_draft_ids(frames)
    assert returned and all(re.fullmatch(r"r-\d{19}", d) for d in returned), returned
    requested = of(frames, "approval_required")[0]
    pending = client.get("/api/approvals").json()
    approval = next(a for a in pending if a["id"] == requested["approval_id"])
    draft_id = approval["payload"]["draft_id"]
    assert draft_id in returned, (draft_id, returned, sent_draft_ids(frames))
    assert stack.gmail(f"/drafts/{draft_id}")["id"] == draft_id
    if any(given not in returned for given in sent_draft_ids(frames)):
        assert "draft_id_substituted" in (stack.home / "server.log").read_text()
    print("draft handoff:", {"returned": returned, "sent_with": sent_draft_ids(frames)})
    client.post(f"/api/approvals/{requested['approval_id']}/reject").raise_for_status()


def test_ambiguous_contact_becomes_a_question(
    stack: Stack, client: httpx.Client, chat: Chat
) -> None:
    sent_before = stack.sent_count()
    frames = chat({"message": AMBIGUOUS_PROMPT})
    assert frames[-1][0] == "done", frames
    said, requested = answer(frames), of(frames, "approval_required")
    print(
        "ambiguous contact:",
        {"tools": tool_calls(frames), "approvals": len(requested), "said": said},
    )
    if requested:
        preview = requested[0]["preview"]
        named = [name for name in SARAS if name in AMBIGUOUS_PROMPT]
        assert any(name in preview or SARAS[name] in preview for name in named), preview
        client.post(f"/api/approvals/{requested[0]['approval_id']}/reject").raise_for_status()
    else:
        assert "which" in said.lower() and "sara" in said.lower(), said
    assert stack.sent_count() == sent_before


def set_self_email(client: httpx.Client, address: str, enabled: bool = True) -> None:
    rules = client.get("/api/settings").json()
    body = {**rules, "email_to_self": enabled, "self_email": address}
    assert client.put("/api/settings", json=body).status_code == 200


def test_brief_emails_self_only_to_the_account_address(stack: Stack, client: httpx.Client) -> None:
    sent_before = stack.sent_count()
    set_self_email(client, ACCOUNT_EMAIL.upper())
    assert httpx.get(f"{stack.url}/api/health").json()["self_email"] == "ok"
    brief = client.post("/api/today/brief").json()
    assert "Good morning" in brief["content"]
    assert stack.sent_count() == sent_before + 1

    set_self_email(client, "someone.else@example.test")
    assert httpx.get(f"{stack.url}/api/health").json()["self_email"] == "mismatch"
    client.post("/api/today/digest").raise_for_status()
    assert stack.sent_count() == sent_before + 1
    set_self_email(client, "", enabled=False)
    assert httpx.get(f"{stack.url}/api/health").json()["self_email"] == "off"


def test_inbox_command_labels_the_simulator_mailbox(stack: Stack, chat: Chat) -> None:
    frames = chat({"message": "/inbox"})
    assert "messages in the inbox cache" in answer(frames), frames
    assert "Invoices" in stack.label_names(INVOICE_MESSAGE)
    assert "Clients" in stack.label_names(PROPOSAL_MESSAGE)
    assert "To review" in stack.label_names(REVIEW_DECK_MESSAGE)


def test_brief_command_stores_a_daily_brief(stack: Stack, chat: Chat, client: httpx.Client) -> None:
    text = answer(chat({"message": "/brief"}))
    assert text.startswith("Good morning")
    assert any(kind == "morning" and content == text for kind, content in stack.brief_rows())
    assert client.get("/api/today").json()["brief"]["content"] == text


def test_brief_shows_on_the_today_page(page: Page, stack: Stack) -> None:
    unlock(page, stack.url)
    page.get_by_role("link", name="Today").click()
    expect(page.get_by_text("Good morning")).to_be_visible()
    expect(page.get_by_test_id("health-line")).to_contain_text("No health check yet")


def test_unanswered_follow_up_drafts_and_sends_through_approval(
    page: Page, stack: Stack, client: httpx.Client, chat: Chat
) -> None:
    client.post("/api/inbox/refresh").raise_for_status()
    created = client.post(f"/api/inbox/{PROPOSAL_MESSAGE}/follow-up", json={"days": 1}).json()
    assert created["status"] == "open" and created["subject"] == "Partnership proposal"
    stack.make_due(created["id"])
    drafts_before = stack.counts()["drafts"]
    assert "End of day" in answer(chat({"message": "/digest"}))
    assert stack.counts()["drafts"] == drafts_before + 1
    shown = [f for f in client.get("/api/today").json()["follow_ups"] if f["id"] == created["id"]]
    assert shown[0]["status"] == "drafted" and shown[0]["draft_id"]
    assert shown[0]["draft_preview"].startswith("Hi Samuel Okafor,")

    sent_before = stack.sent_count()
    unlock(page, stack.url)
    page.get_by_role("link", name="Today").click()
    item = page.get_by_test_id(f"followup-{created['id']}")
    expect(item).to_contain_text('Just following up on "Partnership proposal"')
    item.get_by_role("button", name="Send").click()
    expect(item).to_contain_text("Approval #")
    pending = client.get("/api/approvals").json()
    approval = next(a for a in pending if a["payload"] == {"draft_id": shown[0]["draft_id"]})
    assert approval["action"] == "mail_send"
    assert "samuel.okafor@example.test" in approval["preview"]
    assert stack.sent_count() == sent_before

    page.get_by_role("link", name="Approvals", exact=True).click()
    card = page.get_by_test_id(f"approval-{approval['id']}")
    card.get_by_role("button", name="Approve").click()
    expect(page.get_by_test_id(f"decided-{approval['id']}")).to_contain_text("done")
    assert stack.sent_count() == sent_before + 1


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
