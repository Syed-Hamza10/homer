from datetime import timedelta
from types import ModuleType
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from achilles_core.db.models import Approval, utcnow
from achilles_core.services import approvals

SEND = {
    "approval_required": True,
    "action": "mail_send",
    "payload": {"draft_id": "d1"},
    "preview": "Send draft d1",
}


def make_approval(app: FastAPI, server: str = "google", **payload: Any) -> int:
    result = {**SEND, "payload": {**SEND["payload"], **payload}}
    with Session(app.state.engine) as session:
        return approvals.create_from_tool_result(session, 1, server, result).id


def row(app: FastAPI, approval_id: int) -> Approval:
    with Session(app.state.engine) as session:
        approval = session.get(Approval, approval_id)
        assert approval is not None
        return approval


def test_create_stores_hash_preview_and_channel(logged_in: TestClient, app: FastAPI) -> None:
    approval_id = make_approval(app)
    stored = row(app, approval_id)
    assert stored.status == "pending"
    assert stored.channel == "web"
    assert stored.payload_hash == approvals.payload_hash({"draft_id": "d1"})
    listed = logged_in.get("/api/approvals?status=pending").json()
    assert [(a["id"], a["action"], a["preview"], a["payload"]) for a in listed] == [
        (approval_id, "mail_send", "Send draft d1", {"draft_id": "d1"})
    ]


def test_approve_runs_execute_and_marks_done(
    logged_in: TestClient, app: FastAPI, fake_google: ModuleType, origin: dict[str, str]
) -> None:
    approval_id = make_approval(app)
    response = logged_in.post(f"/api/approvals/{approval_id}/approve", headers=origin)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "done"
    assert body["result"] == {"ok": True, "action": "mail_send", "payload": {"draft_id": "d1"}}
    assert body["decided_at"] is not None
    assert fake_google.executed == [{"action": "mail_send", "payload": {"draft_id": "d1"}}]
    assert logged_in.get("/api/approvals").json() == []


def test_second_approve_is_409(
    logged_in: TestClient, app: FastAPI, fake_google: ModuleType, origin: dict[str, str]
) -> None:
    approval_id = make_approval(app)
    assert (
        logged_in.post(f"/api/approvals/{approval_id}/approve", headers=origin).status_code == 200
    )
    second = logged_in.post(f"/api/approvals/{approval_id}/approve", headers=origin)
    assert second.status_code == 409
    assert "not pending" in second.json()["detail"]
    assert len(fake_google.executed) == 1


def test_reject_then_approve_is_409(
    logged_in: TestClient, app: FastAPI, fake_google: ModuleType, origin: dict[str, str]
) -> None:
    approval_id = make_approval(app)
    rejected = logged_in.post(f"/api/approvals/{approval_id}/reject", headers=origin)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert (
        logged_in.post(f"/api/approvals/{approval_id}/approve", headers=origin).status_code == 409
    )
    assert fake_google.executed == []


def test_edited_payload_fails_hash_check(
    logged_in: TestClient, app: FastAPI, fake_google: ModuleType, origin: dict[str, str]
) -> None:
    approval_id = make_approval(app)
    with Session(app.state.engine) as session:
        approval = session.get(Approval, approval_id)
        assert approval is not None
        approval.payload_json = '{"draft_id": "d2"}'
        session.add(approval)
        session.commit()
    body = logged_in.post(f"/api/approvals/{approval_id}/approve", headers=origin).json()
    assert body["status"] == "failed"
    assert body["result"] == {"error": "payload hash mismatch"}
    assert fake_google.executed == []


def test_stale_approvals_expire(
    logged_in: TestClient, app: FastAPI, origin: dict[str, str]
) -> None:
    approval_id = make_approval(app)
    with Session(app.state.engine) as session:
        approval = session.get(Approval, approval_id)
        assert approval is not None
        approval.created_at = utcnow() - approvals.APPROVAL_TTL - timedelta(minutes=1)
        session.add(approval)
        session.commit()
    assert logged_in.get("/api/approvals").json() == []
    assert row(app, approval_id).status == "expired"
    assert (
        logged_in.post(f"/api/approvals/{approval_id}/approve", headers=origin).status_code == 409
    )


def test_clear_server_failure_marks_failed(
    logged_in: TestClient, app: FastAPI, fake_google: ModuleType, origin: dict[str, str]
) -> None:
    approval_id = make_approval(app, fail="no such draft")
    body = logged_in.post(f"/api/approvals/{approval_id}/approve", headers=origin).json()
    assert body["status"] == "failed"
    assert "no such draft" in body["result"]["error"]
    assert fake_google.executed == []


def test_timeout_marks_unknown(
    logged_in: TestClient, app: FastAPI, origin: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "EXECUTE_TIMEOUT", 0.05)
    approval_id = make_approval(app, hang=2)
    body = logged_in.post(f"/api/approvals/{approval_id}/approve", headers=origin).json()
    assert body["status"] == "unknown"
    assert "may or may not" in body["result"]["error"]


def test_missing_server_marks_failed(
    logged_in: TestClient, app: FastAPI, origin: dict[str, str]
) -> None:
    approval_id = make_approval(app, server="search")
    body = logged_in.post(f"/api/approvals/{approval_id}/approve", headers=origin).json()
    assert body["status"] == "failed"
    assert "not running" in body["result"]["error"]


def test_unknown_approval_is_404(logged_in: TestClient, origin: dict[str, str]) -> None:
    assert logged_in.post("/api/approvals/99/approve", headers=origin).status_code == 404
    assert logged_in.post("/api/approvals/99/reject", headers=origin).status_code == 404


def test_approvals_require_login(client: TestClient, origin: dict[str, str]) -> None:
    assert client.get("/api/approvals").status_code == 401
    assert client.post("/api/approvals/1/approve", headers=origin).status_code == 401
