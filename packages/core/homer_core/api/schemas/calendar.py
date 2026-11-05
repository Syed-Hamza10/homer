from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, model_validator

from homer_core.services.approval_edits import Address


def wall_time(value: str) -> str:
    datetime.fromisoformat(value)
    return value


WallTime = Annotated[str, AfterValidator(wall_time)]


class PersonOut(BaseModel):
    email: str
    name: str
    response: str
    organizer: bool


class EventDetailOut(BaseModel):
    id: str
    title: str
    start: str
    end: str
    all_day: bool
    location: str
    description: str
    attendees: list[str]
    people: list[PersonOut]
    organizer: str
    video_link: str


class EventRangeOut(BaseModel):
    events: list[EventDetailOut]
    source: str


class EventCreate(BaseModel):
    title: str = Field(min_length=1)
    start: WallTime
    end: WallTime
    attendees: list[Address] = []
    description: str = ""
    location: str = ""

    @model_validator(mode="after")
    def check_order(self) -> "EventCreate":
        if datetime.fromisoformat(self.end) <= datetime.fromisoformat(self.start):
            raise ValueError("end must be after start")
        return self


class EventChange(BaseModel):
    title: str | None = None
    start: WallTime | None = None
    end: WallTime | None = None
    attendees: list[Address] | None = None
    description: str | None = None
    location: str | None = None
