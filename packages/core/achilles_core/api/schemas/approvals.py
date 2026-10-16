import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from achilles_core.db.models import Approval


class ApprovalOut(BaseModel):
    id: int
    server: str
    action: str
    payload: dict[str, Any]
    preview: str
    status: str
    channel: str
    created_at: datetime
    decided_at: datetime | None
    result: Any | None

    @classmethod
    def from_row(cls, approval: Approval) -> "ApprovalOut":
        return cls(
            id=approval.id,
            server=approval.server,
            action=approval.action,
            payload=json.loads(approval.payload_json),
            preview=approval.preview,
            status=approval.status,
            channel=approval.channel,
            created_at=approval.created_at,
            decided_at=approval.decided_at,
            result=json.loads(approval.result_json) if approval.result_json else None,
        )
