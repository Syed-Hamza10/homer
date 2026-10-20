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
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.models.test import TestModel

from achilles_core.config import Settings
from achilles_core.main import create_app
from achilles_core.mcp.manager import McpManager

FAKE_SERVERS = Path(__file__).parent / "fake_servers"

PASSPHRASE = "test-pass"
ORIGIN = {"Origin": "http://127.0.0.1:8000"}
Frames = list[tuple[str, dict[str, Any]]]
PostChat = Callable[[dict[str, Any]], Frames]
Step = list[tuple[str, dict[str, Any]]] | str
Scripted = Callable[[str, list[Step], list[list[str]]], Model]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        achilles_home=tmp_path / "home",
        achilles_passphrase=SecretStr(PASSPHRASE),
        user_name="Tester",
        timezone="Europe/London",
        scheduler_enabled=False,
        _env_file=None,
    )


def scripted_model(toolset_name: str, steps: list[Step], seen_tools: list[list[str]]) -> Model:
    """Classifies as toolset_name, then plays one scripted step (tool calls or text) per turn."""

    def classify(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content=toolset_name)])

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[Any]:
        seen_tools.append([tool.name for tool in info.function_tools])
        step = steps[sum(isinstance(message, ModelResponse) for message in messages)]
        if isinstance(step, str):
            yield step
        else:
            yield {
                index: DeltaToolCall(name=name, json_args=json.dumps(args))
                for index, (name, args) in enumerate(step)
            }

    return FunctionModel(function=classify, stream_function=stream)


@pytest.fixture
def scripted() -> Scripted:
    return scripted_model


@pytest.fixture
def model() -> Model:
    return TestModel(custom_output_text="Hello from the test model.", call_tools=[])


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
