import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlmodel import Session, SQLModel, create_engine

from homer_core.db.models import (
    Approval,
    CalendarEventCache,
    EmailCache,
    FollowUp,
    User,
)
from homer_core.mcp.manager import PROFILE_TOOL, McpManager, ServerUnavailable
from homer_core.services.day import (
    PROFILES,
    day_card,
    greeting,
    greeting_name,
    snapshot,
)
from homer_core.services.names import call_name, humanise, person
from homer_core.services.rules import ClientRules

NOW = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)
UPDATED = NOW - timedelta(minutes=20)


def make_session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def email(message_id: str, thread_id: str, **fields: object) -> EmailCache:
    return EmailCache(
        user_id=1,
        message_id=message_id,
        thread_id=thread_id,
        sender=f"Sender {message_id} <{message_id}@example.com>",
        subject=f"Subject {message_id}",
        received_at=NOW - timedelta(minutes=int(message_id[1:])),
        updated_at=UPDATED,
        **fields,
    )


def seed(session: Session) -> User:
    user = User(name="Alex Morgan", timezone="Europe/London")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.add_all(
        [
            CalendarEventCache(
                user_id=1,
                event_id="past",
                title="Standup",
                start_at=NOW - timedelta(hours=1),
                end_at=NOW - timedelta(minutes=45),
                updated_at=UPDATED,
            ),
            CalendarEventCache(
                user_id=1,
                event_id="next",
                title="Call with Elena",
                start_at=NOW + timedelta(minutes=25),
                end_at=NOW + timedelta(minutes=55),
                location="https://meet.example.com/abc",
                attendees_json=json.dumps(["elena@example.com"]),
            ),
            CalendarEventCache(
                user_id=1,
                event_id="tomorrow",
                title="Tomorrow",
                start_at=NOW + timedelta(days=1),
                end_at=NOW + timedelta(days=1, hours=1),
            ),
            email("m1", "t1", unread=True, priority=True),
            email("m2", "t2", unread=True),
            email("m3", "t3", unread=True, category="Clients"),
            email("m4", "t4", unread=False, priority=True),
            email("m5", "t2", labels_json=json.dumps(["SENT"])),
            email("m6", "t6", unread=True, priority=True),
            email("m7", "t7", unread=True, priority=True),
            FollowUp(user_id=1, thread_id="t9", subject="Proposal", due_at=NOW),
            Approval(
                user_id=1,
                server="google",
                action="mail_send",
                payload_json="{}",
                payload_hash="x",
                preview="Send to Rosa",
            ),
        ]
    )
    session.commit()
    return user


class Stub:
    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers

    async def call(self, server: str, tool: str, args: dict[str, Any]) -> Any:
        if tool not in self.answers:
            raise ServerUnavailable("google is down")
        return self.answers[tool]


DOWN = cast(McpManager, Stub({}))


@pytest.fixture(autouse=True)
def forget_profiles() -> None:
    PROFILES.clear()


async def test_card_falls_back_to_the_cache_and_says_when() -> None:
    with make_session() as session:
        user = seed(session)
        snap = await snapshot(session, user, DOWN, ClientRules(), NOW)
        card = day_card(session, user, snap, "Alex", NOW)
    assert card.greeting == "Good morning, Alex."
    assert card.live is False and card.as_of == UPDATED
    assert [meeting.event_id for meeting in card.meetings] == ["past", "next"]
    assert card.next_event_id == "next"
    assert card.meetings[1].join_url == "https://meet.example.com/abc"
    assert card.meetings[1].attendees == ["elena@example.com"]
    assert [(item.thread_id, item.reason) for item in card.emails] == [
        ("t1", "Priority contact"),
        ("t2", "Waiting on your reply"),
        ("t3", "Priority contact"),
    ]
    assert card.needs_you == 5 and card.unread == 5
    assert [item.subject for item in card.follow_ups] == ["Proposal"]
    assert [item.preview for item in card.approvals] == ["Send to Rosa"]


