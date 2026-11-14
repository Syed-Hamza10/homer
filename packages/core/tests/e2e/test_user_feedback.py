"""User feedback round 1 on the real stack: attendees hear about calendar changes, follow-ups work
on any thread, and Inbox and Calendar keep their place in the URL across a reload."""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from playwright.sync_api import Page, expect

from .conftest import REQUEST_TIMEOUT, login, post_chat, require_ollama, unlock
from .real_stack import TIMEZONE, Stack, real_stack

pytestmark = pytest.mark.e2e

MAYA = "maya.lindqvist@example.test"
PROPOSAL_THREAD = "5378fcbd5bd7dbed"
PROPOSAL_MESSAGE = "81b178b5ebec82bd"


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    require_ollama()
    with real_stack(tmp_path_factory.mktemp("homer-feedback-home")) as running:
        yield running


@pytest.fixture
def client(stack: Stack) -> Iterator[httpx.Client]:
    with httpx.Client(
        base_url=stack.url, timeout=REQUEST_TIMEOUT, headers={"Origin": stack.url}
    ) as http_client:
        login(http_client)
        yield http_client


def writes(stack: Stack) -> list[dict[str, Any]]:
    return httpx.get(f"{stack.sim_url}/_sim/calendar-writes").json()


def approve(stack: Stack, client: httpx.Client, approval: dict[str, Any]) -> dict[str, Any]:
    decided = client.post(f"/api/approvals/{approval['id']}/approve").json()
    assert decided["status"] == "done", decided
    return writes(stack)[-1]


def test_attendees_hear_about_create_move_and_cancel(stack: Stack, client: httpx.Client) -> None:
    body = {
        "title": "Homepage review",
        "start": "2026-11-26T10:00",
        "end": "2026-11-26T10:30",
        "attendees": [MAYA],
    }
    created = client.post("/api/calendar/events", json=body).json()
    assert "Attendees will be notified." in created["preview"]
    insert = approve(stack, client, created)
    assert insert["method"] == "insert" and insert["send_updates"] == "all"
    assert insert["body"]["start"]["timeZone"] == TIMEZONE

    event_id = insert["event_id"]
    later = {"start": "2026-11-26T15:00", "end": "2026-11-26T15:30"}
    moved = client.patch(f"/api/calendar/events/{event_id}", json=later).json()
    assert "Attendees will be notified." in moved["preview"]
    patch = approve(stack, client, moved)
    assert patch["method"] == "patch" and patch["send_updates"] == "all"
    assert patch["body"]["start"] == {
        "dateTime": "2026-11-26T15:00:00+05:00",
        "timeZone": TIMEZONE,
    }
    assert patch["body"]["end"]["timeZone"] == TIMEZONE
    assert client.get(f"/api/calendar/events/{event_id}").json()["attendees"] == [MAYA]

    cancelled = client.post(f"/api/calendar/events/{event_id}/cancel").json()
    delete = approve(stack, client, cancelled)
    assert delete["method"] == "delete" and delete["send_updates"] == "all"

    personal = {"title": "Focus time", "start": "2026-11-27T09:00", "end": "2026-11-27T10:00"}
    solo = client.post("/api/calendar/events", json=personal).json()
    assert "notified" not in solo["preview"]
    assert approve(stack, client, solo)["send_updates"] == "none"


def test_follow_up_card_send_mails_the_contact_and_leaves_the_calendar_alone(
    stack: Stack, client: httpx.Client
) -> None:
    created = client.post(f"/api/inbox/{PROPOSAL_MESSAGE}/follow-up", json={"days": 1}).json()
    stack.make_due(created["id"])
    post_chat(client, {"message": "/digest"})
    shown = [f for f in client.get("/api/today").json()["follow_ups"] if f["id"] == created["id"]]
    assert shown[0]["status"] == "drafted"
    calendar_before = len(writes(stack))
    sent_before = stack.sent_count()
    approval = client.post(f"/api/followups/{created['id']}/send").json()
    decided = client.post(f"/api/approvals/{approval['id']}/approve").json()
    assert decided["status"] == "done"
    assert stack.sent_count() == sent_before + 1
    assert len(writes(stack)) == calendar_before


def test_sent_folder_survives_a_reload_and_follow_up_works_there(page: Page, stack: Stack) -> None:
    unlock(page, stack.url)
    page.goto(f"{stack.url}/inbox?folder=sent")
    page.get_by_test_id(f"thread-{PROPOSAL_THREAD}").click()
    expect(page).to_have_url(f"{stack.url}/inbox?folder=sent&thread={PROPOSAL_THREAD}")
    page.reload()
    pane = page.get_by_test_id("reading-pane")
    expect(pane).to_contain_text("Partnership proposal")
    expect(page.get_by_test_id(f"thread-{PROPOSAL_THREAD}")).to_contain_text("To:")
    pane.get_by_role("button", name="Remind me to follow up").click()
    expect(pane).to_contain_text("Follow-up due")
    expect(pane).not_to_contain_text("Request failed")
    expect(page.get_by_test_id("updated-at").first).to_contain_text("Updated")


def test_calendar_view_and_date_survive_a_reload(page: Page, stack: Stack) -> None:
    unlock(page, stack.url)
    page.goto(f"{stack.url}/calendar?view=month&date=2026-11-16")
    page.reload()
    expect(page.get_by_role("button", name="Month")).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_test_id("calendar-title")).to_have_text("November 2026")
    page.keyboard.press("j")
    expect(page).to_have_url(f"{stack.url}/calendar?view=month&date=2026-12-01")
