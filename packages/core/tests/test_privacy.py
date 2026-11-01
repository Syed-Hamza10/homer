from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from homer_core.db.models import OutboundLog
from homer_core.privacy_hosts import CORE_HOSTS, GOOGLE_HOSTS, SEARCH_HOSTS, privacy_markdown
from homer_core.services import approvals
from homer_mcp_google.settings import GOOGLE_API_BASE, GOOGLE_TOKEN_URL
from homer_mcp_search.search import SEARCH_HOST
from homer_net.allowlist import host_key

PostChat = Callable[[dict[str, Any]], list[tuple[str, dict[str, Any]]]]


def test_hosts_are_grouped_with_counts(logged_in: TestClient, app: FastAPI) -> None:
    with Session(app.state.engine) as session:
        for host in ("127.0.0.1:11434", "www.googleapis.com", "127.0.0.1:11434"):
            session.add(OutboundLog(method="GET", host=host, path="/", status=200, duration_ms=1))
        session.commit()
    body = logged_in.get("/api/privacy/hosts").json()
    assert body["web_search"] is True
    assert body["web_search_configured"] is True
    assert [(h["host"], h["calls"]) for h in body["hosts"]] == [
        ("127.0.0.1:11434", 2),
        ("www.googleapis.com", 1),
    ]
    assert body["hosts"][0]["last_seen"]


def test_usage_counts_tokens_and_spends_nothing(logged_in: TestClient, post_chat: PostChat) -> None:
    assert logged_in.get("/api/privacy/usage").json() == {
        "input_tokens": 0,
        "output_tokens": 0,
        "requests": 0,
        "spent_usd": 0,
    }
    post_chat({"message": "Hi"})
    body = logged_in.get("/api/privacy/usage").json()
    assert body["input_tokens"] > 0 and body["output_tokens"] > 0
    assert body["requests"] == 1
    assert body["spent_usd"] == 0


def test_web_search_toggle_needs_a_restart(logged_in: TestClient, origin: dict[str, str]) -> None:
    off = logged_in.put("/api/privacy/web-search", json={"enabled": False}, headers=origin)
    assert off.json() == {"enabled": False, "restart_required": True}
    hosts = logged_in.get("/api/privacy/hosts").json()
    assert hosts["web_search"] is True
    assert hosts["web_search_configured"] is False

    on = logged_in.put("/api/privacy/web-search", json={"enabled": True}, headers=origin)
    assert on.json() == {"enabled": True, "restart_required": False}


def test_wipe_clears_local_data(
    logged_in: TestClient, app: FastAPI, origin: dict[str, str], post_chat: PostChat
) -> None:
    post_chat({"message": "Hi"})
    with Session(app.state.engine) as session:
        session.add(
            OutboundLog(method="GET", host="127.0.0.1:11434", path="/", status=200, duration_ms=1)
        )
        approvals.create_from_tool_result(
            session,
            1,
            "google",
            {
                "approval_required": True,
                "action": "mail_send",
                "payload": {"draft_id": "d1"},
                "preview": "Send draft d1",
            },
        )
    assert logged_in.get("/api/conversations").json()

    response = logged_in.post("/api/privacy/wipe", json={"confirm": True}, headers=origin)
    assert response.status_code == 200
    deleted = response.json()["deleted"]
    assert deleted["conversations"] == 1
    assert deleted["messages"] == 2
    assert deleted["outbound_log"] == 1
    assert deleted["approvals"] == 1

    assert logged_in.get("/api/conversations").json() == []
    assert logged_in.get("/api/approvals").json() == []
    assert logged_in.get("/api/privacy/hosts").json()["hosts"] == []
    assert logged_in.get("/api/privacy/usage").json()["requests"] == 0


def test_wipe_requires_confirmation(logged_in: TestClient, origin: dict[str, str]) -> None:
    response = logged_in.post("/api/privacy/wipe", json={"confirm": False}, headers=origin)
    assert response.status_code == 400


def test_privacy_hosts_match_the_server_defaults() -> None:
    assert host_key(GOOGLE_API_BASE) == GOOGLE_HOSTS[0]
    assert host_key(GOOGLE_TOKEN_URL) == GOOGLE_HOSTS[1]
    assert SEARCH_HOSTS[0] == SEARCH_HOST
    text = privacy_markdown()
    for host in (*CORE_HOSTS, *GOOGLE_HOSTS, *SEARCH_HOSTS):
        assert host in text


def test_privacy_requires_login(client: TestClient) -> None:
    assert client.get("/api/privacy/hosts").status_code == 401
    assert client.get("/api/privacy/usage").status_code == 401
