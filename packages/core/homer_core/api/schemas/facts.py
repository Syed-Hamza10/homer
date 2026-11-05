from datetime import datetime

from pydantic import BaseModel


class FactOut(BaseModel):
    id: int
    text: str
    source: str
    created_at: datetime
