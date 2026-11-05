from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homer_core.mcp.manager import McpManager

KICKOFF_THREAD = "dbe626c57687283a"
PROPOSAL_THREAD = "5378fcbd5bd7dbed"
INVOICE_THREAD = "8273f4fcf6b11f03"
MAYA = "Maya Lindqvist <maya.lindqvist@example.test>"
WRITTEN = "Thursday at 14:00 works well for us."
prompts: list[str] = []


@pytest.fixture
def mcp(sim_mcp: McpManager) -> McpManager:
    return sim_mcp


@pytest.fixture
def model() -> Model:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompts.append(str(messages[-1].parts[-1].content))
        return ModelResponse(parts=[TextPart(content=WRITTEN)])

    return FunctionModel(function=respond, model_name="test")


def counts(sim: FastAPI) -> dict[str, int]:
    return sim.state.sim.counts()


def ids(client: TestClient, **params: Any) -> list[str]:
    page = client.get("/api/mail/threads", params=params)
    assert page.status_code == 200, page.text
    return [thread["id"] for thread in page.json()["threads"]]


def test_mail_routes_need_login(client: TestClient) -> None:
    assert client.get("/api/mail/folders").status_code == 401
    assert client.get("/api/mail/threads").status_code == 401


def test_folders_with_counts_labels_and_categories(logged_in: TestClient) -> None:
    folders = logged_in.get("/api/mail/folders").json()
    assert [(f["id"], f["kind"]) for f in folders] == [
        ("inbox", "folder"),
        ("starred", "folder"),
        ("sent", "folder"),
        ("drafts", "folder"),
        ("all", "folder"),
        ("Label_1", "category"),
        ("Label_3", "label"),
        ("Label_2", "category"),
    ]
    inbox = folders[0]
    assert inbox["name"] == "Inbox" and inbox["unread"] == 4 and inbox["total"] == 5
    assert folders[4]["unread"] == 0


def test_thread_list_pages_filters_and_searches(logged_in: TestClient) -> None:
    first = logged_in.get("/api/mail/threads", params={"size": 3}).json()
    assert len(first["threads"]) == 3 and first["next_page_token"] == "3"
    newest = first["threads"][0]
    assert newest["subject"] == "Quarterly review deck" and newest["unread"] is True
    assert newest["received_at"] and not newest["snippet"].startswith("<untrusted>")
    rest = logged_in.get("/api/mail/threads", params={"size": 3, "page_token": "3"}).json()
    assert len(rest["threads"]) == 2 and rest["next_page_token"] is None
    invoice = next(t for t in first["threads"] + rest["threads"] if t["id"] == INVOICE_THREAD)
    assert invoice["has_attachment"] is True and invoice["sender"].startswith("Tomas")
    assert ids(logged_in, folder="starred") == []
    assert ids(logged_in, folder="Label_3") == ["62d7eea155313e9f"]
    assert ids(logged_in, folder="all", q="from:maya") == [KICKOFF_THREAD]
    assert len(ids(logged_in, folder="sent")) == 3


def test_html_body_is_sanitised_and_remote_images_blocked(logged_in: TestClient) -> None:
    thread = logged_in.get(f"/api/mail/threads/{PROPOSAL_THREAD}").json()
    assert thread["subject"] == "Partnership proposal"
    proposal = thread["messages"][0]
    html = proposal["body_html"]
    assert "Proposal" in html and "our work" in html
    for unsafe in ("<script", "alert(", "onerror", "javascript:", "<style", "tracker.example"):
        assert unsafe not in html
    assert proposal["remote_images"] == 1
    assert 'href="https://agency.example.test/work"' in html
    assert 'target="_blank"' in html and "noopener" in html
    shown = logged_in.get(f"/api/mail/threads/{PROPOSAL_THREAD}", params={"images": True}).json()
    shown_html = shown["messages"][0]["body_html"]
    assert 'src="https://tracker.example.test/pixel.gif"' in shown_html
    assert "onerror" not in shown_html and "javascript:" not in shown_html
    reply = thread["messages"][1]
    assert reply["body_html"] is None and reply["body_text"]


def test_thread_shows_recipients_and_attachments(logged_in: TestClient) -> None:
    thread = logged_in.get(f"/api/mail/threads/{INVOICE_THREAD}").json()
    first = thread["messages"][0]
    assert first["to"] == "jordan.reyes@example.test" and first["date"]
    assert first["attachments"] == [
        {"filename": "invoice-2026-041.pdf", "mime_type": "application/pdf", "size": 48213}
    ]
    assert "invoice 2026-041" in first["body_text"]


