from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

TEMPLATE = (Path(__file__).parent / "prompts" / "system.md").read_text()


@dataclass(frozen=True)
class Deps:
    user_name: str
    timezone: str


def render_prompt(deps: Deps, now: datetime) -> str:
    return TEMPLATE.format(
        user_name=deps.user_name, timezone=deps.timezone, now=now.strftime("%A %d %B %Y, %H:%M")
    )


def build_agent(model: Model) -> Agent[Deps, str]:
    agent: Agent[Deps, str] = Agent(model, deps_type=Deps, output_type=str)

    @agent.instructions
    def system(ctx: RunContext[Deps]) -> str:
        return render_prompt(ctx.deps, datetime.now(ZoneInfo(ctx.deps.timezone)))

    return agent
