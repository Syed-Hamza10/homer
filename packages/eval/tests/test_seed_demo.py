import importlib.util
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from homer_sim.state import KNOWN_TOKEN

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "scripts"
VENV_BIN = Path(sys.executable).parent
AUTH = {"Authorization": f"Bearer {KNOWN_TOKEN}"}
DEMO_QUERY = {"q": "label:homer-demo -in:trash"}


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed(*args: str) -> str:
    command = [sys.executable, str(SCRIPTS / "seed_demo.py"), *args]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.fixture(scope="module")
def sim_url() -> Iterator[str]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    command = [str(VENV_BIN / "homer-sim"), "--port", str(port)]
    command += ["--seed", str(SCRIPTS / "demo_sim_seed.json")]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                httpx.get(f"{url}/_sim/state", timeout=1.0).raise_for_status()
                break
            except httpx.HTTPError:
                time.sleep(0.2)
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_demo_data_is_fictional_and_sized() -> None:
    data = load("demo_data")
    messages = [m for thread in data.THREADS for m in thread.messages]
    assert len(data.THREADS) == 4 and len(messages) == 10 and len(data.EVENTS) == 6
    contacts = [data.OWNER, *(thread.contact for thread in data.THREADS)]
    assert all(data.address(contact).endswith("example.test") for contact in contacts)
    assert all(e.day_offset >= 1 for e in data.EVENTS)
    assert sum(e.day_offset == 1 for e in data.EVENTS) == 2


def test_seed_sim_is_idempotent_and_wipes(sim_url: str) -> None:
    first = seed("--target", "sim", "--sim-url", sim_url)
    assert "inserted 10 messages in 4 threads" in first and "inserted 6 events" in first
    second = seed("--target", "sim", "--sim-url", sim_url)
    assert "mail: already seeded" in second and "calendar: already seeded" in second

    state = httpx.get(f"{sim_url}/_sim/state").json()
    assert state["messages"] == 10 and state["sent"] == 4 and state["events"] == 6
    gmail = f"{sim_url}/gmail/v1/users/me"
    found = httpx.get(f"{gmail}/messages", params=DEMO_QUERY, headers=AUTH).json()["messages"]
    assert len(found) == 10 and len({m["threadId"] for m in found}) == 4
    labels = {
        label["name"] for label in httpx.get(f"{gmail}/labels", headers=AUTH).json()["labels"]
    }
    assert {"Clients", "Invoices", "Newsletters", "homer-demo"} <= labels

    wiped = seed("--target", "sim", "--sim-url", sim_url, "--wipe")
    assert "10 messages trashed, 6 events deleted" in wiped
    assert httpx.get(f"{sim_url}/_sim/state").json()["events"] == 0
    assert httpx.get(f"{gmail}/messages", params=DEMO_QUERY, headers=AUTH).json()["messages"] == []
    assert "0 messages trashed, 0 events deleted" in seed(
        "--target", "sim", "--sim-url", sim_url, "--wipe"
    )


def test_google_dry_run_prints_requests_only() -> None:
    output = seed("--target", "google", "--dry-run")
    lines = output.splitlines()
    assert lines[0] == "target: google at https://www.googleapis.com (dry run)"
    posts = [line for line in lines if line.startswith("POST https://www.googleapis.com/")]
    assert sum("/gmail/v1/users/me/messages?" in line for line in posts) == 10
    assert sum("/calendar/v3/calendars/primary/events?" in line for line in posts) == 6
    assert all("<" in line and "chars>" in line for line in posts if "/messages?" in line)
