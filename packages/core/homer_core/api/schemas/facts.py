from datetime import datetime

from pydantic import BaseModel


class FactOut(BaseModel):
    id: int
    text: str
    person: str | None = None
    source: str
    created_at: datetime
    updated_at: datetime
