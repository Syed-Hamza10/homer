import re

from homer_core.agent.claims import review
from homer_core.agent.intents import ChatIntent
from homer_core.agent.prompt import render_prompt
from homer_core.agent.routing import is_small_talk
from homer_core.services.jobs import mail_status, web_search
from homer_core.services.jobs.turn import Turn

HISTORY_MESSAGES = 8
SEARCH_SERVER = "search"
UNKNOWN = re.compile(
    r"\bI (?:don't|do not) know\b|\bI'm not sure\b|\bI am not sure\b"
    r"|\b(?:real-time|up-to-date|current) (?:information|data|news)\b"
    r"|\bmy (?:knowledge|training)(?: data)? (?:cutoff|cut-off)\b",
    re.IGNORECASE,
)
PERSONAL = re.compile(
    r"\b(?:my|mine|me|calendar|schedule|meetings?|inbox|e-?mails?|mail|remember|forget)\b",
    re.IGNORECASE,
)


def may_search(turn: Turn) -> bool:
    return (
        not PERSONAL.search(turn.message)
        and not is_small_talk(turn.message)
        and SEARCH_SERVER in turn.runtime.manager.toolsets
    )


async def run(turn: Turn, intent: ChatIntent) -> None:
    instructions = render_prompt(turn.user.name, turn.user.timezone, turn.now, turn.facts)
    index = await turn.stream(
        turn.message, instructions, turn.history[-HISTORY_MESSAGES:], guarded=False
    )
    text = turn.segments[index]
    reviewed = review(text, acted=False)
    if reviewed != text:
        turn.replace(index, mail_status.honest(turn) or reviewed)
    elif UNKNOWN.search(text) and may_search(turn):
        await web_search.answer(turn, turn.message, turn.message)
