import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
from playwright.sync_api import Page, expect
from sqlmodel import Session

from achilles_core.config import Settings
from achilles_core.db.models import Approval
from achilles_core.db.session import make_engine
from achilles_core.llm import chat_model_tag
from achilles_core.platform import hardware_tier
from achilles_core.services.approvals import create_from_tool_result

REPO = Path(__file__).resolve().parents[4]
FAKE_SERVERS = Path(__file__).resolve().parents[1] / "fake_servers"
VENV_BIN = Path(sys.executable).parent
OLLAMA_URL = "http://127.0.0.1:11434"
PASSPHRASE = "e2e-pass"
PONG_PROMPT = "Reply with exactly the single word PONG and nothing else."
REQUEST_TIMEOUT = 120.0
STARTUP_TIMEOUT = 60.0
Frames = list[tuple[str, dict[str, Any]]]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Runs e2e last: the sync Playwright API leaves an event loop running for the session."""
    items.sort(key=lambda item: item.get_closest_marker("e2e") is not None)


def require_ollama() -> None:
    tag = chat_model_tag(hardware_tier())
    try:
        response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
        response.raise_for_status()
    except httpx.HTTPError as error:
        pytest.skip(f"Ollama not reachable at {OLLAMA_URL}: {error}")
    if tag not in [model["name"] for model in response.json()["models"]]:
        pytest.skip(f"model {tag} is not pulled in Ollama at {OLLAMA_URL}")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def write_fake_servers(home: Path) -> Path:
    """Puts stand-in achilles-mcp-google and achilles-mcp-system launchers on a bin dir."""
    bin_dir = home / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in ("google", "system"):
        script = bin_dir / f"achilles-mcp-{name}"
        source = FAKE_SERVERS / f"{name}.py"
        launcher = f"runpy.run_path({str(source)!r}, run_name='__main__')"
        script.write_text(f"#!{sys.executable}\nimport runpy\n{launcher}\n")
        script.chmod(0o755)
    return bin_dir


def process_env(home: Path, port: int) -> dict[str, str]:
    (home / ".env").write_text(f"ACHILLES_PASSPHRASE={PASSPHRASE}\nOLLAMA_URL={OLLAMA_URL}\n")
    inherited = {k: v for k, v in os.environ.items() if k.lower() not in Settings.model_fields}
    path = os.pathsep.join([str(write_fake_servers(home)), inherited.get("PATH", "")])
    return {
        **inherited,
        "PATH": path,
        "ACHILLES_HOME": str(home),
        "HOST": "127.0.0.1",
        "PORT": str(port),
    }


def achilles_command(*args: str) -> list[str]:
    return [str(VENV_BIN / "achilles"), *args]


def create_pending_approval(home: Path, draft_id: str = "d1") -> int:
    result = {
        "approval_required": True,
        "action": "mail_send",
        "payload": {"draft_id": draft_id},
        "preview": f"Send draft {draft_id}",
    }
    with Session(make_engine(home)) as session:
        return create_from_tool_result(session, 1, "google", result).id


def approval_status(home: Path, approval_id: int) -> str:
    with Session(make_engine(home)) as session:
        approval = session.get(Approval, approval_id)
        assert approval is not None
        return approval.status


def unlock(page: Page, server: str) -> None:
    page.goto(server)
    expect(page).to_have_url(f"{server}/login")
    page.get_by_placeholder("Passphrase").fill(PASSPHRASE)
    page.get_by_role("button", name="Unlock").click()
    expect(page).to_have_url(f"{server}/")


def wait_until_healthy(process: subprocess.Popen[bytes], base_url: str, log: Path) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited with {process.returncode}:\n{log.read_text()}")
        try:
            response = httpx.get(f"{base_url}/api/health", timeout=5.0)
            if response.status_code == 200 and response.json()["ollama"] == "ok":
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"server not healthy after {STARTUP_TIMEOUT}s:\n{log.read_text()}")


@contextmanager
def running_server(home: Path) -> Iterator[str]:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    log = home / "server.log"
    with log.open("wb") as log_file:
        process = subprocess.Popen(
            achilles_command("serve"),
            cwd=home,
            env=process_env(home, port),
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_until_healthy(process, base_url, log)
            yield base_url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def login(client: httpx.Client) -> None:
    response = client.post("/api/auth/login", json={"passphrase": PASSPHRASE})
    assert response.status_code == 204, response.text


def post_chat(client: httpx.Client, body: dict[str, Any]) -> Frames:
    with client.stream("POST", "/api/chat", json=body) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join(response.iter_text())
    frames: Frames = []
    for frame in filter(None, raw.split("\n\n")):
        event_line, data_line = frame.split("\n")
        name = event_line.removeprefix("event: ")
        frames.append((name, json.loads(data_line.removeprefix("data: "))))
    return frames


@pytest.fixture(scope="session")
def home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("achilles-home")


@pytest.fixture(scope="session")
def server(home: Path) -> Iterator[str]:
    require_ollama()
    with running_server(home) as base_url:
        yield base_url


@pytest.fixture
def fresh_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    require_ollama()
    with running_server(tmp_path_factory.mktemp("achilles-home")) as base_url:
        yield base_url


@pytest.fixture
def server_env(home: Path, server: str) -> dict[str, str]:
    port = urlsplit(server).port
    assert port is not None
    return process_env(home, port)


@pytest.fixture
def doctor_command() -> list[str]:
    return achilles_command("doctor")


@pytest.fixture
def client(server: str) -> Iterator[httpx.Client]:
    with httpx.Client(
        base_url=server, timeout=REQUEST_TIMEOUT, headers={"Origin": server}
    ) as http_client:
        yield http_client


@pytest.fixture
def logged_in(client: httpx.Client) -> httpx.Client:
    login(client)
    return client


@pytest.fixture(scope="session")
def prompt() -> str:
    return PONG_PROMPT


@pytest.fixture(scope="session")
def passphrase() -> str:
    return PASSPHRASE


@pytest.fixture(scope="session")
def first_reply(server: str) -> Frames:
    with httpx.Client(
        base_url=server, timeout=REQUEST_TIMEOUT, headers={"Origin": server}
    ) as http_client:
        login(http_client)
        return post_chat(http_client, {"message": PONG_PROMPT})


@pytest.fixture(scope="session")
def follow_up_reply(server: str, first_reply: Frames) -> Frames:
    conversation_id = first_reply[0][1]["conversation_id"]
    with httpx.Client(
        base_url=server, timeout=REQUEST_TIMEOUT, headers={"Origin": server}
    ) as http_client:
        login(http_client)
        return post_chat(
            http_client,
            {
                "conversation_id": conversation_id,
                "message": "What word did you just say? Answer with that word only.",
            },
        )


@pytest.fixture
def create_approval(home: Path, server: str) -> Callable[[str], int]:
    return lambda draft_id: create_pending_approval(home, draft_id)


@pytest.fixture
def status_of(home: Path) -> Callable[[int], str]:
    return lambda approval_id: approval_status(home, approval_id)


@pytest.fixture
def unlocked(page: Page, server: str) -> Page:
    unlock(page, server)
    return page


@pytest.fixture
def chat(logged_in: httpx.Client) -> Callable[[dict[str, Any]], Frames]:
    return lambda body: post_chat(logged_in, body)
