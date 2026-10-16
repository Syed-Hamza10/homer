import respx
from fastapi.testclient import TestClient

from achilles_core import __version__


def test_health_reports_ollama_ok(client: TestClient, respx_mock: respx.MockRouter) -> None:
    respx_mock.get("http://127.0.0.1:11434/api/tags").respond(200, json={"models": []})
    body = client.get("/api/health").json()
    assert body == {
        "status": "ok",
        "version": __version__,
        "ollama": "ok",
        "model": "test",
        "servers": {"google": "ok", "search": "down", "system": "ok"},
    }


def test_health_reports_ollama_down(client: TestClient, respx_mock: respx.MockRouter) -> None:
    respx_mock.get("http://127.0.0.1:11434/api/tags").respond(503)
    assert client.get("/api/health").json()["ollama"] == "down"
