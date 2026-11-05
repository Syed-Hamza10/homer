from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models import Model

from homer_core.agent.intents import Intents, build_intent_agent
from homer_core.mcp.manager import McpManager


@dataclass(frozen=True)
class Runtime:
    model: Model
    manager: McpManager
    intents: Agent[None, Intents]
    contacts: dict[str, tuple[float, list[dict[str, Any]]]] = field(default_factory=dict)


def build_runtime(model: Model, manager: McpManager) -> Runtime:
    return Runtime(model=model, manager=manager, intents=build_intent_agent(model))
