import re
from collections.abc import Callable

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e
REPLY_TIMEOUT = 60_000


def test_dashboard_login_and_chat(unlocked: Page, prompt: str) -> None:
    page = unlocked
    page.get_by_placeholder("Message Homer").fill(prompt)
    page.get_by_placeholder("Message Homer").press("Enter")
    reply = page.get_by_test_id("message-assistant").last
    expect(reply).to_have_text(re.compile(r"^\W*PONG\W*$"), timeout=REPLY_TIMEOUT)
    expect(page.get_by_test_id("message-assistant")).to_have_count(1)

    status = page.get_by_text("Tokens processed locally")
    expect(status).to_have_text(
        re.compile(r"Tokens processed locally: [1-9][\d,]* · Spent on inference: \$0\.00"),
        timeout=REPLY_TIMEOUT,
    )


def test_approvals_page_approves_and_shows_result(
    unlocked: Page,
    server: str,
    create_approval: Callable[[str], int],
    status_of: Callable[[int], str],
) -> None:
    approval_id = create_approval("d-ui")
    page = unlocked
    page.get_by_role("link", name="Approvals").click()
    expect(page).to_have_url(f"{server}/approvals")

    card = page.get_by_test_id(f"approval-{approval_id}")
    expect(card).to_contain_text("Send draft d-ui")
    card.get_by_role("button", name="Approve").click()

    expect(page.get_by_test_id(f"decided-{approval_id}")).to_contain_text("done")
    expect(card).not_to_be_visible()
    assert status_of(approval_id) == "done"


def test_approvals_page_rejects(
    unlocked: Page,
    server: str,
    create_approval: Callable[[str], int],
    status_of: Callable[[int], str],
) -> None:
    approval_id = create_approval("d-reject")
    page = unlocked
    page.goto(f"{server}/approvals")
    page.get_by_test_id(f"approval-{approval_id}").get_by_role("button", name="Reject").click()
    expect(page.get_by_test_id(f"decided-{approval_id}")).to_contain_text("rejected")
    assert status_of(approval_id) == "rejected"


def test_privacy_page_lists_hosts(unlocked: Page, server: str) -> None:
    page = unlocked
    page.get_by_role("link", name="Privacy").click()
    expect(page).to_have_url(f"{server}/privacy")
    expect(page.get_by_text("Tokens processed locally")).to_have_text(
        re.compile(r"Tokens processed locally: [\d,]+ · Spent on inference: \$0\.00")
    )
    expect(page.get_by_role("cell", name="127.0.0.1:11434")).to_be_visible()


def test_settings_page_saves_the_timezone(unlocked: Page, server: str) -> None:
    page = unlocked
    page.get_by_role("link", name="Settings").click()
    expect(page).to_have_url(f"{server}/settings")
    field = page.get_by_placeholder("Europe/London")
    expect(field).to_have_value(re.compile(r"\S"))
    original = field.input_value()
    field.fill("Europe/Paris")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Saved.")).to_be_visible()
    page.reload()
    field = page.get_by_placeholder("Europe/London")
    expect(field).to_have_value("Europe/Paris")
    field.fill(original)
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Saved.")).to_be_visible()
