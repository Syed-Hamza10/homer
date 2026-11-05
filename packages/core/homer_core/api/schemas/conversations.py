from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: Literal["user", "assistant"]
    content: str
    stopped: bool
    created_approval: bool
    created_at: datetime


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=200, pattern=r"\S")


class RegenerateOut(BaseModel):
    message: str
