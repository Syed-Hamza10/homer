from datetime import datetime

from pydantic import BaseModel


class ReminderOut(BaseModel):
    id: int
    text: str
    due_at: datetime
    status: str
    created_at: datetime
