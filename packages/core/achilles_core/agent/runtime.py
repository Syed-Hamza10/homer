from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset

from achilles_core.agent.agent import Deps, build_agent
from achilles_core.agent.router import build_classifier
from achilles_core.agent.tools import build_core_toolset
from achilles_core.agent.toolsets import build_toolsets
from achilles_core.mcp.manager import McpManager


@dataclass(frozen=True)
class Runtime:
    agent: Agent[Deps, str]
    classifier: Agent[None, str]
    toolsets: dict[str, AbstractToolset[Deps]]
    manager: McpManager


def build_runtime(model: Model, manager: McpManager) -> Runtime:
    return Runtime(
        agent=build_agent(model),
        classifier=build_classifier(model),
        toolsets=build_toolsets(manager.model_toolset(), build_core_toolset()),
        manager=manager,
    )
