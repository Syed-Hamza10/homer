import re
from datetime import datetime

from pydantic_ai import Agent

from homer_core.agent.claims import review
from homer_core.agent.intents import ChatIntent, FixLastAction
from homer_core.agent.prompt import render_prompt
from homer_core.agent.routing import is_small_talk, personal
from homer_core.agent.voice import UNKNOWN
from homer_core.services.facts import matching
from homer_core.services.jobs import fix_action, mail_status, memory, web_search
from homer_core.services.jobs.turn import Turn

HISTORY_MESSAGES = 8
EMPTY = "Sorry, I lost my answer there. Could you ask that once more?"
SEARCH_SERVER = "search"
PERSONAL = re.compile(
    r"\b(?:my|mine|me|calendar|schedule|meetings?|inbox|e-?mails?|mail|remember|forget)\b",
    re.IGNORECASE,
)


CLAIMED_NOW = re.compile(
    r"\b(?:it(?:'s| is)(?: now)?|the (?:current |local )?time (?:is|there is)|currently|right now"
    r"|now)\s*(?:it(?:'s| is)\s+)?(?:about |around |exactly )?(?P<clock>\d{1,2}:\d{2})\b",
    re.IGNORECASE,
)


DAY_WISH = re.compile(
    r"\b(?:have|enjoy)\s+(?:a|an|your|the rest of your)\s+(?:\w+\s+){0,2}?"
    r"(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)


def on_time(text: str, now: datetime) -> str:
    """A reply that tells the time tells the prompt's time, never one the model made up."""
    return CLAIMED_NOW.sub(lambda m: m.group(0).replace(m["clock"], f"{now:%H:%M}"), text)


def on_today(text: str, now: datetime) -> str:
    """ "Have a great Sunday" on a Saturday becomes "Have a great day"."""

    def fixed(match: re.Match[str]) -> str:
        if match["day"].lower() == f"{now:%A}".lower():
            return match.group(0)
        return match.group(0)[: match.start("day") - match.start()] + "day"

    return DAY_WISH.sub(fixed, text)


def may_search(turn: Turn) -> bool:
    return (
        not PERSONAL.search(turn.message)
        and not personal(turn.message, turn.facts)
        and not is_small_talk(turn.message)
        and SEARCH_SERVER in turn.runtime.manager.toolsets
    )


async def run(turn: Turn, intent: ChatIntent) -> None:
    instructions = render_prompt(turn.user.name, turn.user.timezone, turn.now, turn.facts)
    index = await turn.stream(
        turn.message, instructions, turn.history[-HISTORY_MESSAGES:], guarded=False
    )
    text = turn.segments[index]
    if fix_action.DEFERS.search(text) and fix_action.last_action(turn) is not None:
        turn.replace(index, "")
        await fix_action.fix(
            turn, FixLastAction(kind="fix_last_action", what_is_wrong=turn.message)
        )
        return
    if not text:
        turn.replace(index, await second_try(turn, instructions))
        return
    if (timed := on_today(on_time(text, turn.now), turn.now)) != text:
        turn.replace(index, timed)
        text = timed
    reviewed = review(text, acted=False)
    if reviewed != text:
        turn.replace(index, mail_status.honest(turn) or reviewed)
    elif UNKNOWN.search(text) and may_search(turn):
        await web_search.answer(turn, turn.message, turn.message)


async def second_try(turn: Turn, instructions: str) -> str:
    """For an empty answer: the saved facts the message names, else one more model call."""
    if personal(turn.message, turn.facts):
        facts = matching(turn.session, turn.user, turn.message)
        if facts:
            return memory.listing(facts)
    agent = Agent(turn.runtime.model, output_type=str, instructions=instructions)
    text = (await turn.extract(agent, turn.message)).strip()
    return text or EMPTY
