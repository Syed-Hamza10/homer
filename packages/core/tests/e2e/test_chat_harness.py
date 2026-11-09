from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from sqlmodel import Session, col, select

from homer_core.db.models import Message
from homer_core.db.session import make_engine

pytestmark = pytest.mark.e2e
REPLY_TIMEOUT = 120_000
LONG_PROMPT = "Write a long story of at least 600 words about a lighthouse keeper."


def ask(page: Page, text: str) -> None:
    box = page.get_by_placeholder("Message Homer")
    box.fill(text)
    box.press("Enter")


def wait_for_reply(page: Page) -> None:
    expect(page.get_by_role("button", name="Send")).to_be_visible(timeout=REPLY_TIMEOUT)


def test_reply_renders_markdown_with_copy_and_time(unlocked: Page) -> None:
    page = unlocked
    ask(page, "Show a Python hello world in a fenced code block, then one bold word.")
    expect(page.get_by_role("status")).to_be_visible()
    wait_for_reply(page)
    reply = page.get_by_test_id("message-assistant").last
    expect(reply.get_by_test_id("code-block")).to_be_visible()
    expect(reply.get_by_role("button", name="Copy code")).to_be_visible()
    expect(reply.get_by_role("button", name="Copy message")).to_be_visible()
    expect(reply.locator("time")).to_have_count(1)


def test_stop_saves_the_partial_reply(unlocked: Page, home: Path) -> None:
    page = unlocked
    ask(page, LONG_PROMPT)
    reply = page.get_by_test_id("message-assistant").last
    expect(reply).to_contain_text(" ", timeout=REPLY_TIMEOUT)
    page.get_by_role("button", name="Stop").click()
    wait_for_reply(page)
    expect(page.get_by_text("Stopped", exact=True).last).to_be_visible()
    with Session(make_engine(home)) as session:
        last = session.exec(select(Message).order_by(col(Message.id).desc())).first()
        assert last is not None and last.role == "assistant" and last.stopped


def test_regenerate_replaces_the_last_reply(unlocked: Page) -> None:
    page = unlocked
    ask(page, "Say hello in five words.")
    wait_for_reply(page)
    replies = page.get_by_test_id("message-assistant")
    count = replies.count()
    replies.last.get_by_role("button", name="Regenerate").click()
    wait_for_reply(page)
    expect(page.get_by_test_id("message-assistant")).to_have_count(count)
    expect(
        page.get_by_test_id("message-user").filter(has_text="Say hello in five words.")
    ).to_have_count(1)


def test_sidebar_renames_searches_and_deletes(unlocked: Page) -> None:
    page = unlocked
    ask(page, "Reply with the single word PONG")
    wait_for_reply(page)
    today = page.get_by_role("region", name="Today")
    row = today.get_by_role("listitem").first
    row.hover()
    row.get_by_role("button", name="Rename").click()
    title = page.get_by_role("textbox", name="Conversation title")
    title.fill("Harness check")
    title.press("Enter")
    expect(today.get_by_text("Harness check")).to_be_visible()

    page.get_by_role("button", name="Search conversations").click()
    search = page.get_by_role("searchbox", name="Search conversations")
    search.fill("harness")
    expect(page.get_by_text("Harness check")).to_be_visible()
    search.fill("no such chat title")
    expect(page.get_by_text("No matches.")).to_be_visible()
    search.fill("")

    row = page.get_by_role("listitem").filter(has_text="Harness check")
    row.hover()
    row.get_by_role("button", name="Delete").click()
    row.get_by_role("button", name="Confirm delete").click()
    expect(page.get_by_text("Harness check")).to_have_count(0)
