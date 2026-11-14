from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite hands datetimes back naive; they were stored in UTC."""
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    timezone: str
    created_at: datetime = Field(default_factory=utcnow)


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    title: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversations.id", index=True)
    role: str
    content: str
    stopped: bool = False
    created_approval: bool = False
    context_json: str | None = None
    choice_json: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Fact(SQLModel, table=True):
    __tablename__ = "facts"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    text: str
    person: str | None = None
    source: str = "user"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class OutboundLog(SQLModel, table=True):
    __tablename__ = "outbound_log"

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=utcnow)
    method: str
    host: str
    path: str
    status: int | None = None
    duration_ms: int
    error: str | None = None


class TokenCounter(SQLModel, table=True):
    __tablename__ = "token_counter"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0


class Setting(SQLModel, table=True):
    __tablename__ = "settings"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    key: str = Field(primary_key=True)
    value: str


class Reminder(SQLModel, table=True):
    __tablename__ = "reminders"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    text: str
    due_at: datetime
    status: str = "pending"
    created_at: datetime = Field(default_factory=utcnow)


class Approval(SQLModel, table=True):
    __tablename__ = "approvals"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    server: str
    action: str
    payload_json: str
    payload_hash: str
    preview: str
    status: str = Field(default="pending", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    decided_at: datetime | None = None
    result_json: str | None = None
    channel: str = "web"
    conversation_id: int | None = Field(default=None, index=True)
    message_id: int | None = Field(default=None, index=True)


class EmailCache(SQLModel, table=True):
    __tablename__ = "email_cache"
    __table_args__ = (UniqueConstraint("user_id", "message_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    message_id: str = Field(index=True)
    thread_id: str = Field(default="", index=True)
    sender: str = ""
    subject: str = ""
    snippet: str = ""
    received_at: datetime = Field(default_factory=utcnow)
    labels_json: str = "[]"
    category: str = "To review"
    unread: bool = False
    priority: bool = False
    archived: bool = False
    updated_at: datetime = Field(default_factory=utcnow)


class CalendarEventCache(SQLModel, table=True):
    __tablename__ = "calendar_cache"
    __table_args__ = (UniqueConstraint("user_id", "event_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    event_id: str = Field(index=True)
    title: str = ""
    start_at: datetime
    end_at: datetime
    location: str = ""
    description: str = ""
    attendees_json: str = "[]"
    updated_at: datetime = Field(default_factory=utcnow)


class DailyBrief(SQLModel, table=True):
    __tablename__ = "daily_briefs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    kind: str = Field(index=True)
    day: str = Field(index=True)
    content: str
    created_at: datetime = Field(default_factory=utcnow)


class FollowUp(SQLModel, table=True):
    __tablename__ = "follow_ups"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    thread_id: str = Field(index=True)
    subject: str = ""
    contact: str = ""
    due_at: datetime
    status: str = Field(default="open", index=True)
    draft_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
