import json
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine

from homer_core.db.models import (
    Approval,
    CalendarEventCache,
    EmailCache,
    FollowUp,
    User,
)
from homer_core.services.day import day_card, greeting

NOW = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)


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
                created_at=NOW,
            ),
        ]
    )
    session.commit()
    return user


def test_day_card_from_cached_data() -> None:
    with make_session() as session:
        card = day_card(session, seed(session), NOW)
    assert card.greeting == "Good morning, Alex."
    assert [meeting.event_id for meeting in card.meetings] == ["past", "next"]
    assert card.next_event_id == "next"
    assert card.meetings[1].join_url == "https://meet.example.com/abc"
    assert card.meetings[1].attendees == ["elena@example.com"]
    assert [(item.message_id, item.reason) for item in card.emails] == [
        ("m1", "Priority contact"),
        ("m2", "Waiting on your reply"),
        ("m3", "Priority contact"),
    ]
    assert [item.subject for item in card.follow_ups] == ["Proposal"]
    assert [item.preview for item in card.approvals] == ["Send to Rosa"]


def test_greeting_by_local_time() -> None:
    assert greeting("Alex Morgan", NOW.replace(hour=13), "Europe/London") == "Good afternoon, Alex."
    assert greeting("Alex", NOW.replace(hour=20), "Europe/London") == "Good evening, Alex."
    assert greeting("", NOW.replace(hour=2), "Asia/Tokyo") == "Good morning."
