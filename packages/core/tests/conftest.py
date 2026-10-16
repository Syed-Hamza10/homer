import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel

from achilles_core.config import Settings
from achilles_core.main import create_app

PASSPHRASE = "test-pass"
ORIGIN = {"Origin": "http://127.0.0.1:8000"}
Frames = list[tuple[str, dict[str, Any]]]
PostChat = Callable[[dict[str, Any]], Frames]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        achilles_home=tmp_path / "home",
        achilles_passphrase=SecretStr(PASSPHRASE),
        user_name="Tester",
        timezone="Europe/London",
        _env_file=None,
    )


@pytest.fixture
def model() -> Model:
    return TestModel(custom_output_text="Hello from the test model.")


@pytest.fixture
def app(settings: Settings, model: Model) -> FastAPI:
    return create_app(settings, model=model)


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
