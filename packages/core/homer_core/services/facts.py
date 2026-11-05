from sqlmodel import Session, col, select

from homer_core.db.models import Fact, User
from homer_core.services.errors import NotFound

PROMPT_FACTS = 20


def add_fact(session: Session, user_id: int, text: str) -> Fact:
    fact = Fact(user_id=user_id, text=text.strip())
    session.add(fact)
    session.commit()
    session.refresh(fact)
    return fact


def list_facts(session: Session, user: User, limit: int | None = None) -> list[Fact]:
    """Newest first."""
    statement = (
        select(Fact).where(Fact.user_id == user.id).order_by(col(Fact.id).desc()).limit(limit)
    )
    return list(session.exec(statement))


def prompt_facts(session: Session, user: User) -> list[str]:
    """The latest facts, oldest first, for the prompts."""
    return [fact.text for fact in reversed(list_facts(session, user, PROMPT_FACTS))]


def delete_fact(session: Session, user: User, fact_id: int) -> None:
    fact = session.get(Fact, fact_id)
    if fact is None or fact.user_id != user.id:
        raise NotFound(f"fact {fact_id} not found")
    session.delete(fact)
    session.commit()


def forget(session: Session, user: User, about: str | None) -> Fact | None:
    """Deletes the newest fact, or the newest one mentioning `about`; returns it."""
    words = (about or "").lower().split()
    for fact in list_facts(session, user):
        if all(word in fact.text.lower() for word in words):
            session.delete(fact)
            session.commit()
            return fact
    return None
