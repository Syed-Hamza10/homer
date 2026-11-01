"""Fictional mailbox and calendar for the demo persona. Shared by both seed targets."""

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Any

OWNER = "Dana Whitfield <dana.whitfield@example.test>"
MARKER = "homer-demo"
LABELS = ["Clients", "Invoices", "Newsletters"]

ROSA = "Rosa Lindgren <rosa.lindgren@meridian-roast.example.test>"
OWEN = "Owen Castellanos <owen.castellanos@brightline-studio.example.test>"
BRIEF = "The Brand Brief <newsletter@brandbrief.example.test>"
ACCOUNTS = "Accounts, Harbor & Pine <accounts@harborpine.example.test>"


@dataclass(frozen=True)
class Message:
    days_ago: int
    hour: int
    from_owner: bool
    body: str
    unread: bool = False


@dataclass(frozen=True)
class Thread:
    key: str
    contact: str
    subject: str
    label: str
    messages: tuple[Message, ...]


@dataclass(frozen=True)
class Event:
    day_offset: int
    start: str
    end: str
    title: str
    location: str = ""
    description: str = ""
    attendees: tuple[str, ...] = ()


THREADS = [
    Thread(
        "proposal",
        ROSA,
        "Brand refresh proposal for Meridian Roast",
        "Clients",
        (
            Message(
                6,
                10,
                True,
                "Hi Rosa,\n\nAttached is the proposal for the brand refresh: a positioning "
                "workshop, the visual identity, and packaging for the three core blends. "
                "Fee and timeline are on page 4.\n\nBest,\nDana",
            ),
            Message(
                3,
                15,
                False,
                "Hi Dana,\n\nThanks, we like the direction. Two asks: split phase 1 so the "
                "workshop can start before our board meeting, and move the packaging work to "
                "Q1. Could you send a revised version?\n\nRosa",
            ),
            Message(
                1,
                9,
                False,
                "Hi Dana,\n\nQuick nudge on the revised proposal. Our board meets on the 28th "
                "and I would like to bring it along. When can you send it?\n\nRosa",
                unread=True,
            ),
        ),
    ),
    Thread(
        "scheduling",
        OWEN,
        "45-minute call next week about the rollout",
        "Clients",
        (
            Message(
                2,
                11,
                False,
                "Hi Dana,\n\nCould we find 45 minutes next week to go through the rollout plan "
                "for the new identity? Tuesday or Thursday afternoon works best on our side."
                "\n\nOwen",
                unread=True,
            ),
            Message(
                2,
                16,
                True,
                "Hi Owen,\n\nYes. I will check my calendar and send two options tomorrow.\n\nDana",
            ),
        ),
    ),
    Thread(
        "newsletter",
        BRIEF,
        "The Brand Brief: three rebrands that worked this quarter",
        "Newsletters",
        (
            Message(
                0,
                7,
                False,
                "This week: why a regional bakery dropped its mascot, what a 40-year-old "
                "hardware chain kept, and the one slide every rebrand pitch needs.\n\n"
                "Read the full issue on our site. You receive this because you subscribed.",
                unread=True,
            ),
        ),
    ),
    Thread(
        "invoice",
        ACCOUNTS,
        "Invoice DW-2026-017 for the September workshop days",
        "Invoices",
        (
            Message(
                8,
                9,
                True,
                "Hello,\n\nPlease find invoice DW-2026-017 for the September workshop days. "
                "Payment terms are 30 days.\n\nThanks,\nDana",
            ),
            Message(
                4,
                14,
                False,
                "Hello Dana,\n\nOur system rejected the invoice because it has no purchase "
                "order number. The PO for this engagement is HP-4471. Could you reissue it "
                "with the PO on it?\n\nAccounts team",
            ),
            Message(4, 17, True, "Thanks, I will reissue it this week.\n\nDana"),
            Message(
                1,
                12,
                False,
                "Hello Dana,\n\nA gentle reminder about DW-2026-017; our payment run is on "
                "Friday.\n\nAccounts team",
                unread=True,
            ),
        ),
    ),
]

EVENTS = [
    Event(
        1,
        "09:30",
        "10:30",
        "Workshop prep for Meridian Roast",
        "Home office",
        "Finish the positioning exercises.",
        (ROSA,),
    ),
    Event(1, "14:00", "14:45", "Design review: packaging drafts", "Video call"),
    Event(2, "11:00", "12:00", "Portfolio review with a prospective client", "Cafe on Elm Street"),
    Event(3, "09:00", "11:00", "Admin block: invoices and bookkeeping"),
    Event(4, "13:00", "14:00", "Lunch with Sam, mentor", "Riverside Deli"),
    Event(6, "10:00", "11:30", "Pitch rehearsal: Harbor & Pine packaging", "Home office", "", ()),
]


def address(contact: str) -> str:
    return contact.rsplit("<", 1)[1].rstrip(">")


def message_id(thread: Thread, index: int) -> str:
    return f"<{MARKER}-{thread.key}-{index}@example.test>"


def raw_message(thread: Thread, index: int, now: datetime) -> str:
    item = thread.messages[index]
    sent_at = (now - timedelta(days=item.days_ago)).replace(
        hour=item.hour, minute=0, second=0, microsecond=0
    )
    mail = EmailMessage()
    mail["From"] = OWNER if item.from_owner else thread.contact
    mail["To"] = thread.contact if item.from_owner else OWNER
    mail["Subject"] = thread.subject if index == 0 else f"Re: {thread.subject}"
    mail["Date"] = format_datetime(sent_at)
    mail["Message-ID"] = message_id(thread, index)
    if index:
        mail["In-Reply-To"] = message_id(thread, index - 1)
        mail["References"] = " ".join(message_id(thread, i) for i in range(index))
    mail.set_content(item.body)
    return base64.urlsafe_b64encode(mail.as_bytes()).decode().rstrip("=")


def label_names(thread: Thread, item: Message) -> list[str]:
    system = ["SENT"] if item.from_owner else ["INBOX", *(["UNREAD"] if item.unread else [])]
    return [*system, thread.label, MARKER]


def event_body(event: Event, now: datetime) -> dict[str, Any]:
    day = (now + timedelta(days=event.day_offset)).replace(second=0, microsecond=0)
    description = f"{event.description}\n\n[{MARKER}]".strip()
    return {
        "summary": event.title,
        "location": event.location,
        "description": description,
        "start": {"dateTime": _at(day, event.start)},
        "end": {"dateTime": _at(day, event.end)},
        "attendees": [{"email": address(contact)} for contact in event.attendees],
    }


def is_demo_event(event: dict[str, Any]) -> bool:
    return f"[{MARKER}]" in event.get("description", "")


def _at(day: datetime, clock: str) -> str:
    hour, minute = clock.split(":")
    return day.replace(hour=int(hour), minute=int(minute)).isoformat()
