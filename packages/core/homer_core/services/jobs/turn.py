import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import RunUsage
from sqlmodel import Session

from homer_core.agent.claims import HONEST, claims_sending
from homer_core.agent.dates import DateFormat, default_format
from homer_core.agent.runtime import Runtime
from homer_core.agent.voice import HINT, leaks, scrubbed
from homer_core.db.models import Approval, User
from homer_core.services.rules import ClientRules

log = structlog.get_logger(__name__)

SUMMARY_LENGTH = 200
MIN_SCRUBBED_WORDS = 6
RECONNECT = "Your Google connection has expired. Reconnect it in Settings, it takes a minute."
RECONNECT_EVENT = "google_reconnect"
BLOCKED = "search_blocked"
ERRORS = {
    "web_search_off": "Web search is turned off, so I cannot look that up. "
    "You can turn it on in Settings.",
    BLOCKED: "The search engine is limiting searches from this computer for a few "
    "minutes, so I can't look that up right now. Try again shortly.",
    "google_contacts_warming": "Google's contacts service is waking up; please try again in "
    "a few seconds.",
    "search_invalid_key": "The search service did not accept the API key, so I can't look "
    "that up. Check the key under Web search in Settings.",
    "search_limited": "The search service has used up its free searches or is asking me to "
    "slow down, so I can't look that up right now. Try again later.",
}


@dataclass(frozen=True)
class ChatEvent:
    name: str
    data: dict[str, Any]


class JobError(Exception):
    """A job cannot go on; the message is said to the user as is."""


class ReconnectRequired(JobError):
    """Google refused the token; no job that needs Google can run this turn."""


def failure(tool: str, result: Any) -> str | None:
    if not isinstance(result, dict) or "error" not in result:
        return None
    error = str(result["error"])
    if error in ERRORS:
        return ERRORS[error]
    detail = str(result.get("message") or result.get("detail") or "")
    structlog.get_logger().warning("tool_failed", tool=tool, error=error, detail=detail[:500])
    return (
        f"Something went wrong talking to {service_name(tool)}, so I stopped. "
        "Nothing was sent or changed. Try again in a moment."
    )


def service_name(tool: str) -> str:
    if tool.startswith("cal_"):
        return "Google Calendar"
    if tool.startswith(("mail_", "contacts_")):
        return "Gmail"
    return "the web" if tool in {"web_search", "fetch_page"} else "a service"


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
    previous: list[dict[str, Any]] = field(default_factory=list)
    earlier: list[dict[str, Any]] = field(default_factory=list)
    resolved: list[dict[str, Any]] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    blocked: dict[str, str] = field(default_factory=dict)
    picked: dict[str, dict[str, Any]] = field(default_factory=dict)
    question: dict[str, Any] | None = None

    @property
    def date_format(self) -> DateFormat:
        return self.rules.date_format or default_format(self.user.timezone)

    def note(self, **fields: Any) -> None:
        """Adds what a job resolved (dates, approval ids) to the current intent's record."""
        self.resolved[-1].update({k: v for k, v in fields.items() if v is not None})

    @property
    def answer(self) -> str:
        return "\n\n".join(segment for segment in self.segments if segment)

    def emit(self, name: str, data: dict[str, Any]) -> None:
        self.events.put_nowait(ChatEvent(name, data))

    def say(self, text: str) -> None:
        separator = "\n\n" if self.answer else ""
        self.segments.append(text)
        self.emit("token", {"text": separator + text})

    def ask_to_reconnect(self) -> None:
        self.say(RECONNECT)
        self.emit(RECONNECT_EVENT, {"url": "/settings"})

    def replace(self, index: int, text: str) -> None:
        self.segments[index] = text
        self.emit("replace", {"text": self.answer})

    async def call(self, server: str, tool: str, args: dict[str, Any]) -> Any:
        """Calls the tool; after the search engine's bot check, later searches this turn fail
        straight away instead of asking again."""
        if tool in self.blocked:
            raise JobError(self.blocked[tool])
        self.emit("tool_call", {"name": tool, "args": args})
        result = await self.runtime.manager.call(server, tool, args)
        self.emit("tool_result", {"name": tool, "summary": summarise(result)})
        if isinstance(result, dict) and result.get("error") == "google_reconnect_required":
            raise ReconnectRequired(RECONNECT)
        problem = failure(tool, result)
        if problem is not None:
            if result.get("error") == BLOCKED:
                self.blocked[tool] = problem
            raise JobError(problem)
        return result

    def requested(self, approval: Approval) -> None:
        approval.conversation_id = self.conversation_id
        self.session.add(approval)
        self.session.commit()
        self.session.refresh(approval)
        self.approvals.append(approval)
        self.show(approval)

    def show(self, approval: Approval, again: bool = False) -> None:
        """Streams the approval card; `again` marks a card shown before, which this turn did
        not create."""
        data = {
            "approval_id": approval.id,
            "action": approval.action,
            "preview": approval.preview,
            "payload": json.loads(approval.payload_json),
        }
        self.emit("approval_required", data | ({"again": True} if again else {}))

    async def extract[T](self, agent: Agent[None, T], prompt: str) -> T:
        result = await agent.run(prompt)
        self.usage.incr(result.usage)
        return result.output

    async def stream(
        self,
        prompt: str,
        instructions: str,
        history: list[ModelMessage] | None = None,
        guarded: bool = True,
    ) -> int:
        """Streams one model answer as a new segment; returns the segment's index. A guarded
        answer that claims an email went out is replaced, since no model call sends anything."""
        separator = "\n\n" if self.answer else ""
        index = len(self.segments)
        self.segments.append("")
        agent = Agent(self.runtime.model, output_type=str, instructions=instructions)
        try:
            async with agent.run_stream(prompt, message_history=history or []) as result:
                async for delta in result.stream_text(delta=True):
                    if not self.segments[index] and separator:
                        self.emit("token", {"text": separator})
                    self.segments[index] += delta
                    self.emit("token", {"text": delta})
                self.usage.incr(result.usage)
        except UnexpectedModelBehavior:
            log.warning("empty_model_answer", text=self.segments[index])
        self.segments[index] = self.segments[index].strip()
        if guarded and claims_sending(self.segments[index]):
            log.warning("unbacked_action_claim", text=self.segments[index])
            self.replace(index, HONEST)
        elif leaks(self.segments[index]):
            await self.rephrase(index, prompt, instructions, history)
        return index

    async def rephrase(
        self, index: int, prompt: str, instructions: str, history: list[ModelMessage] | None
    ) -> None:
        """Replaces an answer that talks about its sources or "the user": scrubbed when enough
        is left, else written once more with a hint, then scrubbed."""
        log.warning("scaffolding_leak", text=self.segments[index])
        text = scrubbed(self.segments[index])
        if len(text.split()) < MIN_SCRUBBED_WORDS:
            agent = Agent(self.runtime.model, output_type=str, instructions=instructions + HINT)
            result = await agent.run(prompt, message_history=history or [])
            self.usage.incr(result.usage)
            text = scrubbed(result.output) or text
        self.replace(index, text)
