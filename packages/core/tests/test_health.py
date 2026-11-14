import json

import httpx
import respx
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homer_core import __version__
from homer_core.agent.intents import OUTPUT_TOOL, build_intent_agent, instructions
from homer_core.services.ollama import warm, warm_up
from homer_net import Allowlist, AllowlistedClient

from .conftest import ORIGIN


def test_health_reports_ollama_ok(client: TestClient, respx_mock: respx.MockRouter) -> None:
    respx_mock.get("http://127.0.0.1:11434/api/tags").respond(
        200, json={"models": [{"name": "test"}]}
    )
    body = client.get("/api/health").json()
    assert body.pop("checked_at")
    assert body == {
        "status": "ok",
        "version": __version__,
        "ollama": "ok",
        "model": "test",
        "model_pulled": "ok",
        "model_status": "running",
        "servers": {"google": "ok", "search": "down", "system": "ok"},
        "self_email": "off",
    }


def test_health_reports_a_missing_model(client: TestClient, respx_mock: respx.MockRouter) -> None:
    respx_mock.get("http://127.0.0.1:11434/api/tags").respond(200, json={"models": []})
    body = client.get("/api/health").json()
    assert body["ollama"] == "ok" and body["model_pulled"] == "down"
    assert body["model_status"] == "missing"


def test_health_reports_ollama_down(client: TestClient, respx_mock: respx.MockRouter) -> None:
    respx_mock.get("http://127.0.0.1:11434/api/tags").respond(503)
    body = client.get("/api/health").json()
    assert (body["ollama"], body["model_status"]) == ("down", "stopped")


def test_warm_loads_the_chat_model_with_keep_alive(
    logged_in: TestClient, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.post("http://127.0.0.1:11434/api/generate").respond(200, json={})
    response = logged_in.post("/api/model/warm", headers=ORIGIN)
    assert response.status_code == 204
    assert json.loads(route.calls.last.request.content) == {"model": "test", "keep_alive": "10m"}


def test_warm_failure_is_not_an_error(logged_in: TestClient, respx_mock: respx.MockRouter) -> None:
    respx_mock.post("http://127.0.0.1:11434/api/generate").respond(500)
    assert logged_in.post("/api/model/warm", headers=ORIGIN).status_code == 204


def test_warm_needs_login(client: TestClient) -> None:
    assert client.post("/api/model/warm", headers=ORIGIN).status_code == 401


async def test_warm_reports_an_unreachable_ollama(respx_mock: respx.MockRouter) -> None:
    respx_mock.post("http://ollama.test/api/generate").mock(side_effect=httpx.ConnectError("x"))
    client = AllowlistedClient(Allowlist(["ollama.test"]))
    assert await warm(client, "http://ollama.test", "test") is False


async def test_warm_up_primes_the_intent_prompt(respx_mock: respx.MockRouter) -> None:
    respx_mock.post("http://ollama.test/api/generate").respond(200, json={})
    asked: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        asked.append(str(getattr(messages[-1], "instructions", "")))
        return ModelResponse(parts=[ToolCallPart(OUTPUT_TOOL, {"intents": [{"kind": "chat"}]})])

    client = AllowlistedClient(Allowlist(["ollama.test"]))
    agent = build_intent_agent(FunctionModel(function=respond))
    await warm_up(client, "http://ollama.test", "test", agent)
    assert len(asked) == 1 and asked[0] == instructions()
