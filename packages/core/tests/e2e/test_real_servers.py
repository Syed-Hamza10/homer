"""Skills, pages and approvals on the real stack (see real_stack.py)."""

from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from playwright.sync_api import Page, expect

from .conftest import REQUEST_TIMEOUT, Frames, create_pending_approval, login, post_chat, unlock
from .real_stack import Stack

pytestmark = pytest.mark.e2e

ACCOUNT_EMAIL = "jordan.reyes@example.test"
AMBIGUOUS_PROMPT = "Email Sara and tell her the invoice is approved"
INVOICE_MESSAGE = "aed89caf9a7af277"
PROPOSAL_MESSAGE = "81b178b5ebec82bd"
REVIEW_DECK_MESSAGE = "5cc2f1f78a46377d"
Chat = Callable[[dict[str, Any]], Frames]


def of(frames: Frames, name: str) -> list[dict[str, Any]]:
    return [data for event, data in frames if event == name]


def answer(frames: Frames) -> str:
    return "".join(data["text"] for data in of(frames, "token"))


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


def test_ambiguous_contact_becomes_a_question(stack: Stack, chat: Chat) -> None:
    sent_before = stack.sent_count()
    frames = chat({"message": AMBIGUOUS_PROMPT})
    assert frames[-1][0] == "done", frames
    said = answer(frames)
    assert of(frames, "approval_required") == [], said
    assert said.startswith("Which Sara do you mean"), said
    assert "sara.whitfield@example.test" in said and "sara.mbeki@example.test" in said
    answered = chat({"conversation_id": frames[0][1]["conversation_id"], "message": "Sara Mbeki"})
    requested = of(answered, "approval_required")
    assert requested and requested[0]["payload"]["to"] == "sara.mbeki@example.test", answer(
        answered
    )
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
    expect(page.get_by_test_id("health-line")).to_have_count(0)


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
    approval = next(a for a in pending if a["payload"]["draft_id"] == shown[0]["draft_id"])
    assert approval["action"] == "mail_send"
    assert "samuel.okafor@example.test" in approval["preview"]
    assert stack.sent_count() == sent_before

    page.get_by_role("link", name="Approvals", exact=True).click()
    card = page.get_by_test_id(f"approval-{approval['id']}")
    card.get_by_role("button", name="Send").click()
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
    card.get_by_role("button", name="Send").click()
    expect(page.get_by_test_id(f"decided-{approval_id}")).to_contain_text("done")
    assert stack.sent_count() == sent_before + 1

    page.get_by_role("link", name="Privacy").click()
    rows = page.locator("tbody tr")
    expect(rows).to_have_count(2)
    for host in stack.hosts:
        expect(page.get_by_role("cell", name=host, exact=True)).to_be_visible()
