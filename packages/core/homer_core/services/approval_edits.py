import json
import re
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, BeforeValidator
from sqlalchemy import update
from sqlmodel import Session

from homer_core.agent.intents import clock, iso_date
from homer_core.db.models import Approval, User
from homer_core.mcp.manager import McpManager
from homer_core.services.approvals import (
    SUPERSEDED,
    NotPending,
    create_from_tool_result,
    get_approval,
    is_approval_object,
    transition_from_pending,
)
from homer_core.services.errors import DomainError
from homer_core.services.jobs.send_email import request_send

QUOTED_TITLE = re.compile(r"'(.+?)'")


Editor = Callable[[Session, User, McpManager, Approval, Any], Awaitable[Approval]]


class NotEditable(DomainError):
    status_code = 422


def address(value: str) -> str:
    if "@" not in value:
        raise ValueError(f"not an email address: {value!r}")
    return value.strip()


Address = Annotated[str, AfterValidator(address)]


class MailEdit(BaseModel):
    to: Address
    subject: str
    body: str


class EventEdit(BaseModel):
    title: str
    date: Annotated[str, BeforeValidator(iso_date)]
    start: Annotated[str, BeforeValidator(clock)]
    end: Annotated[str, BeforeValidator(clock)]
    attendees: list[Address] = []


def problem(result: Any) -> str | None:
    if isinstance(result, dict) and "error" in result:
        return str(result.get("message") or result["error"])
    return None


async def edited_mail(
    session: Session, user: User, manager: McpManager, approval: Approval, change: MailEdit
) -> Approval:
    payload = json.loads(approval.payload_json)
    args = {
        "draft_id": payload["draft_id"],
        "to": change.to,
        "subject": change.subject,
        "body": change.body,
        "thread_id": payload.get("thread_id") or None,
    }
    result = await manager.call("google", "mail_draft_update", args)
    if (error := problem(result)) is not None:
        raise DomainError(f"could not update the draft: {error}")
    return request_send(
        session,
        user.id,
        payload["draft_id"],
        change.to,
        change.subject,
        change.body,
        str(payload.get("thread_id") or ""),
        payload.get("to_name", "") if change.to == payload["to"] else "",
    )


async def edited_event(
    session: Session, user: User, manager: McpManager, approval: Approval, change: EventEdit
) -> Approval:
    payload = json.loads(approval.payload_json)
    args = {
        "title": change.title,
        "start": f"{change.date}T{change.start}:00",
        "end": f"{change.date}T{change.end}:00",
        "attendees": change.attendees,
        "description": payload.get("description", ""),
        "location": payload.get("location", ""),
        "timezone": user.timezone,
    }
    result = await manager.call("google", "cal_create", args)
    if not is_approval_object(result):
        raise DomainError(f"could not update the event: {problem(result) or result}")
    return create_from_tool_result(session, user.id, "google", result)


def current_title(preview: str) -> str:
    found = QUOTED_TITLE.search(preview)
    return found.group(1) if found else ""


async def edited_update(
    session: Session, user: User, manager: McpManager, approval: Approval, change: EventEdit
) -> Approval:
    payload = json.loads(approval.payload_json)
    args: dict[str, Any] = {
        "event_id": payload["event_id"],
        "start": f"{change.date}T{change.start}:00",
        "end": f"{change.date}T{change.end}:00",
        "timezone": payload.get("timezone") or user.timezone,
    }
    if change.title.strip() and change.title.strip() != current_title(approval.preview):
        args["title"] = change.title.strip()
    if change.attendees:
        args["attendees"] = change.attendees
    result = await manager.call("google", "cal_update", args)
    if not is_approval_object(result):
        raise DomainError(f"could not update the event change: {problem(result) or result}")
    return create_from_tool_result(session, user.id, "google", result)


EDITORS: dict[tuple[str, type[BaseModel]], Editor] = {
    ("mail_send", MailEdit): edited_mail,
    ("cal_create", EventEdit): edited_event,
    ("cal_update", EventEdit): edited_update,
}


def reopen(session: Session, approval: Approval) -> None:
    session.exec(
        update(Approval)
        .where(Approval.id == approval.id, Approval.status == SUPERSEDED)
        .values(status="pending", decided_at=None)
    )
    session.commit()


async def edit(
    session: Session,
    user: User,
    approval_id: int,
    manager: McpManager,
    change: MailEdit | EventEdit,
) -> Approval:
    """Supersedes the pending approval before touching Gmail or Calendar, so an approve racing
    the edit finds nothing pending, then returns its fresh replacement. A failed edit puts the
    old approval back."""
    approval = get_approval(session, user, approval_id)
    if approval.status != "pending":
        raise NotPending(f"approval {approval.id} is {approval.status}, not pending")
    editor = EDITORS.get((approval.action, type(change)))
    if editor is None:
        raise NotEditable(f"approval {approval.id} ({approval.action}) cannot take that edit")
    transition_from_pending(session, approval, SUPERSEDED)
    try:
        fresh = await editor(session, user, manager, approval, change)
    except BaseException:
        reopen(session, approval)
        raise
    fresh.conversation_id = approval.conversation_id
    fresh.message_id = approval.message_id
    session.add(fresh)
    session.commit()
    session.refresh(fresh)
    return fresh
