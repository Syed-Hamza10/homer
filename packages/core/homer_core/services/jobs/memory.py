import re

from sqlmodel import Session

from homer_core.agent.intents import Forget, Recall, Remember
from homer_core.db.models import Fact, User
from homer_core.services.facts import add_fact, forget, keywords, list_facts, matching
from homer_core.services.jobs.turn import Turn

SHOWN_FACTS = 10


def shown(text: str) -> str:
    """Facts saved as "The user's sister ..." read as "Your sister ..."."""
    text = re.sub(r"\bthe user's\b", "your", text, flags=re.IGNORECASE)
    text = re.sub(r"\bthe user\b", "you", text, flags=re.IGNORECASE)
    return text[:1].upper() + text[1:]


def listing(facts: list[Fact]) -> str:
    return "\n".join(f"- {shown(fact.text)}" for fact in facts[:SHOWN_FACTS])


def previous_fact(turn: Turn) -> Fact | None:
    """The one fact the previous turn saved or recalled, for "forget that"."""
    ids = [
        fact_id
        for item in turn.previous
        for fact_id in [item.get("fact_id"), *item.get("fact_ids", [])]
        if fact_id is not None
    ]
    if len(set(ids)) != 1:
        return None
    fact = turn.session.get(Fact, ids[0])
    return fact if fact is not None and fact.user_id == turn.user.id else None


def delete(session: Session, fact: Fact) -> Fact:
    session.delete(fact)
    session.commit()
    return fact


async def remember(turn: Turn, intent: Remember) -> None:
    fact = add_fact(turn.session, turn.user.id, intent.fact)
    turn.facts.append(fact.text)
    turn.note(fact_id=fact.id)
    turn.say(f"Saved to memory: {shown(fact.text)}")


def chosen(turn: Turn, user: User, about: str | None) -> Fact | None:
    if keywords(about):
        return forget(turn.session, user, about)
    fact = previous_fact(turn) or next(iter(list_facts(turn.session, user, 1)), None)
    return delete(turn.session, fact) if fact is not None else None


async def drop(turn: Turn, intent: Forget) -> None:
    about = intent.about if keywords(intent.about) else turn.message
    fact = chosen(turn, turn.user, about)
    if fact is not None:
        turn.facts[:] = [text for text in turn.facts if text != fact.text]
        turn.say(f"Forgot: {shown(fact.text)}")
        return
    saved = list_facts(turn.session, turn.user)
    if not saved:
        turn.say("I have nothing saved, so there is nothing to forget.")
        return
    turn.say(
        f"I have nothing saved about {about.strip()}. What I have saved:\n{listing(saved)}\n"
        "Say which one to forget."
    )


async def recall(turn: Turn, intent: Recall) -> None:
    facts = matching(turn.session, turn.user, intent.about)
    asked = keywords(intent.about)
    turn.note(fact_ids=[fact.id for fact in facts[:SHOWN_FACTS]])
    if not facts:
        about = f" about {intent.about}" if asked else ""
        turn.say(f"I have nothing saved{about}.")
        return
    if len(asked) > 2 and len(facts) == 1:
        turn.say(shown(facts[0].text))
        return
    who = f" about {intent.about}" if 0 < len(asked) <= 2 else ""
    turn.say(f"Here is what I have saved{who}:\n{listing(facts)}")
