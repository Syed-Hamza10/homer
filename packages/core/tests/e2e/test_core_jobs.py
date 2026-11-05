"""The four core jobs on the real stack with the live model, three runs per scenario."""

import json
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from playwright.sync_api import Page, expect

from homer_core.services.jobs.edit_email import UPDATED

from .conftest import REQUEST_TIMEOUT, Frames, login, require_ollama, unlock
from .real_stack import Stack, local_today, real_stack, tomorrow_titles

pytestmark = pytest.mark.e2e

RUNS = range(3)
TIMINGS = Path(tempfile.gettempdir()) / "homer-e2e-timings.jsonl"
DUCKDUCKGO = "https://html.duckduckgo.com/html/?q=homer"
READY = "Draft to {who} is ready. Edit it or press Send."


@dataclass(frozen=True)
class Reply:
    frames: Frames
    seconds: float
    approval_seconds: float | None

    def of(self, name: str) -> list[dict[str, Any]]:
        return [data for event, data in self.frames if event == name]

    @property
    def said(self) -> str:
        text = ""
        for event, data in self.frames:
            if event == "replace":
                text = data["text"]
            elif event == "token":
                text += data["text"]
        return text

    @property
    def tools(self) -> list[str]:
        return [call["name"] for call in self.of("tool_call")]

    @property
    def actions(self) -> list[str]:
        return [approval["action"] for approval in self.of("approval_required")]

    @property
    def conversation(self) -> int:
        return self.frames[0][1]["conversation_id"]

    def finished(self) -> dict[str, Any]:
        assert self.frames[-1][0] == "done", self.frames
        return self.frames[-1][1]


Talk = Callable[..., Reply]


def record(scenario: str, reply: Reply) -> None:
    row = {"scenario": scenario, "seconds": reply.seconds, "approval": reply.approval_seconds}
    with TIMINGS.open("a") as handle:
        handle.write(json.dumps(row) + "\n")


def timed_chat(client: httpx.Client, body: dict[str, Any]) -> Reply:
    start = time.monotonic()
    frames: Frames = []
    approval_at = None
    buffer = ""
    with client.stream("POST", "/api/chat", json=body) as response:
        assert response.status_code == 200, response.read()
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                frame, buffer = buffer.split("\n\n", 1)
                event_line, data_line = frame.split("\n")
                name = event_line.removeprefix("event: ")
                frames.append((name, json.loads(data_line.removeprefix("data: "))))
                if name == "approval_required" and approval_at is None:
                    approval_at = time.monotonic() - start
    return Reply(frames, time.monotonic() - start, approval_at)


def next_weekday(weekday: int) -> date:
    day = local_today() + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


def a_weekday_ahead(days: int) -> date:
    day = local_today() + timedelta(days=days)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


@contextmanager
def connect(stack: Stack) -> Iterator[httpx.Client]:
    with httpx.Client(
        base_url=stack.url, timeout=REQUEST_TIMEOUT, headers={"Origin": stack.url}
    ) as http_client:
        login(http_client)
        for approval in http_client.get("/api/approvals").json():
            http_client.post(f"/api/approvals/{approval['id']}/reject")
        yield http_client


@pytest.fixture
def client(stack: Stack) -> Iterator[httpx.Client]:
    with connect(stack) as http_client:
        yield http_client


@pytest.fixture
def talk(client: httpx.Client, request: pytest.FixtureRequest) -> Talk:
    def send(message: str, conversation: int | None = None) -> Reply:
        body: dict[str, Any] = {"message": message}
        if conversation is not None:
            body["conversation_id"] = conversation
        reply = timed_chat(client, body)
        record(request.node.originalname, reply)
        return reply

    return send


@pytest.mark.parametrize("run", RUNS)
def test_send_email_by_address(stack: Stack, client: httpx.Client, talk: Talk, run: int) -> None:
    sent = stack.sent_count()
    reply = talk("Email priya.natarajan@example.test and tell her the weekend cover is sorted")
    reply.finished()
    assert reply.actions == ["mail_send"], (reply.tools, reply.said)
    assert reply.said == READY.format(who="Priya Natarajan")
    approval = reply.of("approval_required")[0]
    assert approval["payload"]["to"] == "priya.natarajan@example.test"
    assert approval["payload"]["body"].strip()
    assert stack.sent_count() == sent
    done = client.post(f"/api/approvals/{approval['approval_id']}/approve").json()
    assert done["status"] == "done" and stack.sent_count() == sent + 1


