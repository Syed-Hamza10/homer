import json
from datetime import datetime

from pydantic import BaseModel, Field

from homer_core.api.schemas.reminders import ReminderOut
from homer_core.db.models import CalendarEventCache, DailyBrief, EmailCache, FollowUp
from homer_core.services.day import DayCard
from homer_core.services.followups import draft_body
from homer_core.services.google_account import GoogleStatus
from homer_core.services.health import HealthReport
from homer_core.services.rules import ClientRules


class EmailOut(BaseModel):
    message_id: str
    thread_id: str
    sender: str
    subject: str
    snippet: str
    category: str
    labels: list[str]
    unread: bool
    priority: bool
    received_at: datetime

    @classmethod
    def from_row(cls, row: EmailCache) -> "EmailOut":
        return cls(
            message_id=row.message_id,
            thread_id=row.thread_id,
            sender=row.sender,
            subject=row.subject,
            snippet=row.snippet,
            category=row.category,
            labels=json.loads(row.labels_json),
            unread=row.unread,
            priority=row.priority,
            received_at=row.received_at,
        )


class EventOut(BaseModel):
    event_id: str
    title: str
    start: datetime
    end: datetime
    location: str
    attendees: list[str]

    @classmethod
    def from_row(cls, row: CalendarEventCache) -> "EventOut":
        return cls(
            event_id=row.event_id,
            title=row.title,
            start=row.start_at,
            end=row.end_at,
            location=row.location,
            attendees=json.loads(row.attendees_json),
        )


class FollowUpOut(BaseModel):
    id: int
    thread_id: str
    subject: str
    contact: str
    due_at: datetime
    status: str
    draft_id: str | None
    draft_preview: str | None

    @classmethod
    def from_row(cls, row: FollowUp, rules: ClientRules) -> "FollowUpOut":
        return cls(
            id=row.id,
            thread_id=row.thread_id,
            subject=row.subject,
            contact=row.contact,
            due_at=row.due_at,
            status=row.status,
            draft_id=row.draft_id,
            draft_preview=draft_body(row, rules) if row.draft_id else None,
        )


class BriefOut(BaseModel):
    kind: str
    day: str
    content: str

    @classmethod
    def from_row(cls, row: DailyBrief) -> "BriefOut":
        return cls(kind=row.kind, day=row.day, content=row.content)


class TodayOut(BaseModel):
    day: str
    brief: BriefOut | None
    digest: BriefOut | None
    events: list[EventOut]
    reminders: list[ReminderOut]
    follow_ups: list[FollowUpOut]
    unread: int
    pending_approvals: int
    health: HealthReport | None
    google: GoogleStatus
    card: DayCard


class RefreshOut(BaseModel):
    messages: int
    labeled: int
    failed: int


class TriageOut(BaseModel):
    labeled: int
    failed: int


class FollowUpRequest(BaseModel):
    days: int | None = Field(default=None, ge=1, le=30)


class DraftOut(BaseModel):
    draft_id: str | None
    to: str
    subject: str
    body: str


class SlotRequest(BaseModel):
    duration_minutes: int = Field(default=30, ge=5, le=240)
    days: int = Field(default=7, ge=1, le=31)


class SlotOut(BaseModel):
    start: str
    end: str
