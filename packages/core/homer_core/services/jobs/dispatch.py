from collections.abc import Awaitable, Callable
from typing import Any

from homer_core.agent.intents import FreeTime, Intent, as_free
from homer_core.services.jobs import (
    calculate,
    change_event,
    chat,
    create_event,
    day_summary,
    draft_question,
    edit_email,
    mail_status,
    memory,
    read_calendar,
    read_email,
    remind,
    send_email,
    web_search,
)
from homer_core.services.jobs.turn import Turn


async def free_time(turn: Turn, intent: FreeTime) -> None:
    await read_calendar.run(turn, as_free(intent))


RUNNERS: dict[str, Callable[[Turn, Any], Awaitable[None]]] = {
    "send_email": send_email.run,
    "edit_draft": edit_email.edit,
    "draft_question": draft_question.question,
    "send_status": mail_status.status,
    "discard_draft": draft_question.discard,
    "free_time": free_time,
    "create_event": create_event.run,
    "update_event": change_event.update,
    "cancel_event": change_event.cancel,
    "read_calendar": read_calendar.run,
    "read_email": read_email.run,
    "web_search": web_search.run,
    "remind": remind.run,
    "remember": memory.remember,
    "correct_memory": memory.correct,
    "forget": memory.drop,
    "day_summary": day_summary.run,
    "recall": memory.recall,
    "calculate": calculate.run,
    "chat": chat.run,
}


async def run(turn: Turn, intent: Intent) -> None:
    turn.resolved.append(intent.model_dump(exclude_none=True))
    await RUNNERS[intent.kind](turn, intent)
