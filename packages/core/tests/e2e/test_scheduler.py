"""The scheduler on a real server: the health job runs at start and feeds the Today page."""

import time
from pathlib import Path

import httpx
import pytest

from .conftest import free_port, login, require_ollama, running_server, stand_in_env

pytestmark = pytest.mark.e2e
HEALTH_TIMEOUT = 20.0


def test_health_job_reports_on_today(tmp_path_factory: pytest.TempPathFactory) -> None:
    require_ollama()
    home: Path = tmp_path_factory.mktemp("achilles-scheduler-home")
    env = stand_in_env(home, free_port(), SCHEDULER_ENABLED="true")
    with running_server(home, env) as url, httpx.Client(base_url=url, headers={"Origin": url}) as c:
        login(c)
        deadline = time.monotonic() + HEALTH_TIMEOUT
        health = None
        while health is None and time.monotonic() < deadline:
            health = c.get("/api/today").json()["health"]
            time.sleep(0.25)
    assert health is not None, "the health job did not run at start"
    assert health["ollama"] == "ok" and health["model_pulled"] == "ok"
    assert set(health["servers"]) == {"google", "search", "system"}
    assert health["servers"]["google"] == "ok" and health["servers"]["system"] == "ok"
    assert health["self_email"] == "off"
