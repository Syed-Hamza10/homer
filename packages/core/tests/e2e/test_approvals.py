from collections.abc import Callable
from typing import Any

import httpx
import pytest

from achilles_core.services.chat import NOT_YET_AVAILABLE

pytestmark = pytest.mark.e2e
Frames = list[tuple[str, dict[str, Any]]]
Chat = Callable[[dict[str, Any]], Frames]
SEND_PROMPT = "Send the draft with id d1 now."


def of(frames: Frames, name: str) -> list[dict[str, Any]]:
    return [data for event, data in frames if event == name]


def token_text(frames: Frames) -> str:
    return "".join(data["text"] for data in of(frames, "token"))


def test_model_driven_send_needs_approval(logged_in: httpx.Client, chat: Chat) -> None:
    frames = chat({"message": SEND_PROMPT})
    assert frames[-1][0] == "done", frames
    requested = of(frames, "approval_required")
    if not requested:
        pytest.skip(f"model answered in text instead of calling mail_send: {token_text(frames)!r}")
    assert [c["name"] for c in of(frames, "tool_call")] == ["mail_send"]
    assert requested[0]["action"] == "mail_send"
    assert "d1" in requested[0]["preview"]
    assert any("Approval #" in r["summary"] for r in of(frames, "tool_result"))

    approval_id = requested[0]["approval_id"]
    pending = logged_in.get("/api/approvals").json()
    assert approval_id in [a["id"] for a in pending]
    approved = logged_in.post(f"/api/approvals/{approval_id}/approve").json()
    assert approved["status"] == "done"
    assert approved["result"] == {
        "ok": True,
        "action": "mail_send",
        "payload": {"draft_id": "d1"},
    }


def test_approval_round_trip_over_http(
    logged_in: httpx.Client, create_approval: Callable[[str], int]
) -> None:
    approval_id = create_approval("d-http")
    pending = logged_in.get("/api/approvals").json()
    assert [a["preview"] for a in pending if a["id"] == approval_id] == ["Send draft d-http"]

    approved = logged_in.post(f"/api/approvals/{approval_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "done"
    assert approved.json()["result"]["payload"] == {"draft_id": "d-http"}
    assert logged_in.post(f"/api/approvals/{approval_id}/approve").status_code == 409

    rejected_id = create_approval("d-no")
    rejected = logged_in.post(f"/api/approvals/{rejected_id}/reject")
    assert rejected.json()["status"] == "rejected"
    assert logged_in.post(f"/api/approvals/{rejected_id}/approve").status_code == 409


def test_slash_commands(chat: Chat, create_approval: Callable[[str], int]) -> None:
    assert token_text(chat({"message": "/brief"})) == NOT_YET_AVAILABLE
    approval_id = create_approval("d-cmd")
    frames = chat({"message": f"/approve {approval_id}"})
    assert token_text(frames) == f"Approval #{approval_id} (mail_send): done."
    assert frames[-1][0] == "done"
