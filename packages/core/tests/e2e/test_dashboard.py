import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e
REPLY_TIMEOUT = 60_000


def test_dashboard_login_and_chat(server: str, passphrase: str, prompt: str, page: Page) -> None:
    page.goto(server)
    expect(page).to_have_url(f"{server}/login")

    page.get_by_placeholder("Passphrase").fill(passphrase)
    page.get_by_role("button", name="Unlock").click()
    expect(page).to_have_url(f"{server}/")

    page.get_by_placeholder("Message Achilles").fill(prompt)
    page.get_by_placeholder("Message Achilles").press("Enter")
    expect(page.get_by_text(re.compile(r"^\W*PONG\W*$"))).to_be_visible(timeout=REPLY_TIMEOUT)

    status = page.get_by_text("Tokens processed locally")
    expect(status).to_have_text(
        re.compile(r"Tokens processed locally: [1-9][\d,]* · Spent on inference: \$0\.00"),
        timeout=REPLY_TIMEOUT,
    )
