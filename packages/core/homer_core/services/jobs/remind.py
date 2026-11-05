from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from homer_core.agent.intents import Remind
from homer_core.services.jobs.turn import Turn
from homer_core.services.reminders import create_reminder

DEFAULT_TIME = "09:00"


async def run(turn: Turn, intent: Remind) -> None:
    local = datetime.combine(
        date.fromisoformat(intent.date),
        time.fromisoformat(intent.time or DEFAULT_TIME),
        ZoneInfo(turn.user.timezone),
    )
    create_reminder(turn.session, turn.user.id, intent.text, local.astimezone(UTC))
    turn.say(f"Reminder set for {local:%a %d %b %H:%M}: {intent.text}.")
