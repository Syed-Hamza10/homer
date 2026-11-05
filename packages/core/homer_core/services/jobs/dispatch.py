from collections.abc import Awaitable, Callable
from typing import Any

from homer_core.agent.intents import Intent
from homer_core.services.jobs import (
    chat,
    create_event,
    read_calendar,
    read_email,
    remind,
    send_email,
    web_search,
)
from homer_core.services.jobs.turn import Turn

RUNNERS: dict[str, Callable[[Turn, Any], Awaitable[None]]] = {
    "send_email": send_email.run,
    "create_event": create_event.run,
    "read_calendar": read_calendar.run,
    "read_email": read_email.run,
    "web_search": web_search.run,
    "remind": remind.run,
    "chat": chat.run,
}


async def run(turn: Turn, intent: Intent) -> None:
    await RUNNERS[intent.kind](turn, intent)