def test_archive_star_and_read_act_straight_away(
    logged_in: TestClient, origin: dict[str, str]
) -> None:
    logged_in.post("/api/inbox/refresh", headers=origin)
    assert any(row["thread_id"] == KICKOFF_THREAD for row in logged_in.get("/api/inbox").json())
    starred = logged_in.post(
        f"/api/mail/threads/{KICKOFF_THREAD}/labels",
        json={"add": ["STARRED"], "remove": ["UNREAD"]},
        headers=origin,
    ).json()
    assert "STARRED" in starred["labels"] and "UNREAD" not in starred["labels"]
    assert ids(logged_in, folder="starred") == [KICKOFF_THREAD]
    assert logged_in.get("/api/mail/folders").json()[0]["unread"] == 3
    logged_in.post(
        f"/api/mail/threads/{KICKOFF_THREAD}/labels", json={"remove": ["INBOX"]}, headers=origin
    )
    assert KICKOFF_THREAD not in ids(logged_in)
    assert all(row["thread_id"] != KICKOFF_THREAD for row in logged_in.get("/api/inbox").json())
    logged_in.post(
        f"/api/mail/threads/{KICKOFF_THREAD}/labels", json={"add": ["Follow up"]}, headers=origin
    )
    assert KICKOFF_THREAD in ids(logged_in, folder="Label_3")


def test_reply_reply_all_and_forward_drafts(logged_in: TestClient) -> None:
    reply = logged_in.get(f"/api/mail/threads/{KICKOFF_THREAD}/reply").json()
    assert reply["to"] == MAYA and reply["thread_id"] == KICKOFF_THREAD
    assert reply["subject"] == "Re: Kickoff for the Northwind website redesign"
    assert "Maya Lindqvist" in reply["body"] and "\n> " in reply["body"]
    own = logged_in.get(f"/api/mail/threads/{PROPOSAL_THREAD}/reply").json()
    assert own["to"] == "Samuel Okafor <samuel.okafor@example.test>"
    everyone = logged_in.get(
        f"/api/mail/threads/{KICKOFF_THREAD}/reply", params={"mode": "reply_all"}
    ).json()
    assert everyone["to"] == MAYA
    forward = logged_in.get(
        f"/api/mail/threads/{INVOICE_THREAD}/reply", params={"mode": "forward"}
    ).json()
    assert forward["to"] == "" and forward["thread_id"] is None
    assert forward["subject"].startswith("Fwd: ") and "Forwarded message" in forward["body"]


def test_send_makes_a_draft_and_an_approval_but_sends_nothing(
    logged_in: TestClient, origin: dict[str, str], sim: FastAPI
) -> None:
    before = counts(sim)
    body = {
        "to": "maya.lindqvist@example.test, tomas.keller@example.test",
        "subject": "Re: Kickoff for the Northwind website redesign",
        "body": "Thursday works.",
        "thread_id": KICKOFF_THREAD,
    }
    approval = logged_in.post("/api/mail/compose", json=body, headers=origin).json()
    assert approval["action"] == "mail_send" and approval["status"] == "pending"
    assert approval["payload"]["thread_id"] == KICKOFF_THREAD
    assert approval["payload"]["draft_id"].startswith("r-")
    assert counts(sim)["drafts"] == before["drafts"] + 1
    assert counts(sim)["sent"] == before["sent"]
    done = logged_in.post(f"/api/approvals/{approval['id']}/approve", headers=origin).json()
    assert done["status"] == "done"
    assert counts(sim)["sent"] == before["sent"] + 1


def test_compose_rejects_bad_addresses(logged_in: TestClient, origin: dict[str, str]) -> None:
    body = {"to": "maya, nobody", "subject": "Hi", "body": "Hello"}
    assert logged_in.post("/api/mail/compose", json=body, headers=origin).status_code == 422


def test_draft_with_homer_sends_the_thread_and_instruction(
    logged_in: TestClient, origin: dict[str, str], sim: FastAPI
) -> None:
    prompts.clear()
    before = counts(sim)
    body = {"instruction": "say Thursday works", "thread_id": KICKOFF_THREAD}
    written = logged_in.post("/api/mail/write", json=body, headers=origin).json()
    assert written == {"body": WRITTEN}
    assert "say Thursday works" in prompts[0] and "<untrusted>" in prompts[0]
    assert "kickoff slots" in prompts[0]
    assert counts(sim) == before


def test_google_errors_become_502(logged_in: TestClient, tmp_path: Any) -> None:
    (tmp_path / "google" / "credentials" / "google_token.json").unlink()
    response = logged_in.get("/api/mail/folders")
    assert response.status_code == 502
    assert response.json()["detail"] == "google_reconnect_required"
