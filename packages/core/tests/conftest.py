import importlib.util
import json
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp.client import Client
from pydantic import SecretStr
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homer_core.agent.intents import OUTPUT_TOOL as INTENT_TOOL
from homer_core.config import Settings
from homer_core.main import create_app
from homer_core.mcp.manager import McpManager

FAKE_SERVERS = Path(__file__).parent / "fake_servers"

PASSPHRASE = "test-pass"
ORIGIN = {"Origin": "http://127.0.0.1:8000"}
Frames = list[tuple[str, dict[str, Any]]]
PostChat = Callable[[dict[str, Any]], Frames]
TEXT = "Hello from the test model."
JobModel = Callable[..., Model]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        homer_home=tmp_path / "home",
        homer_passphrase=SecretStr(PASSPHRASE),
        user_name="Tester",
        timezone="Europe/London",
        scheduler_enabled=False,
        _env_file=None,
    )


def job_model(
    intents: list[list[dict[str, Any]]],
    text: str = TEXT,
    email: dict[str, str] | None = None,
    seen: list[list[ModelMessage]] | None = None,
) -> Model:
    """Plays the three calls Homer makes: one intents list per turn (chat once they run out),
    the subject and body for `write_email`, and `text` for every plain answer."""
    queue = list(intents)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        names = {tool.name for tool in info.output_tools}
        if INTENT_TOOL in names:
            found = queue.pop(0) if queue else [{"kind": "chat"}]
            return ModelResponse(parts=[ToolCallPart(INTENT_TOOL, {"intents": found})])
        if "write_email" in names:
            written = email or {"subject": "Hello", "body": "Hi there."}
            return ModelResponse(parts=[ToolCallPart("write_email", written)])
        return ModelResponse(parts=[TextPart(content=text)])

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        if seen is not None:
            seen.append(messages)
        yield text

    return FunctionModel(function=respond, stream_function=stream, model_name="test")


@pytest.fixture
def jobs() -> JobModel:
    return job_model


@pytest.fixture
def model() -> Model:
    return job_model([])


def load_fake_server(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"fake_{name}", FAKE_SERVERS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_google() -> ModuleType:
    return load_fake_server("google")


@pytest.fixture
def mcp(fake_google: ModuleType) -> McpManager:
    fakes = {"google": fake_google, "system": load_fake_server("system")}
    return McpManager(
        {
            name: MCPToolset(Client(module.server), id=name, tool_error_behavior="failed")
            for name, module in fakes.items()
        }
    )


@pytest.fixture
async def live_mcp(fake_google: ModuleType) -> AsyncIterator[McpManager]:
    manager = McpManager(
        {
            "google": MCPToolset(
                Client(fake_google.server), id="google", tool_error_behavior="failed"
            )
        }
    )
    await manager.start()
    yield manager
    await manager.stop()


@pytest.fixture
def app(settings: Settings, model: Model, mcp: McpManager) -> FastAPI:
    return create_app(settings, model=model, mcp=mcp)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def logged_in(client: TestClient) -> TestClient:
    response = client.post("/api/auth/login", json={"passphrase": PASSPHRASE}, headers=ORIGIN)
    assert response.status_code == 204
    return client


@pytest.fixture
def origin() -> dict[str, str]:
    return ORIGIN


@pytest.fixture
def post_chat(logged_in: TestClient) -> PostChat:
    def post(body: dict[str, Any]) -> Frames:
        with logged_in.stream("POST", "/api/chat", json=body, headers=ORIGIN) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            raw = "".join(response.iter_text())
        frames: Frames = []
        for frame in filter(None, raw.split("\n\n")):
            event_line, data_line = frame.split("\n")
            name = event_line.removeprefix("event: ")
            frames.append((name, json.loads(data_line.removeprefix("data: "))))
        return frames

    return post
