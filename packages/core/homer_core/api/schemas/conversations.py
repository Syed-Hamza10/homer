from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ChoiceOption(BaseModel):
    id: str
    label: str
    detail: str


class ChoiceCard(BaseModel):
    question_id: str
    prompt: str
    options: list[ChoiceOption]
    allow_other: bool
    answered: str | None = None


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: Literal["user", "assistant"]
    content: str
    stopped: bool
    created_approval: bool
    created_at: datetime
    choice: ChoiceCard | None = None


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=200, pattern=r"\S")


class RegenerateOut(BaseModel):
    message: str