@pytest.mark.parametrize("run", RUNS)
def test_send_email_by_contact_name(talk: Talk, run: int) -> None:
    reply = talk("Email Maya and tell her the kickoff notes are ready")
    reply.finished()
    assert reply.actions == ["mail_send"], (reply.tools, reply.said)
    assert reply.of("approval_required")[0]["payload"]["to"] == "maya.lindqvist@example.test"
    assert reply.said == READY.format(who="Maya Lindqvist")


@pytest.mark.parametrize("run", RUNS)
def test_send_then_edit_the_body_then_send(
    stack: Stack, client: httpx.Client, talk: Talk, run: int
) -> None:
    reply = talk("Email Tomas Keller that the invoice is paid")
    reply.finished()
    first = reply.of("approval_required")[0]
    drafts, sent = stack.counts()["drafts"], stack.sent_count()
    marker = f"Edited body, run {run}. Paid in full on Monday."
    change = {"to": first["payload"]["to"], "subject": first["payload"]["subject"], "body": marker}
    fresh = client.post(f"/api/approvals/{first['approval_id']}/edit", json=change).json()
    assert fresh["id"] != first["approval_id"] and fresh["payload"]["body"] == marker
    assert stack.counts()["drafts"] == drafts
    assert [a["id"] for a in client.get("/api/approvals").json()] == [fresh["id"]]
    done = client.post(f"/api/approvals/{fresh['id']}/approve").json()
    assert done["status"] == "done"
    assert stack.sent_count() == sent + 1
    assert any(marker[:30] in body for body in stack.sent_bodies())


@pytest.mark.parametrize("run", RUNS)
def test_compound_email_and_meeting_in_a_window(talk: Talk, run: int) -> None:
    tuesday = next_weekday(1)
    reply = talk(
        "Email Tomas Keller that the invoice is paid and schedule a 30-minute meeting with him "
        "on Tuesday between 9 and 11am"
    )
    reply.finished()
    assert reply.actions == ["mail_send", "cal_create"], (reply.tools, reply.said)
    event = reply.of("approval_required")[1]["payload"]
    assert event["start"].startswith(f"{tuesday.isoformat()}T"), event
    assert event["start"].endswith("+05:00"), event
    assert "09:00" <= event["start"][11:16] < "11:00", event
    assert event["end"][11:16] <= "11:00", event
    assert "tomas.keller@example.test" in event["attendees"]


@pytest.mark.parametrize("run", RUNS)
def test_calendar_tomorrow(talk: Talk, run: int) -> None:
    reply = talk("What's on my calendar tomorrow?")
    reply.finished()
    assert reply.tools == ["cal_list"] and reply.actions == []
    for title in tomorrow_titles():
        assert title in reply.said, reply.said
    assert "15:00-16:00 Studio visit with Elena Marchetti" in reply.said, reply.said


@pytest.mark.parametrize("run", RUNS)
def test_calendar_this_week_is_fast_and_in_local_time(talk: Talk, run: int) -> None:
    reply = talk("What's on my calendar this week?")
    reply.finished()
    assert reply.tools == ["cal_list"]
    assert "Weekly planning" in reply.said and "14:00-14:30 Weekly planning" in reply.said
    assert reply.seconds < 30, reply.seconds


@pytest.mark.parametrize("run", RUNS)
def test_add_a_meeting_at_3pm(talk: Talk, run: int) -> None:
    day = a_weekday_ahead(3)
    reply = talk(f"Add a meeting with Priya on {day:%A %-d %B} at 3pm")
    reply.finished()
    assert reply.actions == ["cal_create"], (reply.tools, reply.said)
    event = reply.of("approval_required")[0]["payload"]
    assert event["start"] == f"{day.isoformat()}T15:00:00+05:00", event
    assert event["attendees"] == ["priya.natarajan@example.test"]
    assert "timezone" not in reply.said.lower()


