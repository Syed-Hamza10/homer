import json
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.toolsets import WrapperToolset
from pydantic_ai.toolsets.abstract import ToolsetTool

from achilles_core.agent.agent import Deps
from achilles_core.agent.toolsets import TIER_2_TOOLS
from achilles_core.db.models import Approval
from achilles_core.services.approvals import create_from_tool_result, is_approval_object

UNTRUSTED_TAG = "<untrusted>"
APPROVAL_METADATA_KEY = "approval"


@dataclass
class RunState:
    untrusted_seen: bool = False
    approvals: list[Approval] = field(default_factory=list)


def tier_2_approval(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval_required": True,
        "action": name,
        "payload": args,
        "preview": f"{name} {json.dumps(args)} (proposed after reading untrusted content)",
    }


@dataclass
class ApprovalGate(WrapperToolset[Deps]):
    """Turns approval objects from tools into stored approvals and a short text for the model."""

    state: RunState

    async def call_tool(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[Deps], tool: ToolsetTool[Deps]
    ) -> Any:
        if name in TIER_2_TOOLS and self.state.untrusted_seen:
            result: Any = tier_2_approval(name, tool_args)
        else:
            result = await super().call_tool(name, tool_args, ctx, tool)
        if not is_approval_object(result):
            if UNTRUSTED_TAG in str(result):
                self.state.untrusted_seen = True
            return result
        approval = create_from_tool_result(
            ctx.deps.session, ctx.deps.user_id, tool.toolset.id or "core", result
        )
        self.state.approvals.append(approval)
        return ToolReturn(
            return_value=f"Approval #{approval.id} requested; the user will decide",
            metadata={APPROVAL_METADATA_KEY: approval.id},
        )
