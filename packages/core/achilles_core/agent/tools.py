from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic_ai import RunContext
from pydantic_ai.toolsets import FunctionToolset

from achilles_core.agent.agent import Deps
from achilles_core.services.reminders import create_reminder


async def remind(ctx: RunContext[Deps], text: str, when_iso: str) -> dict[str, Any]:
    """Saves a reminder for the user. when_iso is an ISO 8601 datetime, e.g. 2026-10-17T09:00:00."""
    due_at = datetime.fromisoformat(when_iso)
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=ZoneInfo(ctx.deps.timezone))
    due_at = due_at.astimezone(UTC)
    reminder = create_reminder(ctx.deps.session, ctx.deps.user_id, text, due_at)
    return {"id": reminder.id, "text": reminder.text, "due_at": reminder.due_at.isoformat()}


def build_core_toolset() -> FunctionToolset[Deps]:
    return FunctionToolset([remind], id="core")
