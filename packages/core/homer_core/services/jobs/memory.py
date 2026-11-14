import structlog
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.exceptions import UnexpectedModelBehavior

from homer_core.agent.intents import CorrectMemory, Forget, Recall, Remember
from homer_core.agent.routing import first_to_second_person
from homer_core.agent.voice import capitalised, second_person
from homer_core.db.models import Fact
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