@pytest.mark.parametrize("run", RUNS)
def test_read_email_from_a_sender(talk: Talk, run: int) -> None:
    reply = talk("Did I get any email from Samuel? What did he ask?")
    reply.finished()
    assert "mail_search" in reply.tools and reply.actions == []
    said = reply.said.lower()
    assert "samuel" in said and ("partner" in said or "proposal" in said), reply.said


@pytest.mark.parametrize("run", RUNS)
def test_missing_contact_keeps_the_meeting(talk: Talk, run: int) -> None:
    reply = talk(
        "Email Zed Quinlan that the report is late and add a meeting with Maya Lindqvist "
        "tomorrow at 3pm"
    )
    reply.finished()
    assert reply.actions == ["cal_create"], (reply.tools, reply.said)
    assert "Zed" in reply.said and "address" in reply.said, reply.said


@pytest.mark.parametrize("run", RUNS)
def test_typed_approval_sends_without_the_model(
    stack: Stack, talk: Talk, client: httpx.Client, run: int
) -> None:
    word = ["send it", "yes", "approved"][run]
    draft = talk("Email Elena Marchetti that the deck looks good")
    draft.finished()
    approval_id = draft.of("approval_required")[0]["approval_id"]
    sent = stack.sent_count()
    reply = talk(word, draft.conversation)
    assert reply.said == f"Approval #{approval_id} (mail_send): done.", reply.said
    assert reply.tools == [] and reply.finished()["input_tokens"] == 0
    assert stack.sent_count() == sent + 1


@pytest.mark.parametrize("run", RUNS)
def test_six_turns_without_drift(talk: Talk, run: int) -> None:
    first = talk("Hello, I'm Omar")
    first.finished()
    assert first.actions == [] and "name is there" not in first.said.lower()
    conversation = first.conversation
    calendar = talk("What's on my calendar tomorrow?", conversation)
    assert "Studio visit with Elena Marchetti" in calendar.said, calendar.said
    name = talk("What's my name?", conversation)
    assert "Omar" in name.said and name.actions == [], name.said
    email = talk("Email Maya Lindqvist and tell her the kickoff notes are ready", conversation)
    assert email.actions == ["mail_send"], (email.tools, email.said)
    asked = talk("Thanks. What did Samuel Okafor ask me about?", conversation)
    assert "mail_search" in asked.tools and asked.actions == [], asked.said
    assert "proposal" in asked.said.lower() or "partner" in asked.said.lower(), asked.said
    day = talk("Which day of the week is tomorrow?", conversation)
    tomorrow = local_today() + timedelta(days=1)
    assert f"{tomorrow:%A}" in day.said and day.actions == [], day.said


@pytest.fixture(scope="module")
def web_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    try:
        httpx.get(DUCKDUCKGO, timeout=5.0).raise_for_status()
    except httpx.HTTPError as error:
        pytest.skip(f"DuckDuckGo not reachable: {error}")
    with real_stack(tmp_path_factory.mktemp("homer-web-home"), web_search=True) as running:
        yield running


@pytest.mark.parametrize("run", RUNS)
def test_latest_news_searches_and_cites(web_stack: Stack, run: int) -> None:
    with connect(web_stack) as client:
        reply = timed_chat(client, {"message": "What's the latest news about OpenAI?"})
    record("test_latest_news_searches_and_cites", reply)
    reply.finished()
    assert reply.tools[0] == "web_search", (reply.tools, reply.said)
    assert "Sources:" in reply.said and "http" in reply.said, reply.said
    assert reply.seconds < 60, reply.seconds


def test_edit_a_draft_in_the_chat_card_and_send(page: Page, stack: Stack) -> None:
    sent = stack.sent_count()
    unlock(page, stack.url)
    box = page.get_by_placeholder("Message Homer")
    box.fill("Email priya.natarajan@example.test that the launch moved to Friday")
    box.press("Enter")
    card = page.locator("[data-testid^=approval-]").last
    expect(card).to_contain_text("Send email to priya.natarajan@example.test", timeout=120_000)
    card.get_by_role("button", name="Edit").click()
    body = card.get_by_label("Body")
    body.fill("Edited in the card: the launch is on Friday.")
    card.get_by_role("button", name="Save").click()
    expect(card).to_contain_text("Edited in the card: the launch is on Friday.")
    card.get_by_role("button", name="Send").click()
    expect(card).to_contain_text("Status: done")
    assert stack.sent_count() == sent + 1
    assert any("Edited in the card" in body for body in stack.sent_bodies())


