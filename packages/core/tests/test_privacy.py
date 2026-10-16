from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from achilles_core.db.models import OutboundLog

PostChat = Callable[[dict[str, Any]], list[tuple[str, dict[str, Any]]]]


def test_hosts_are_grouped_with_counts(logged_in: TestClient, app: FastAPI) -> None:
    with Session(app.state.engine) as session:
        for host in ("127.0.0.1:11434", "www.googleapis.com", "127.0.0.1:11434"):
            session.add(OutboundLog(method="GET", host=host, path="/", status=200, duration_ms=1))
        session.commit()
    body = logged_in.get("/api/privacy/hosts").json()
    assert body["web_search"] is True
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


def test_privacy_requires_login(client: TestClient) -> None:
    assert client.get("/api/privacy/hosts").status_code == 401
    assert client.get("/api/privacy/usage").status_code == 401
