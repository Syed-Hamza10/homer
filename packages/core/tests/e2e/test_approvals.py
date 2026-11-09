from collections.abc import Callable
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e
Frames = list[tuple[str, dict[str, Any]]]
Chat = Callable[[dict[str, Any]], Frames]
SEND_PROMPT = "Email ada@example.test and tell her invoice 42 is paid."


def of(frames: Frames, name: str) -> list[dict[str, Any]]:
    return [data for event, data in frames if event == name]


def token_text(frames: Frames) -> str:
    return "".join(data["text"] for data in of(frames, "token"))


def test_live_model_send_becomes_an_approval(logged_in: httpx.Client, chat: Chat) -> None:
    frames = chat({"message": SEND_PROMPT})
    assert frames[-1][0] == "done", frames
    requested = of(frames, "approval_required")
    assert requested, token_text(frames)
    assert [c["name"] for c in of(frames, "tool_call")] == ["mail_draft"]
    assert requested[0]["action"] == "mail_send"
    assert requested[0]["payload"]["to"] == "ada@example.test"
    assert (
        token_text(frames)
        == "Here's your email to ada@example.test. Press Send when it looks right."
    )

    approval_id = requested[0]["approval_id"]
    approved = logged_in.post(f"/api/approvals/{approval_id}/approve").json()
    assert approved["status"] == "done"
    assert approved["result"]["payload"]["draft_id"] == requested[0]["payload"]["draft_id"]


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
    assert "Good morning" in token_text(chat({"message": "/brief"}))
    approval_id = create_approval("d-cmd")
    frames = chat({"message": f"/approve {approval_id}"})
    assert token_text(frames) == f"Approval #{approval_id} (mail_send): done."
    assert frames[-1][0] == "done"
