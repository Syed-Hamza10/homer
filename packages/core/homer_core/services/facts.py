import re
from difflib import SequenceMatcher

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


STOP_WORDS = frozenset(
    {"that", "this", "the", "a", "an", "thing", "things", "stuff", "about", "please", "pls"}
    | {"forget", "remember", "fact", "info", "information", "bit", "one", "it", "what", "you"}
    | {"know", "said", "told", "i", "me", "my", "your", "of", "on", "re", "and", "to", "is"}
)
CLOSE_ENOUGH = 0.8
PREFIX = 4


def keywords(text: str | None) -> list[str]:
    found = re.findall(r"[\w-]+", (text or "").lower())
    return [word.removesuffix("'s") for word in found if word not in STOP_WORDS]


def word_score(keyword: str, words: list[str]) -> float:
    best = 0.0
    for word in words:
        if word == keyword:
            return 1.0
        short, long_ = sorted((word, keyword), key=len)
        if len(short) >= PREFIX and long_.startswith(short):
            best = max(best, 0.9)
        elif SequenceMatcher(None, word, keyword).ratio() >= CLOSE_ENOUGH:
            best = max(best, 0.8)
    return best


def score(fact: Fact, wanted: list[str]) -> float:
    words = re.findall(r"[\w-]+", fact.text.lower().replace("'s", ""))
    return sum(word_score(keyword, words) for keyword in wanted)


def matching(session: Session, user: User, about: str | None) -> list[Fact]:
    """Facts mentioning any keyword of `about` (exact, prefix or close spelling), best first;
    every fact, newest first, when `about` has no keywords."""
    facts = list_facts(session, user)
    wanted = keywords(about)
    if not wanted:
        return facts
    scored = [(score(fact, wanted), fact) for fact in facts]
    return [fact for value, fact in sorted(scored, key=lambda pair: -pair[0]) if value > 0]


def forget(session: Session, user: User, about: str | None) -> Fact | None:
    """Deletes the fact that best matches `about` (the newest one on a tie or when `about` says
    nothing specific); returns it."""
    found = matching(session, user, about)
    if not found:
        return None
    fact = found[0]
    session.delete(fact)
    session.commit()
    return fact
