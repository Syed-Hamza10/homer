from datetime import datetime

from sqlmodel import Session, select

from achilles_core.db.models import Reminder, User


def create_reminder(session: Session, user_id: int, text: str, due_at: datetime) -> Reminder:
    reminder = Reminder(user_id=user_id, text=text, due_at=due_at)
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return reminder


def list_reminders(session: Session, user: User) -> list[Reminder]:
    statement = select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.due_at)
    return list(session.exec(statement))
