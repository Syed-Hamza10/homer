import json
import re
from dataclasses import dataclass, field
from typing import Any

import structlog
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ToolReturn
from pydantic_ai.toolsets import WrapperToolset
from pydantic_ai.toolsets.abstract import ToolsetTool

from achilles_core.agent.agent import Deps
from achilles_core.agent.toolsets import TIER_2_TOOLS
from achilles_core.db.models import Approval
from achilles_core.services.approvals import create_from_tool_result, is_approval_object

log = structlog.get_logger(__name__)

UNTRUSTED_TAG = "<untrusted>"
APPROVAL_METADATA_KEY = "approval"
DRAFT_TOOL = "mail_draft"
SEND_TOOL = "mail_send"
DRAFT_ID_PATTERN = re.compile(r"\br-\d{19}\b")


@dataclass
class RunState:
    untrusted_seen: bool = False
    approvals: list[Approval] = field(default_factory=list)
    draft_ids: list[str] = field(default_factory=list)

    def remember_draft(self, draft_id: str) -> None:
        if draft_id not in self.draft_ids:
            self.draft_ids.append(draft_id)

    def resolve_draft(self, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Swaps a guessed draft_id for the only known one; refuses when the choice is unclear."""
        given, known = str(args.get("draft_id", "")), self.draft_ids
        if not known or given in known:
            return args, None
        if len(known) == 1:
            log.info("draft_id_substituted", given=given, draft_id=known[0])
            return {**args, "draft_id": known[0]}, None
        return args, {"error": "unknown_draft_id", "draft_id": given, "known_draft_ids": known}


def mentioned_draft_ids(history: list[ModelMessage], prompt: str) -> list[str]:
    texts = [str(getattr(part, "content", "")) for message in history for part in message.parts]
    return list(dict.fromkeys(DRAFT_ID_PATTERN.findall(" ".join([*texts, prompt]))))


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
        if name == SEND_TOOL:
            tool_args, refusal = self.state.resolve_draft(tool_args)
            if refusal is not None:
                return refusal
        if name in TIER_2_TOOLS and self.state.untrusted_seen:
            result: Any = tier_2_approval(name, tool_args)
        else:
            result = await super().call_tool(name, tool_args, ctx, tool)
        if name == DRAFT_TOOL and isinstance(result, dict) and result.get("draft_id"):
            self.state.remember_draft(str(result["draft_id"]))
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
