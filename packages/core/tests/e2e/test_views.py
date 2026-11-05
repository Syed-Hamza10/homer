"""Inbox and Calendar views in the browser on the real stack (see real_stack.py)."""

import pytest
from playwright.sync_api import Page, expect

from .conftest import unlock
from .real_stack import Stack

pytestmark = pytest.mark.e2e

PROPOSAL_THREAD = "5378fcbd5bd7dbed"
KICKOFF_THREAD = "dbe626c57687283a"


def test_inbox_reads_safely_and_sends_only_after_approval(page: Page, stack: Stack) -> None:
    unlock(page, stack.url)
    page.get_by_role("link", name="Inbox").click()
    page.get_by_test_id(f"thread-{PROPOSAL_THREAD}").click()
    body = page.frame_locator("[data-testid=message-html]").first
    expect(body.get_by_text("Proposal")).to_be_visible()
    expect(body.locator("script")).to_have_count(0)
    expect(body.locator("img[src^='https://']")).to_have_count(0)
    expect(body.get_by_role("link", name="our work")).to_have_attribute("target", "_blank")
    page.get_by_role("button", name="Show images").click()
    expect(body.locator("img[src^='https://']")).to_have_count(1)

    page.get_by_test_id(f"thread-{KICKOFF_THREAD}").click()
    page.get_by_role("button", name="Reply", exact=True).click()
    composer = page.get_by_test_id("composer")
    expect(composer.get_by_label("To")).to_have_value(
        "Maya Lindqvist <maya.lindqvist@example.test>"
    )
    composer.get_by_label("Message").fill("Thursday at 14:00 works for us.")
    sent_before = stack.sent_count()
    composer.get_by_role("button", name="Send").click()
    card = page.get_by_test_id("composer-approval")
    expect(card).to_contain_text("Send email to Maya Lindqvist")
    assert stack.sent_count() == sent_before
    card.get_by_role("button", name="Send").click()
    expect(card).to_contain_text("done")
    assert stack.sent_count() == sent_before + 1


def test_inbox_keyboard_archive_and_cheat_sheet(page: Page, stack: Stack) -> None:
    unlock(page, stack.url)
    page.get_by_role("link", name="Inbox").click()
    expect(page.get_by_test_id(f"thread-{PROPOSAL_THREAD}")).to_be_visible()
    page.keyboard.press("?")
    expect(page.get_by_role("dialog", name="Inbox keyboard shortcuts")).to_be_visible()
    page.keyboard.press("Escape")
    page.get_by_test_id(f"thread-{PROPOSAL_THREAD}").click()
    page.keyboard.press("e")
    expect(page.get_by_test_id(f"thread-{PROPOSAL_THREAD}")).to_have_count(0)
    assert "INBOX" not in stack.gmail("/messages/81b178b5ebec82bd")["labelIds"]


def test_calendar_cancel_and_create_wait_for_approval(page: Page, stack: Stack) -> None:
    unlock(page, stack.url)
    page.get_by_role("link", name="Calendar").click()
    expect(page.get_by_test_id("calendar-grid")).to_be_visible()
    page.get_by_role("button", name="Week").click()
    page.get_by_test_id("event-evt_006").click()
    popover = page.get_by_test_id("event-popover")
    expect(popover).to_contain_text("tomas.keller@example.test")
    before = stack.counts()["events"]
    popover.get_by_role("button", name="Cancel event").click()
    approval = page.get_by_test_id("calendar-approval")
    expect(approval).to_contain_text("Delete 'Lunch with Tomas'")
    assert stack.counts()["events"] == before
    approval.get_by_role("button", name="Approve").click()
    expect(approval).to_contain_text("done")
    assert stack.counts()["events"] == before - 1

    page.keyboard.press("c")
    create = page.get_by_test_id("quick-create")
    create.get_by_label("Title").fill("Design review")
    create.get_by_role("button", name="Create").click()
    approval = page.get_by_test_id("calendar-approval")
    expect(approval).to_contain_text("Create event 'Design review'")
    assert stack.counts()["events"] == before - 1
