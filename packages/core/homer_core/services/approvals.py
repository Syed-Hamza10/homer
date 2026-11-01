import asyncio
import hashlib
import json
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import update
from sqlmodel import Session, select

from homer_core.db.models import Approval, User, utcnow
from homer_core.mcp.manager import EXECUTOR_TOOL, ExecuteFailed, McpManager, ServerUnavailable
from homer_core.services.errors import DomainError, NotFound

log = structlog.get_logger(__name__)

APPROVAL_TTL = timedelta(hours=24)
EXECUTE_TIMEOUT = 60.0
CHANNEL_WEB = "web"


class NotPending(DomainError):
    status_code = 409


def is_approval_object(result: Any) -> bool:
    return isinstance(result, dict) and result.get("approval_required") is True


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_from_tool_result(
    session: Session, user_id: int, server: str, result: dict[str, Any]
) -> Approval:
    payload = result["payload"]
    approval = Approval(
        user_id=user_id,
        server=server,
        action=result["action"],
        payload_json=json.dumps(payload),
        payload_hash=payload_hash(payload),
        preview=result["preview"],
        channel=CHANNEL_WEB,
    )
    session.add(approval)
    session.commit()
    session.refresh(approval)
    return approval


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


def list_pending(session: Session, user: User) -> list[Approval]:
    expire_stale(session)
    statement = (
        select(Approval)
        .where(Approval.user_id == user.id, Approval.status == "pending")
        .order_by(Approval.id)
    )
    return list(session.exec(statement))


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
        return "done", result
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
