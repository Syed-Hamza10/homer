import json
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, BeforeValidator
from sqlmodel import Session

from homer_core.agent.intents import clock, iso_date
from homer_core.db.models import Approval, User
from homer_core.mcp.manager import McpManager
from homer_core.services.approvals import (
    NotPending,
    create_from_tool_result,
    get_approval,
    is_approval_object,
    transition_from_pending,
)
from homer_core.services.errors import DomainError
from homer_core.services.jobs.send_email import request_send

SUPERSEDED = "superseded"


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
    session: Session, user: User, manager: McpManager, payload: dict[str, Any], change: MailEdit
) -> Approval:
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
    )


async def edited_event(
    session: Session, user: User, manager: McpManager, payload: dict[str, Any], change: EventEdit
) -> Approval:
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


async def edit(
    session: Session,
    user: User,
    approval_id: int,
    manager: McpManager,
    change: MailEdit | EventEdit,
) -> Approval:
    """Applies the edit, supersedes the pending approval and returns its fresh replacement."""
    approval = get_approval(session, user, approval_id)
    if approval.status != "pending":
        raise NotPending(f"approval {approval.id} is {approval.status}, not pending")
    payload = json.loads(approval.payload_json)
    match approval.action, change:
        case "mail_send", MailEdit():
            fresh = await edited_mail(session, user, manager, payload, change)
        case "cal_create", EventEdit():
            fresh = await edited_event(session, user, manager, payload, change)
        case _:
            raise NotEditable(f"approval {approval.id} ({approval.action}) cannot take that edit")
    try:
        transition_from_pending(session, approval, SUPERSEDED)
    except NotPending:
        transition_from_pending(session, fresh, SUPERSEDED)
        raise
    return fresh
