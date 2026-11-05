from datetime import datetime, timedelta
from pathlib import Path

TEMPLATE = (Path(__file__).parent / "prompts" / "system.md").read_text()
PLACEHOLDER_NAMES = frozenset({"", "there"})


def known_name(name: str) -> str | None:
    """The user's real name, or None while it is still the install-time placeholder."""
    return None if name.strip().lower() in PLACEHOLDER_NAMES else name.strip()


def describe(day: datetime) -> str:
    return day.strftime("%A %Y-%m-%d")


def render_prompt(user_name: str, timezone: str, now: datetime) -> str:
    name = known_name(user_name)
    return TEMPLATE.format(
        who=f" The user's name is {name}." if name else "",
        timezone=timezone,
        now=now.strftime("%A %d %B %Y, %H:%M"),
        today=describe(now),
        tomorrow=describe(now + timedelta(days=1)),
    )
