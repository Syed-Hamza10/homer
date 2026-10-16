from sqlmodel import Session, select

from achilles_core.db.models import User


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
