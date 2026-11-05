import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlmodel import Session, select

from homer_core.agent.intents import OUTPUT_TOOL as INTENT_TOOL
from homer_core.config import Settings
from homer_core.db.models import Message, TokenCounter, User
from homer_core.services import chat

PostChat = Callable[[dict[str, Any]], list[tuple[str, dict[str, Any]]]]
JobModel = Callable[..., Model]


def test_sse_order_and_persistence(
    logged_in: TestClient, app: FastAPI, post_chat: PostChat
) -> None:
    frames = post_chat({"message": "Hi there"})
    names = [name for name, _ in frames]
    assert names[0] == "meta"
    assert names[-1] == "done"
    assert set(names[1:-1]) == {"token"}
    meta = frames[0][1]
    assert set(meta) == {"conversation_id", "message_id"}
    assert "".join(data["text"] for name, data in frames if name == "token") == (
        "Hello from the test model."
    )
    done = frames[-1][1]
    assert done["input_tokens"] > 0 and done["output_tokens"] > 0

    with Session(app.state.engine) as session:
        messages = list(session.exec(select(Message).order_by(Message.id)))
        assert [(m.role, m.content) for m in messages] == [
            ("user", "Hi there"),
            ("assistant", "Hello from the test model."),
        ]
        assert messages[0].conversation_id == meta["conversation_id"]
        counter = session.get(TokenCounter, 1)
        assert counter is not None
        assert (counter.input_tokens, counter.output_tokens, counter.requests) == (
            done["input_tokens"],
            done["output_tokens"],
            1,
        )


def test_title_is_first_sixty_characters(logged_in: TestClient, post_chat: PostChat) -> None:
    long_message = "x" * 100
    conversation_id = post_chat({"message": long_message})[0][1]["conversation_id"]
    conversations = logged_in.get("/api/conversations").json()
    assert conversations[0]["id"] == conversation_id
    assert conversations[0]["title"] == "x" * 60


def test_unknown_conversation_is_404(logged_in: TestClient, origin: dict[str, str]) -> None:
    response = logged_in.post(
        "/api/chat", json={"conversation_id": 99, "message": "x"}, headers=origin
    )
    assert response.status_code == 404


def test_chat_requires_login(client: TestClient, origin: dict[str, str]) -> None:
    assert client.post("/api/chat", json={"message": "x"}, headers=origin).status_code == 401


class TestHistory:
    @pytest.fixture
    def seen(self) -> list[list[ModelMessage]]:
        return []

    @pytest.fixture
    def model(self, jobs: JobModel, seen: list[list[ModelMessage]]) -> Model:
        return jobs([], text="ok", seen=seen)

    def test_second_message_carries_history(
        self, logged_in: TestClient, post_chat: PostChat, seen: list[list[ModelMessage]]
    ) -> None:
        conversation_id = post_chat({"message": "first"})[0][1]["conversation_id"]
        frames = post_chat({"conversation_id": conversation_id, "message": "second"})
        assert frames[0][1]["conversation_id"] == conversation_id
        assert frames[-1][0] == "done"

        texts = [part.content for message in seen[-1] for part in message.parts]
        assert [text for text in texts if text in ("first", "ok", "second")] == [
            "first",
            "ok",
            "second",
        ]
        rows = logged_in.get(f"/api/conversations/{conversation_id}/messages").json()
        assert [m["content"] for m in rows] == ["first", "ok", "second", "ok"]


class TestPlaceholderName:
    @pytest.fixture
    def seen(self) -> list[list[ModelMessage]]:
        return []

    @pytest.fixture
    def settings(self, settings: Settings) -> Settings:
        return settings.model_copy(update={"user_name": "there"})

    @pytest.fixture
    def model(self, jobs: JobModel, seen: list[list[ModelMessage]]) -> Model:
        return jobs([], text="Nice to meet you, Omar.", seen=seen)

    def test_the_prompt_never_names_the_user_there(
        self, logged_in: TestClient, post_chat: PostChat, seen: list[list[ModelMessage]]
    ) -> None:
        post_chat({"message": "Hello, I'm Omar"})
        instructions = [
            message.instructions
            for message in seen[-1]
            if isinstance(message, ModelRequest) and message.instructions
        ]
        assert instructions and "name is" not in instructions[0]


class TestModelFailure:
    @pytest.fixture
    def model(self) -> Model:
        def chat(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[ToolCallPart(INTENT_TOOL, {"intents": [{"kind": "chat"}]})])

        async def explode(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
            raise RuntimeError("secret internal detail")
            yield ""

        return FunctionModel(function=chat, stream_function=explode)

    def test_model_failure_yields_generic_error_event(
        self, logged_in: TestClient, app: FastAPI, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "boom"})
        assert [name for name, _ in frames] == ["meta", "error"]
        assert "secret" not in frames[1][1]["message"]
        with Session(app.state.engine) as session:
            roles = [m.role for m in session.exec(select(Message))]
        assert roles == ["user"]


class TestStop:
    @pytest.fixture
    def cancelled(self) -> list[bool]:
        return []

    @pytest.fixture
    def model(self, cancelled: list[bool]) -> Model:
        def chat_intent(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[ToolCallPart(INTENT_TOOL, {"intents": [{"kind": "chat"}]})])

        async def hang(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
            yield "Half an ans"
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

        return FunctionModel(function=chat_intent, stream_function=hang)

    @staticmethod
    def saved(app: FastAPI) -> list[tuple[str, str, bool]]:
        with Session(app.state.engine) as session:
            rows = session.exec(select(Message).order_by(Message.id))
            return [(m.role, m.content, m.stopped) for m in rows]

    async def test_cancelled_run_saves_the_partial_answer_as_stopped(
        self, logged_in: TestClient, app: FastAPI, cancelled: list[bool]
    ) -> None:
        first_token = asyncio.Event()
        with Session(app.state.engine) as session:
            user = session.get(User, 1)
            assert user is not None
            events = chat.stream(session, user, app.state.runtime, None, "Tell me a story")

            async def consume() -> None:
                async for event in events:
                    if event.name == "token":
                        first_token.set()

            task = asyncio.create_task(consume())
            await first_token.wait()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            await asyncio.sleep(0.05)

        assert self.saved(app) == [
            ("user", "Tell me a story", False),
            ("assistant", "Half an ans", True),
        ]
        assert cancelled == [True]

    async def test_closed_stream_saves_the_partial_answer_as_stopped(
        self, logged_in: TestClient, app: FastAPI, cancelled: list[bool]
    ) -> None:
        with Session(app.state.engine) as session:
            user = session.get(User, 1)
            assert user is not None
            events = chat.stream(session, user, app.state.runtime, None, "Tell me a story")
            while (await anext(events)).name != "token":
                pass
            await events.aclose()
            await asyncio.sleep(0.05)

        assert self.saved(app)[-1] == ("assistant", "Half an ans", True)
        assert cancelled == [True]
