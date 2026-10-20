from sqlalchemy import delete
from sqlmodel import Session, select

from achilles_core.db.models import Setting, User
from achilles_core.services import privacy


def first_user(session: Session) -> User | None:
    return session.exec(select(User).order_by(User.id)).first()


def ensure_first_user(session: Session, name: str, timezone: str) -> User:
    user = first_user(session)
    if user is None:
        user = User(name=name, timezone=timezone)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def forget_user(session: Session, user: User) -> dict[str, int]:
    deleted = privacy.wipe(session, user)
    deleted["settings"] = session.exec(delete(Setting).where(Setting.user_id == user.id)).rowcount
    session.delete(user)
    session.commit()
    deleted["users"] = 1
    return deleted
