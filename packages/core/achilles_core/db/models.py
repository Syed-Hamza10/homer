from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


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
    created_at: datetime = Field(default_factory=utcnow)


class OutboundLog(SQLModel, table=True):
    __tablename__ = "outbound_log"

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=utcnow)
    method: str
    host: str
    path: str
    status: int | None = None
    duration_ms: int


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
