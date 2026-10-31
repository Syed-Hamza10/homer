from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from sqlmodel import Session

TEMPLATE = (Path(__file__).parent / "prompts" / "system.md").read_text()


@dataclass(frozen=True)
class Deps:
    user_id: int
    user_name: str
    timezone: str
    session: Session


def describe(day: datetime) -> str:
    return day.strftime("%A %Y-%m-%d")


def render_prompt(deps: Deps, now: datetime) -> str:
    return TEMPLATE.format(
        user_name=deps.user_name,
        timezone=deps.timezone,
        now=now.strftime("%A %d %B %Y, %H:%M"),
        today=describe(now),
        tomorrow=describe(now + timedelta(days=1)),
        yesterday=describe(now - timedelta(days=1)),
    )


def build_agent(model: Model) -> Agent[Deps, str]:
    agent: Agent[Deps, str] = Agent(model, deps_type=Deps, output_type=str)

    @agent.instructions
    def system(ctx: RunContext[Deps]) -> str:
        return render_prompt(ctx.deps, datetime.now(ZoneInfo(ctx.deps.timezone)))

    return agent
