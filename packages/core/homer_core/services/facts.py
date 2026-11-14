import re
from difflib import SequenceMatcher

from sqlmodel import Session, col, select

from homer_core.db.models import Fact, User, utcnow
from homer_core.services.errors import NotFound

PROMPT_FACTS = 20


def add_fact(session: Session, user_id: int, text: str, person: str | None = None) -> Fact:
    fact = Fact(user_id=user_id, text=text.strip(), person=person)
    session.add(fact)
    session.commit()
    session.refresh(fact)
    return fact


def update_fact(session: Session, fact: Fact, text: str, person: str | None = None) -> Fact:
    fact.text = text.strip()
    fact.person = person or fact.person
    fact.updated_at = utcnow()
    session.add(fact)
    session.commit()
    session.refresh(fact)
    return fact


def list_facts(session: Session, user: User, limit: int | None = None) -> list[Fact]:
    """Newest change first."""
    statement = (
        select(Fact)
        .where(Fact.user_id == user.id)
        .order_by(col(Fact.updated_at).desc(), col(Fact.id).desc())
        .limit(limit)
    )
    return list(session.exec(statement))


def prompt_facts(session: Session, user: User) -> list[str]:
    """The latest facts, oldest first, for the prompts."""
    return [fact.text for fact in reversed(list_facts(session, user, PROMPT_FACTS))]


def remove(session: Session, fact: Fact) -> Fact:
    session.delete(fact)
    session.commit()
    return fact


def delete_fact(session: Session, user: User, fact_id: int) -> None:
    fact = session.get(Fact, fact_id)
    if fact is None or fact.user_id != user.id:
        raise NotFound(f"fact {fact_id} not found")
    remove(session, fact)


STOP_WORDS = frozenset(
    {"that", "this", "the", "a", "an", "thing", "things", "stuff", "about", "please", "pls"}
    | {"forget", "remember", "fact", "info", "information", "bit", "one", "it", "what", "you"}
    | {"know", "said", "told", "i", "me", "my", "your", "of", "on", "re", "and", "to", "is"}
)
CLOSE_ENOUGH = 0.8
PREFIX = 4
NEAR_BEST = 0.75


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
    text = f"{fact.person or ''} {fact.text}".lower().replace("'s", "")
    words = re.findall(r"[\w-]+", text)
    return sum(word_score(keyword, words) for keyword in wanted)


def scored(session: Session, user: User, about: str | None) -> list[tuple[float, Fact]]:
    """Every fact with its keyword score for `about`, best first, newest first on a tie."""
    wanted = keywords(about)
    pairs = [(score(fact, wanted), fact) for fact in list_facts(session, user)]
    return sorted(pairs, key=lambda pair: -pair[0])


def matching(session: Session, user: User, about: str | None) -> list[Fact]:
    """Facts mentioning any keyword of `about` (exact, prefix or close spelling), best first;
    every fact, newest first, when `about` has no keywords."""
    if not keywords(about):
        return list_facts(session, user)
    pairs = scored(session, user, about)
    best = pairs[0][0] if pairs else 0.0
    return [fact for value, fact in pairs if value > 0 and value >= best / 2]


def closest(session: Session, user: User, about: str | None) -> list[Fact]:
    """The facts about the same person and topic as `about`: those scoring near the best, so
    "Imran" matches every Imran fact and "Tariq's wedding" only the wedding ones."""
    if not keywords(about):
        return []
    pairs = scored(session, user, about)
    best = pairs[0][0] if pairs else 0.0
    return [fact for value, fact in pairs if value > 0 and value >= best * NEAR_BEST]
