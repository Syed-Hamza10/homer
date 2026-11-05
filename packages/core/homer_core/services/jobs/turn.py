import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import RunUsage
from sqlmodel import Session

from homer_core.agent.runtime import Runtime
from homer_core.db.models import Approval, User
from homer_core.services.rules import ClientRules

SUMMARY_LENGTH = 200
ERRORS = {
    "google_not_connected": "Google is not connected yet. Run homer-mcp-google-setup first.",
    "web_search_off": "Web search is turned off, so I cannot look that up. "
    "You can turn it on in Settings.",
}


@dataclass(frozen=True)
class ChatEvent:
    name: str
    data: dict[str, Any]


class JobError(Exception):
    """A job cannot go on; the message is said to the user as is."""


def failure(tool: str, result: Any) -> str | None:
    if not isinstance(result, dict) or "error" not in result:
        return None
    error = str(result["error"])
    detail = result.get("message") or result.get("detail") or ""
    return ERRORS.get(error, f"{tool} failed: {error} {detail}".strip())


def summarise(content: Any) -> str:
    text = content if isinstance(content, str) else json.dumps(content, default=str)
    return text if len(text) <= SUMMARY_LENGTH else text[: SUMMARY_LENGTH - 1] + "…"


@dataclass
class Turn:
    """One chat turn: what the jobs share, and the events they stream to the browser."""

    session: Session
    user: User
    message: str
    runtime: Runtime
    rules: ClientRules
    history: list[ModelMessage]
    now: datetime
    events: asyncio.Queue[ChatEvent | None] = field(default_factory=asyncio.Queue)
    segments: list[str] = field(default_factory=list)
    usage: RunUsage = field(default_factory=RunUsage)
    approvals: list[Approval] = field(default_factory=list)
    conversation_id: int | None = None

    @property
    def answer(self) -> str:
        return "\n\n".join(segment for segment in self.segments if segment)

    def emit(self, name: str, data: dict[str, Any]) -> None:
        self.events.put_nowait(ChatEvent(name, data))

    def say(self, text: str) -> None:
        separator = "\n\n" if self.answer else ""
        self.segments.append(text)
        self.emit("token", {"text": separator + text})

    def replace(self, index: int, text: str) -> None:
        self.segments[index] = text
        self.emit("replace", {"text": self.answer})

    async def call(self, server: str, tool: str, args: dict[str, Any]) -> Any:
        self.emit("tool_call", {"name": tool, "args": args})
        result = await self.runtime.manager.call(server, tool, args)
        self.emit("tool_result", {"name": tool, "summary": summarise(result)})
        problem = failure(tool, result)
        if problem is not None:
            raise JobError(problem)
        return result

    def requested(self, approval: Approval) -> None:
        approval.conversation_id = self.conversation_id
        self.session.add(approval)
        self.session.commit()
        self.session.refresh(approval)
        self.approvals.append(approval)
        self.emit(
            "approval_required",
            {
                "approval_id": approval.id,
                "action": approval.action,
                "preview": approval.preview,
                "payload": json.loads(approval.payload_json),
            },
        )

    async def extract[T](self, agent: Agent[None, T], prompt: str) -> T:
        result = await agent.run(prompt)
        self.usage.incr(result.usage)
        return result.output

    async def stream(
        self, prompt: str, instructions: str, history: list[ModelMessage] | None = None
    ) -> int:
        """Streams one model answer as a new segment; returns the segment's index."""
        separator = "\n\n" if self.answer else ""
        index = len(self.segments)
        self.segments.append("")
        agent = Agent(self.runtime.model, output_type=str, instructions=instructions)
        async with agent.run_stream(prompt, message_history=history or []) as result:
            async for delta in result.stream_text(delta=True):
                if not self.segments[index] and separator:
                    self.emit("token", {"text": separator})
                self.segments[index] += delta
                self.emit("token", {"text": delta})
            self.usage.incr(result.usage)
        self.segments[index] = self.segments[index].strip()
        return index