async def test_card_reads_today_live_and_replaces_the_cached_day() -> None:
    google = Stub(
        {
            "cal_list": {
                "events": [
                    {
                        "id": "fresh",
                        "title": "Made a minute ago",
                        "start": "2026-11-06T09:00:00Z",
                        "end": "2026-11-06T09:30:00Z",
                    }
                ]
            },
            "mail_labels": {"labels": [{"id": "INBOX", "unread": 24, "total": 31}]},
            PROFILE_TOOL: {"email": "me@example.com", "name": "Alex Morgan"},
            "mail_list_threads": {
                "threads": [
                    {"id": "a", "from": "Ana <ana@example.com>", "subject": "Hi", "label_ids": []},
                    {
                        "id": "b",
                        "from": "Bo <bo@example.com>",
                        "subject": "Re: plan",
                        "label_ids": ["INBOX", "SENT", "UNREAD"],
                        "internal_date": "1762419600000",
                    },
                    {
                        "id": "c",
                        "from": "Alex <ME@example.com>",
                        "subject": "Re: client contract",
                        "label_ids": ["INBOX", "SENT", "UNREAD"],
                    },
                ]
            },
        }
    )
    with make_session() as session:
        user = seed(session)
        snap = await snapshot(session, user, cast(McpManager, google), ClientRules(), NOW)
        card = day_card(session, user, snap, "", NOW)
    assert card.live is True and card.as_of is None
    assert [meeting.event_id for meeting in card.meetings] == ["fresh"]
    assert card.unread == 24 and card.needs_you == 1
    assert card.emails[0].thread_id == "b" and card.emails[0].reason == "Waiting on your reply"
    assert card.greeting == "Good morning."


def test_greeting_by_local_time() -> None:
    assert greeting("Alex", NOW.replace(hour=13), "Europe/London") == "Good afternoon, Alex."
    assert greeting("Alex", NOW.replace(hour=20), "Europe/London") == "Good evening, Alex."
    assert greeting("", NOW.replace(hour=2), "Asia/Tokyo") == "Good morning."
    assert greeting("", NOW.replace(hour=11, minute=30), "Asia/Karachi") == "Good afternoon."


@pytest.mark.parametrize(
    ("display", "expected"),
    [
        ("Alex Morgan", "Alex"),
        ("BSDSF21A019-Syed Hamza Shah", "Hamza"),
        ("BSDSF21A019 - Hamza Shah", "Hamza"),
        ("Dr. Elena Marchetti", "Elena"),
        ("Mr Omar", "Omar"),
        ("Syed", "Syed"),
        ("JORDAN REYES", "Jordan"),
        ("ali@example.com", ""),
        ("", ""),
    ],
)
def test_call_name(display: str, expected: str) -> None:
    assert call_name(display) == expected


async def test_greeting_name_prefers_settings_then_the_gmail_profile() -> None:
    profile = cast(McpManager, Stub({PROFILE_TOOL: {"name": "BSDSF21A019-Syed Hamza Shah"}}))
    assert await greeting_name(User(id=7, name="Alex Morgan", timezone="UTC"), profile) == "Alex"
    assert await greeting_name(User(id=7, name="there", timezone="UTC"), profile) == "Hamza"
    PROFILES.clear()
    assert await greeting_name(User(id=7, name="there", timezone="UTC"), DOWN) == ""
    assert 7 not in PROFILES


def test_addresses_read_as_names() -> None:
    known = {"hassan.k@example.com": "Hassan"}
    assert humanise("Ask hassan.k@example.com", known) == "Ask Hassan"
    assert humanise("hassan30khawaja@example.com owns it", {}) == "Hassan owns it"
    assert person("Elena M <elena@example.com>", {}) == "Elena"
    assert person("hassan.k@example.com", known) == "Hassan"
