from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from homer_core.db.models import Approval, Conversation, Message

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
    assert set(messages[0]) == {
        "id",
        "conversation_id",
        "role",
        "content",
        "stopped",
        "created_approval",
        "created_at",
    }


def test_unknown_conversation_messages_are_404(logged_in: TestClient) -> None:
    response = logged_in.get("/api/conversations/42/messages")
    assert response.status_code == 404
    assert response.json() == {"detail": "conversation 42 not found"}


def test_title_is_the_first_six_words(logged_in: TestClient, post_chat: PostChat) -> None:
    post_chat({"message": "  What is   on my calendar for tomorrow morning please"})
    assert logged_in.get("/api/conversations").json()[0]["title"] == ("What is on my calendar for")


def test_rename(logged_in: TestClient, post_chat: PostChat, origin: dict[str, str]) -> None:
    conversation_id = post_chat({"message": "one"})[0][1]["conversation_id"]
    response = logged_in.patch(
        f"/api/conversations/{conversation_id}", json={"title": "  Trip plans "}, headers=origin
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Trip plans"
    assert logged_in.get("/api/conversations").json()[0]["title"] == "Trip plans"


def test_rename_rejects_a_blank_title(
    logged_in: TestClient, post_chat: PostChat, origin: dict[str, str]
) -> None:
    conversation_id = post_chat({"message": "one"})[0][1]["conversation_id"]
    response = logged_in.patch(
        f"/api/conversations/{conversation_id}", json={"title": "   "}, headers=origin
    )
    assert response.status_code == 422


def test_rename_unknown_is_404(logged_in: TestClient, origin: dict[str, str]) -> None:
    response = logged_in.patch("/api/conversations/42", json={"title": "x"}, headers=origin)
    assert response.status_code == 404


def test_delete_removes_messages_and_keeps_approvals(
    logged_in: TestClient, app: FastAPI, post_chat: PostChat, origin: dict[str, str]
) -> None:
    kept = post_chat({"message": "keep"})[0][1]["conversation_id"]
    gone = post_chat({"message": "gone"})[0][1]["conversation_id"]
    with Session(app.state.engine) as session:
        session.add(
            Approval(
                user_id=1,
                server="google",
                action="mail_send",
                payload_json="{}",
                payload_hash="h",
                preview="p",
            )
        )
        session.commit()

    assert logged_in.delete(f"/api/conversations/{gone}", headers=origin).status_code == 204

    assert [c["id"] for c in logged_in.get("/api/conversations").json()] == [kept]
    with Session(app.state.engine) as session:
        assert session.get(Conversation, gone) is None
        left = session.exec(select(Message.conversation_id)).all()
        assert set(left) == {kept}
        assert len(session.exec(select(Approval)).all()) == 1
    assert logged_in.delete(f"/api/conversations/{gone}", headers=origin).status_code == 404


def test_regenerate_removes_the_last_exchange(
    logged_in: TestClient, post_chat: PostChat, origin: dict[str, str]
) -> None:
    conversation_id = post_chat({"message": "first"})[0][1]["conversation_id"]
    post_chat({"conversation_id": conversation_id, "message": "second"})

    response = logged_in.post(f"/api/conversations/{conversation_id}/regenerate", headers=origin)

    assert response.status_code == 200
    assert response.json() == {"message": "second"}
    rows = logged_in.get(f"/api/conversations/{conversation_id}/messages").json()
    assert [m["content"] for m in rows] == ["first", "Hello from the test model."]


def test_regenerate_refuses_a_reply_that_created_an_approval(
    logged_in: TestClient, app: FastAPI, post_chat: PostChat, origin: dict[str, str]
) -> None:
    conversation_id = post_chat({"message": "first"})[0][1]["conversation_id"]
    with Session(app.state.engine) as session:
        reply = session.exec(select(Message).where(Message.role == "assistant")).one()
        reply.created_approval = True
        session.add(reply)
        session.commit()

    response = logged_in.post(f"/api/conversations/{conversation_id}/regenerate", headers=origin)

    assert response.status_code == 409
    rows = logged_in.get(f"/api/conversations/{conversation_id}/messages").json()
    assert len(rows) == 2


def test_regenerate_unknown_is_404(logged_in: TestClient, origin: dict[str, str]) -> None:
    assert logged_in.post("/api/conversations/42/regenerate", headers=origin).status_code == 404
