from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, SQLModel, create_engine

from homer_core.db.models import (
    CalendarEventCache,
    EmailCache,
    FollowUp,
    Reminder,
    User,
)
from homer_core.services.briefs import (
    DIGEST,
    MORNING,
    current_kind,
    digest_text,
    mail_line,
    morning_text,
    reminder_line,
    todo_lines,
)
from homer_core.services.day import EmailNeed, Snapshot

KARACHI = "Asia/Karachi"
ZONE = ZoneInfo(KARACHI)
AFTERNOON = datetime(2026, 11, 14, 16, 30, tzinfo=ZONE)
NINE = datetime(2026, 11, 14, 9, 0, tzinfo=ZONE)
HASSAN = "hassan30khawaja@example.com"


def make_session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def seed(session: Session) -> User:
    user = User(name="there", timezone=KARACHI)
    session.add(user)
    session.commit()
    session.refresh(user)
    session.add_all(
        [
            Reminder(
                user_id=user.id, text=f"{HASSAN} owns the quantization comparison", due_at=NINE
            ),
            FollowUp(
                user_id=user.id,
                thread_id="t1",
                subject="the quantization comparison",
                contact=f"Hassan Khawaja <{HASSAN}>",
                due_at=NINE + timedelta(hours=1),
            ),
            EmailCache(user_id=user.id, message_id="m1", sender=f"Hassan Khawaja <{HASSAN}>"),
        ]
    )
    session.commit()
    return user


def event(title: str, start: datetime) -> CalendarEventCache:
    return CalendarEventCache(
        user_id=1,
        event_id=title,
        title=title,
        start_at=start.astimezone(UTC),
        end_at=(start + timedelta(hours=1)).astimezone(UTC),
    )


def snap(*events: CalendarEventCache, needs: list[EmailNeed] | None = None) -> Snapshot:
    return Snapshot(events=list(events), unread=24, needs_you=needs or [], live=True, as_of=None)


def test_reminders_and_follow_ups_read_as_plain_lines() -> None:
    with make_session() as session:
        seed(session)
        lines = todo_lines(
            [session.get(Reminder, 1)],
            [session.get(FollowUp, 1)],
            ZONE,
            date(2026, 11, 14),
            {HASSAN: "Hassan"},
        )
    assert lines == [
        "09:00 Follow up with Hassan about the quantization comparison",
        "10:00 Follow up with Hassan about the quantization comparison",
    ]


@pytest.mark.parametrize(
    ("text", "line"),
    [
        (
            f"{HASSAN} owns the quantization comparison",
            "Follow up with Hassan about the quantization comparison",
        ),
        (f"remind {HASSAN} that he owes the slides", "Follow up with Hassan about the slides"),
        (f"call {HASSAN} about the invoice.", "Call Hassan about the invoice"),
        ("pay rent", "Pay rent"),
    ],
)
def test_reminder_text_reads_as_an_action(text: str, line: str) -> None:
    assert reminder_line(text, {}) == line


def test_an_overdue_item_shows_its_day() -> None:
    late = Reminder(user_id=1, text="pay rent", due_at=NINE - timedelta(days=7))
    assert todo_lines([late], [], ZONE, date(2026, 11, 14), {}) == ["Sat 7 Nov 09:00 Pay rent"]


def test_mail_line_names_people_not_addresses() -> None:
    need = EmailNeed(
        thread_id="t",
        sender=HASSAN,
        subject="Results",
        received_at=AFTERNOON,
        reason="Waiting on your reply",
    )
    assert (
        mail_line(24, [need], {})
        == "24 unread emails in your inbox, 1 needs you: Results from Hassan."
    )
    assert mail_line(0, [], {}) == "Your inbox is read."


def test_morning_brief_matches_the_hour_it_was_made_and_hides_internals() -> None:
    with make_session() as session:
        user = seed(session)
        text = morning_text(
            session, user, AFTERNOON, snap(event("Sync", NINE.replace(hour=15))), ""
        )
    assert text == (
        "Good afternoon. Today is Saturday 14 November. On your calendar: 15:00 Sync. "
        "24 unread emails in your inbox. Due today: 09:00 Follow up with Hassan about the "
        "quantization comparison; 10:00 Follow up with Hassan about the quantization comparison."
    )
    assert "@" not in text and "cache" not in text


def test_digest_lists_tomorrow_and_what_is_still_open() -> None:
    evening = AFTERNOON.replace(hour=18, minute=0)
    with make_session() as session:
        user = seed(session)
        text = digest_text(
            session, user, evening, snap(), [event("Planning", NINE + timedelta(days=1))], "Hamza"
        )
    assert text.startswith("Good evening, Hamza. Tomorrow: 09:00 Planning. 24 unread emails")
    assert "Still open: 09:00 Follow up with Hassan" in text


@pytest.mark.parametrize(
    ("hour", "minute", "kind"),
    [(7, 30, MORNING), (14, 59, MORNING), (15, 0, DIGEST), (23, 0, DIGEST), (0, 30, MORNING)],
)
def test_brief_before_three_digest_after(hour: int, minute: int, kind: str) -> None:
    moment = AFTERNOON.replace(hour=hour, minute=minute).astimezone(UTC)
    assert current_kind(moment, KARACHI) == kind
