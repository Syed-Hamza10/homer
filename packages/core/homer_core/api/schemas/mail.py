from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

FolderKind = Literal["folder", "label", "category"]


def address_list(value: str) -> str:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts or any("@" not in part for part in parts):
        raise ValueError("give at least one email address, separated by commas")
    return ", ".join(parts)


class FolderOut(BaseModel):
    id: str
    name: str
    kind: FolderKind
    unread: int
    total: int


class ThreadSummaryOut(BaseModel):
    id: str
    subject: str
    sender: str = Field(validation_alias="from")
    to: str
    senders: list[str]
    snippet: str
    received_at: datetime | None
    message_count: int
    unread: bool
    starred: bool
    has_attachment: bool
    labels: list[str]


class ThreadPageOut(BaseModel):
    threads: list[ThreadSummaryOut]
    next_page_token: str | None


class AttachmentOut(BaseModel):
    filename: str
    mime_type: str
    size: int


class MessageOut(BaseModel):
    id: str
    sender: str
    to: str
    cc: str
    date: str
    received_at: datetime | None
    labels: list[str]
    unread: bool
    body_text: str
    body_html: str | None
    remote_images: int
    attachments: list[AttachmentOut]


class ThreadOut(BaseModel):
    id: str
    subject: str
    messages: list[MessageOut]


class LabelChange(BaseModel):
    add: list[str] = []
    remove: list[str] = []


class ThreadLabelsOut(BaseModel):
    id: str
    labels: list[str]


class ComposeIn(BaseModel):
    to: Annotated[str, AfterValidator(address_list)]
    subject: str
    body: str
    thread_id: str | None = None


class ComposeDraftOut(BaseModel):
    to: str
    subject: str
    body: str
    thread_id: str | None


class WriteIn(BaseModel):
    instruction: str = Field(min_length=1, max_length=500)
    thread_id: str | None = None
    to: str = ""


class WriteOut(BaseModel):
    body: str
