import asyncio
import hashlib
import json
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import update
from sqlmodel import Session, col, select

from homer_core.db.models import Approval, User, utcnow
from homer_core.mcp.manager import EXECUTOR_TOOL, ExecuteFailed, McpManager, ServerUnavailable
from homer_core.services.errors import DomainError, NotFound

log = structlog.get_logger(__name__)

APPROVAL_TTL = timedelta(hours=24)
EXECUTE_TIMEOUT = 60.0
CHANNEL_WEB = "web"
SEND_ACTION = "mail_send"
DRAFT_DELETE_TOOL = "mail_draft_delete"
SUPERSEDED = "superseded"


class NotPending(DomainError):
    status_code = 409


def is_approval_object(result: Any) -> bool:
    return isinstance(result, dict) and result.get("approval_required") is True


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def create(
    session: Session,
    user_id: int,
    server: str,
    action: str,
    payload: dict[str, Any],
    preview: str,
) -> Approval:
    approval = Approval(
        user_id=user_id,
        server=server,
        action=action,
        payload_json=json.dumps(payload),
        payload_hash=payload_hash(payload),
        preview=preview,
        channel=CHANNEL_WEB,
    )
    session.add(approval)
    session.commit()
    session.refresh(approval)
    return approval


def create_from_tool_result(
    session: Session, user_id: int, server: str, result: dict[str, Any]
) -> Approval:
    return create(session, user_id, server, result["action"], result["payload"], result["preview"])


def get_approval(session: Session, user: User, approval_id: int) -> Approval:
    approval = session.get(Approval, approval_id)
    if approval is None or approval.user_id != user.id:
        raise NotFound(f"approval {approval_id} not found")
    return approval


def expire_stale(session: Session) -> int:
    now = utcnow()
    statement = (
        update(Approval)
        .where(Approval.status == "pending", Approval.created_at < now - APPROVAL_TTL)
        .values(status="expired", decided_at=now)
    )
    count = session.exec(statement).rowcount
    session.commit()
    return count


def list_pending(
    session: Session, user: User, conversation_id: int | None = None
) -> list[Approval]:
    """Every pending approval of the user, or only those of one conversation when given."""
    expire_stale(session)
    statement = (
        select(Approval)
        .where(Approval.user_id == user.id, Approval.status == "pending")
        .order_by(Approval.id)
    )
    if conversation_id is not None:
        statement = statement.where(Approval.conversation_id == conversation_id)
    return list(session.exec(statement))


def list_for_conversation(session: Session, user: User, conversation_id: int) -> list[Approval]:
    """The live and decided approvals of one conversation; superseded edits are left out."""
    expire_stale(session)
    statement = (
        select(Approval)
        .where(
            Approval.user_id == user.id,
            Approval.conversation_id == conversation_id,
            Approval.status != SUPERSEDED,
        )
        .order_by(Approval.id)
    )
    return list(session.exec(statement))


def attach(session: Session, approval_ids: list[int], message_id: int) -> None:
    """Shows these approvals under the assistant message that offered them."""
    if not approval_ids:
        return
    session.exec(
        update(Approval).where(col(Approval.id).in_(approval_ids)).values(message_id=message_id)
    )
    session.commit()


def latest_send(
    session: Session, user: User, conversation_id: int | None, recipient: str | None
) -> Approval | None:
    """The newest live email approval to the recipient, or in the conversation without one."""
    expire_stale(session)
    statement = (
        select(Approval)
        .where(
            Approval.user_id == user.id,
            Approval.action == SEND_ACTION,
            Approval.status != SUPERSEDED,
        )
        .order_by(Approval.id.desc())
    )
    if recipient is None:
        statement = statement.where(Approval.conversation_id == conversation_id)
    for approval in session.exec(statement):
        if recipient is None or recipient in json.loads(approval.payload_json).get("to", ""):
            return approval
    return None


def transition_from_pending(session: Session, approval: Approval, status: str) -> None:
    """Moves pending -> status in one conditional UPDATE; raises NotPending if someone else won."""
    expire_stale(session)
    statement = (
        update(Approval)
        .where(Approval.id == approval.id, Approval.status == "pending")
        .values(status=status, decided_at=utcnow())
    )
    updated = session.exec(statement).rowcount
    session.commit()
    session.refresh(approval)
    if updated == 0:
        raise NotPending(f"approval {approval.id} is {approval.status}, not pending")


def finish(session: Session, approval: Approval, status: str, result: Any) -> Approval:
    approval.status = status
    approval.result_json = json.dumps(result)
    session.add(approval)
    session.commit()
    session.refresh(approval)
    return approval


async def execute(manager: McpManager, approval: Approval) -> tuple[str, Any]:
    args = {"action": approval.action, "payload": json.loads(approval.payload_json)}
    try:
        result = await asyncio.wait_for(
            manager.call(approval.server, EXECUTOR_TOOL, args), EXECUTE_TIMEOUT
        )
        failed = isinstance(result, dict) and "error" in result
        return ("failed" if failed else "done"), result
    except (ExecuteFailed, ServerUnavailable) as error:
        return "failed", {"error": str(error)}
    except TimeoutError:
        return "unknown", {"error": "timed out; the action may or may not have run"}
    except Exception as error:
        log.exception("execute_ambiguous", approval_id=approval.id)
        return "unknown", {"error": f"{type(error).__name__}; the action may or may not have run"}


async def approve(session: Session, user: User, approval_id: int, manager: McpManager) -> Approval:
    approval = get_approval(session, user, approval_id)
    transition_from_pending(session, approval, "running")
    if payload_hash(json.loads(approval.payload_json)) != approval.payload_hash:
        return finish(session, approval, "failed", {"error": "payload hash mismatch"})
    status, result = await execute(manager, approval)
    return finish(session, approval, status, result)


def reject(session: Session, user: User, approval_id: int) -> Approval:
    approval = get_approval(session, user, approval_id)
    transition_from_pending(session, approval, "rejected")
    return approval


async def discard(session: Session, user: User, approval_id: int, manager: McpManager) -> Approval:
    """Rejects the approval and deletes the Gmail draft a rejected send leaves behind."""
    approval = reject(session, user, approval_id)
    draft_id = json.loads(approval.payload_json).get("draft_id")
    if approval.action == SEND_ACTION and draft_id:
        try:
            await manager.call(approval.server, DRAFT_DELETE_TOOL, {"draft_id": draft_id})
        except (ExecuteFailed, ServerUnavailable):
            log.warning("draft_delete_failed", approval_id=approval.id, draft_id=draft_id)
    return approval
