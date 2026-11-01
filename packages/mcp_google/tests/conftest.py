import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

REPO = Path(__file__).resolve().parents[3]
STARTUP_TIMEOUT = 30.0
KNOWN_TOKEN = "sim-access-token"
OUTBOUND_LOG_SCHEMA = (
    "CREATE TABLE outbound_log (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, method TEXT NOT NULL, "
    "host TEXT NOT NULL, path TEXT NOT NULL, status INTEGER, duration_ms INTEGER NOT NULL)"
)

Spawn = Callable[[Path, str | None, str | None], Client]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _write_token(home: Path, access_token: str = KNOWN_TOKEN) -> Path:
    path = home / "credentials" / "google_token.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "token": access_token,
                "refresh_token": "sim-refresh-token",
                "client_id": "sim-client-id",
                "client_secret": "sim-client-secret",
                "scopes": [],
            }
        )
    )
    return path


def _create_outbound_log(home: Path) -> Path:
    db = home / "data" / "homer.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute(OUTBOUND_LOG_SCHEMA)
    return db


def _spawn(home: Path, api_base: str, token_url: str) -> Client:
    env = {
        **os.environ,
        "HOMER_HOME": str(home),
        "GOOGLE_API_BASE": api_base,
        "GOOGLE_TOKEN_URL": token_url,
    }
    transport = StdioTransport(
        command="uv",
        args=["run", "--project", str(REPO), "homer-mcp-google"],
        env=env,
        log_file=sys.stderr,
    )
    return Client(transport, timeout=60)


@pytest.fixture
def free_port() -> Callable[[], int]:
    return _free_port


@pytest.fixture
def write_token() -> Callable[..., Path]:
    return _write_token


@pytest.fixture
def create_outbound_log() -> Callable[[Path], Path]:
    return _create_outbound_log


@pytest.fixture(scope="session")
def sim_url() -> Iterator[str]:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        ["uv", "run", "--project", str(REPO), "homer-sim", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(process.stderr.read().decode() if process.stderr else "sim died")
        try:
            httpx.get(f"{url}/_sim/state", timeout=1.0).raise_for_status()
            break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        process.kill()
        raise RuntimeError("simulator did not start")
    yield url
    process.terminate()
    process.wait(timeout=10)


@pytest.fixture
def sim(sim_url: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=sim_url, timeout=10.0) as client:
        client.post("/_sim/reset").raise_for_status()
        yield client


@pytest.fixture
def spawn(sim_url: str) -> Spawn:
    """Starts a fresh MCP server over stdio against the simulator; None keeps the simulator URLs."""

    def start(home: Path, api_base: str | None = None, token_url: str | None = None) -> Client:
        return _spawn(home, api_base or sim_url, token_url or f"{sim_url}/token")

    return start


@pytest.fixture(scope="session")
def home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    home = tmp_path_factory.mktemp("homer_home")
    _write_token(home)
    _create_outbound_log(home)
    return home


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def mcp(sim_url: str, home: Path) -> AsyncIterator[Client]:
    async with _spawn(home, sim_url, f"{sim_url}/token") as client:
        yield client
