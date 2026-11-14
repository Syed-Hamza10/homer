import importlib.util
import json
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import FastMCP
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
from homer_core.services.jobs.memory import RECALL_TOOL
from homer_mcp_google.auth import TokenStore
from homer_mcp_google.client import GoogleClient
from homer_mcp_google.settings import Settings as GoogleSettings
from homer_mcp_google.tools import GoogleTools, register
from homer_net import Allowlist, AllowlistedClient
from homer_sim.app import create_app as create_sim_app
from homer_sim.state import KNOWN_TOKEN

FAKE_SERVERS = Path(__file__).parent / "fake_servers"
SIM_BASE = "http://sim.test"

PASSPHRASE = "test-pass"
ORIGIN = {"Origin": "http://127.0.0.1:8000"}
Frames = list[tuple[str, dict[str, Any]]]
PostChat = Callable[[dict[str, Any]], Frames]
TEXT = "Hello from the test model."
JobModel = Callable[..., Model]
WRITTEN = {"subject": "Hello", "body": "Just checking in to see how the week is going for you."}


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
    email: dict[str, str] | list[dict[str, str]] | None = None,
    seen: list[list[ModelMessage]] | None = None,
    recalled: dict[str, Any] | None = None,
    asked: list[str] | None = None,
) -> Model:
    """Plays the calls Homer makes: one intents list per turn (chat once they run out; each
    intent prompt is added to `asked`), the subject and body for `write_email` (a list is
    played in order, its last one repeats), `recalled` for an answer from saved facts, and
    `text` for every plain answer."""
    queue = list(intents)
    emails = list(email) if isinstance(email, list) else [email or WRITTEN]

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        names = {tool.name for tool in info.output_tools}
        if INTENT_TOOL in names:
            if asked is not None:
                asked.append(" ".join(str(part.content) for part in messages[-1].parts))
            found = queue.pop(0) if queue else [{"kind": "chat"}]
            return ModelResponse(parts=[ToolCallPart(INTENT_TOOL, {"intents": found})])
        if RECALL_TOOL in names:
            return ModelResponse(parts=[ToolCallPart(RECALL_TOOL, recalled or {"answer": text})])
        if "write_email" in names:
            written = emails.pop(0) if len(emails) > 1 else emails[0]
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


def sim_google_server(home: Path, sim: FastAPI) -> FastMCP:
    """The real google MCP server, in process, with its HTTP routed to the simulator app."""
    settings = GoogleSettings(home=home, api_base=SIM_BASE, token_url=f"{SIM_BASE}/token")
    settings.token_path.parent.mkdir(parents=True, exist_ok=True)
    settings.token_path.write_text(json.dumps({"token": KNOWN_TOKEN, "refresh_token": "r"}))
    client = GoogleClient(settings, TokenStore(settings.token_path))
    client.http = AllowlistedClient(
        Allowlist({"sim.test"}), transport=httpx.ASGITransport(app=sim), timeout=30.0
    )
    server = FastMCP("homer-google")
    register(server, GoogleTools(client))
    return server


@pytest.fixture
def sim() -> FastAPI:
    return create_sim_app()


@pytest.fixture
def sim_mcp(tmp_path: Path, sim: FastAPI) -> McpManager:
    server = sim_google_server(tmp_path / "google", sim)
    return McpManager(
        {"google": MCPToolset(Client(server), id="google", tool_error_behavior="failed")}
    )


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