NO_DRAFT = "There's no draft waiting in this chat."


def message_part(body: str) -> str:
    return body.split("\n\n")[1] if body.count("\n\n") >= 1 else body


@pytest.mark.parametrize("run", RUNS)
def test_chat_edits_change_the_card_and_the_sent_mail(
    stack: Stack, client: httpx.Client, talk: Talk, run: int
) -> None:
    draft = talk("email priya.natarajan@example.test that the review meeting is confirmed")
    first = draft.of("approval_required")[0]
    subject = talk("change subject to Lunch is on me!", draft.conversation)
    assert subject.said in UPDATED, subject.said
    assert subject.of("approval_required")[0]["payload"]["subject"] == "Lunch is on me!"
    added = talk("add that I'm free Friday", draft.conversation)
    assert added.said in UPDATED, added.said
    fresh = added.of("approval_required")[0]
    assert "friday" in fresh["payload"]["body"].lower(), fresh["payload"]["body"]
    assert fresh["payload"]["draft_id"] == first["payload"]["draft_id"]
    shorter = talk("make it shorter", draft.conversation)
    assert shorter.said in UPDATED, shorter.said
    last = shorter.of("approval_required")[0]
    assert [a["id"] for a in client.get("/api/approvals").json()] == [last["approval_id"]]
    sent = stack.sent_count()
    done = talk("looks good, send it", draft.conversation)
    assert done.said == f"Approval #{last['approval_id']} (mail_send): done.", done.said
    assert stack.sent_count() == sent + 1


@pytest.mark.parametrize("run", RUNS)
def test_terse_requests_become_real_emails(talk: Talk, run: int) -> None:
    for message, greeting in [
        ("emial priya.natarajan@example.test that the demo is redone, thx", "Hi Priya,"),
        ("email Maya that the kickoff notes are in the shared folder", "Hi Maya,"),
        ("pls send Samuel Okafor a thanks for yesterday", "Hi Samuel,"),
    ]:
        reply = talk(message)
        assert reply.actions == ["mail_send"], (reply.tools, reply.said)
        payload = reply.of("approval_required")[0]["payload"]
        body, subject = payload["body"], payload["subject"]
        assert body.startswith(greeting), body
        assert "[" not in body and "thx" not in body.lower(), body
        assert subject.strip().lower() not in {body.lower(), message_part(body).lower()}, payload
        assert len(message_part(body).split()) >= 8, body
        assert not body.rstrip().endswith("Best,"), body


@pytest.mark.parametrize("run", RUNS)
def test_typed_approvals_stay_in_their_chat(
    stack: Stack, client: httpx.Client, talk: Talk, run: int
) -> None:
    word = ["looks good send", "perfect send it", "lgtm"][run]
    draft = talk("Email Elena Marchetti that the deck looks good")
    approval_id = draft.of("approval_required")[0]["approval_id"]
    elsewhere = talk("send it")
    assert elsewhere.said == NO_DRAFT and elsewhere.actions == [], elsewhere.said
    sent = stack.sent_count()
    reply = talk(word, draft.conversation)
    assert reply.said == f"Approval #{approval_id} (mail_send): done.", reply.said
    assert stack.sent_count() == sent + 1


@pytest.mark.parametrize("run", RUNS)
def test_send_status_comes_from_the_approvals(
    stack: Stack, client: httpx.Client, talk: Talk, run: int
) -> None:
    draft = talk("email priya.natarajan@example.test the budget is approved")
    waiting = talk("did you send it?", draft.conversation)
    assert waiting.said.startswith("Not yet. The draft to priya.natarajan@example.test"), (
        waiting.said
    )
    sent = stack.sent_count()
    now = talk("ok now send it", draft.conversation)
    assert now.said.endswith("(mail_send): done."), now.said
    assert stack.sent_count() == sent + 1
    asked = talk("did you send my email to Priya?")
    assert asked.said.startswith("Yes, sent to priya.natarajan@example.test at "), asked.said
    claim = talk("did you send it?")
    assert "sent" not in claim.said.lower() or claim.said.startswith("No."), claim.said
