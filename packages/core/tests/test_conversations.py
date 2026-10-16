from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

PostChat = Callable[[dict[str, Any]], list[tuple[str, dict[str, Any]]]]


def test_list_is_empty_at_first(logged_in: TestClient) -> None:
    assert logged_in.get("/api/conversations").json() == []


def test_conversations_and_messages_are_listed(logged_in: TestClient, post_chat: PostChat) -> None:
    first = post_chat({"message": "one"})[0][1]["conversation_id"]
    second = post_chat({"message": "two"})[0][1]["conversation_id"]

    conversations = logged_in.get("/api/conversations").json()
    assert [c["id"] for c in conversations] == [second, first]
    assert set(conversations[0]) == {"id", "title", "created_at", "updated_at"}

    messages = logged_in.get(f"/api/conversations/{first}/messages").json()
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "one"),
        ("assistant", "Hello from the test model."),
    ]
    assert set(messages[0]) == {"id", "conversation_id", "role", "content", "created_at"}


def test_unknown_conversation_messages_are_404(logged_in: TestClient) -> None:
    response = logged_in.get("/api/conversations/42/messages")
    assert response.status_code == 404
    assert response.json() == {"detail": "conversation 42 not found"}
