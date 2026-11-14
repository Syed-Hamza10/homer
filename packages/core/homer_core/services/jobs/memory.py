import re

import structlog
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.exceptions import UnexpectedModelBehavior
from sqlmodel import col, select

from homer_core.agent.intents import (
    CorrectMemory,
    Forget,
    Intent,
    ReadEmail,
    Recall,
    Remember,
    calendar_read,
)
from homer_core.agent.routing import CALENDAR_ASKED, first_to_second_person
from homer_core.agent.voice import capitalised, second_person
from homer_core.db.models import EmailCache, Fact
from homer_core.services.facts import (
    add_fact,
    closest,
    keywords,
    list_facts,
    matching,
    prompt_facts,
    remove,
    update_fact,
)
from homer_core.services.jobs.turn import Turn

log = structlog.get_logger(__name__)

SHOWN_FACTS = 10
RECALL_TOOL = "answer_from_facts"
RECALL_PROMPT = """Answer the question from the saved facts below only, in one or two short
sentences, speaking to the person as "you". The facts are newest first. When two facts
contradict each other the newer one is true: answer from it and put the id of every older
fact it contradicts in `outdated`. When the facts do not answer the question, say in one
sentence what is saved about it.
Facts:
{facts}"""


MAIL_ASKED = re.compile(
    r"\b(?:e-?mails?|mail|inbox|unread|messages?|repl(?:y|ies)|sent|drafts?)\b",
    re.IGNORECASE,
)
ASKS = re.compile(
    r"\bwhat (?:did|does|do) (?P<who>[A-Za-z][\w'-]+)(?: [A-Z][\w'-]+)? (?:ask|say|write|send"
    r"|want|need|expect)",
    re.IGNORECASE,
)
NOT_SENDERS = frozenset({"i", "you", "we", "they", "he", "she", "it", "that", "this"})


class RecallAnswer(BaseModel):
    answer: str
    outdated: list[int] = Field(default_factory=list)


def shown(text: str) -> str:
    """Facts saved as "The user's sister ..." read as "Your sister ..."."""
    return capitalised(second_person(text))


def listing(facts: list[Fact]) -> str:
    return "\n".join(f"- {shown(fact.text)}" for fact in facts[:SHOWN_FACTS])


def refresh(turn: Turn) -> None:
    turn.facts[:] = prompt_facts(turn.session, turn.user)


def previous_facts(turn: Turn) -> list[Fact]:
    """The facts the previous turn saved, changed or recalled, for "forget that"."""
    ids = {
        fact_id
        for item in turn.previous
        for fact_id in [item.get("fact_id"), *item.get("fact_ids", [])]
        if fact_id is not None
    }
    facts = [turn.session.get(Fact, fact_id) for fact_id in sorted(ids)]
    return [fact for fact in facts if fact is not None and fact.user_id == turn.user.id]


async def remember(turn: Turn, intent: Remember) -> None:
    fact = add_fact(turn.session, turn.user.id, intent.fact, intent.about_person)
    refresh(turn)
    turn.note(fact_id=fact.id)
    turn.say(f"Saved to memory: {shown(fact.text)}")


def corrected(turn: Turn, about: str) -> Fact | None:
    """The fact a correction replaces: the one fact the previous turn touched when it is about
    the same person and topic or the words name nothing, else the closest match."""
    found = closest(turn.session, turn.user, about)
    earlier = previous_facts(turn)
    if len(earlier) == 1 and (not found or earlier[0] in found):
        return earlier[0]
    return found[0] if found else None


async def correct(turn: Turn, intent: CorrectMemory) -> None:
    text = first_to_second_person(intent.new_fact)
    fact = corrected(turn, intent.about)
    if fact is None:
        fact = add_fact(turn.session, turn.user.id, text)
        turn.say(f"Saved to memory: {shown(fact.text)}")
    else:
        fact = update_fact(turn.session, fact, text)
        turn.say(f"Updated: {shown(fact.text)}")
    refresh(turn)
    turn.note(fact_id=fact.id)


def forgotten(turn: Turn, about: str | None) -> list[Fact]:
    """Every fact about the person or topic, else what the previous turn touched, else the
    newest fact."""
    if about is not None:
        return closest(turn.session, turn.user, about)
    return previous_facts(turn) or list_facts(turn.session, turn.user, 1)


async def drop(turn: Turn, intent: Forget) -> None:
    about = next((text for text in (intent.about, turn.message) if keywords(text)), None)
    facts = [remove(turn.session, fact) for fact in forgotten(turn, about)]
    refresh(turn)
    if len(facts) == 1:
        turn.say(f"Forgot: {shown(facts[0].text)}")
        return
    if facts:
        turn.say(f"Forgot {len(facts)} things:\n{listing(facts)}")
        return
    saved = list_facts(turn.session, turn.user)
    if not saved:
        turn.say("I have nothing saved, so there is nothing to forget.")
        return
    asked = (about or turn.message).strip()
    turn.say(
        f"I have nothing saved about {asked}. What I have saved:\n{listing(saved)}\n"
        "Say which one to forget."
    )


def fact_lines(facts: list[Fact]) -> str:
    return "\n".join(
        f"[{fact.id}] saved {fact.updated_at:%Y-%m-%d %H:%M}: {shown(fact.text)}" for fact in facts
    )


async def answered(turn: Turn, facts: list[Fact]) -> RecallAnswer | None:
    output = ToolOutput(RecallAnswer, name=RECALL_TOOL, description="Records the answer.")
    instructions = RECALL_PROMPT.format(facts=fact_lines(facts))
    agent = Agent(turn.runtime.model, output_type=output, instructions=instructions)
    try:
        return await turn.extract(agent, turn.message)
    except UnexpectedModelBehavior:
        log.warning("recall_failed", message=turn.message)
        return None


def drop_outdated(turn: Turn, facts: list[Fact], outdated: list[int]) -> None:
    """Deletes the facts a newer one contradicts; the newest fact asked about always stays."""
    for fact in facts[1:]:
        if fact.id in outdated:
            log.info("fact_outdated", fact_id=fact.id)
            remove(turn.session, fact)
    refresh(turn)


async def recall(turn: Turn, intent: Recall) -> None:
    found_facts = matching(turn.session, turn.user, intent.about)[:SHOWN_FACTS]
    facts = sorted(found_facts, key=lambda fact: fact.updated_at, reverse=True)
    turn.note(fact_ids=[fact.id for fact in facts])
    if not facts:
        about = f" about {intent.about}" if keywords(intent.about) else ""
        turn.say(f"I have nothing saved{about}.")
        return
    found = await answered(turn, facts)
    if found is None or not found.answer.strip():
        turn.say(f"Here is what I have saved:\n{listing(facts)}")
        return
    drop_outdated(turn, facts, found.outdated)
    turn.say(capitalised(second_person(found.answer.strip())))


def sender(message: str) -> str | None:
    """Who "what does Owen want" or "what did Rosa ask" asks about."""
    found = ASKS.search(message)
    return found["who"] if found and found["who"].lower() not in NOT_SENDERS else None


def has_mail(turn: Turn, who: str) -> bool:
    """Mail from someone of that name is in the cached inbox."""
    rows = select(EmailCache.id).where(
        EmailCache.user_id == turn.user.id, col(EmailCache.sender).icontains(who)
    )
    return turn.session.exec(rows.limit(1)).first() is not None


def rerouted(turn: Turn, intent: Recall) -> Intent:
    """A recall about mail or the calendar that no saved fact answers is a mail or calendar
    read: "when is my next meeting" is never a memory question. "What does Owen want from me"
    reads Owen's mail unless only a saved fact knows Owen."""
    who = sender(turn.message)
    known = matching(turn.session, turn.user, intent.about)
    if who and (not known or has_mail(turn, who)):
        log.info("recall_rerouted", to="read_email", message=turn.message)
        return ReadEmail(kind="read_email", question=turn.message, sender=who)
    if known:
        return intent
    asked = f"{intent.about or ''} {turn.message}"
    if MAIL_ASKED.search(asked):
        log.info("recall_rerouted", to="read_email", message=turn.message)
        return ReadEmail(kind="read_email", question=intent.about or turn.message)
    if CALENDAR_ASKED.search(asked):
        log.info("recall_rerouted", to="read_calendar", message=turn.message)
        return calendar_read(turn.message, turn.now.date())
    return intent
