"""The real stack: homer serve, the real MCP servers, the Google simulator and the live model."""

import json
import sqlite3
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from sqlmodel import Session

from homer_core.db.models import FollowUp
from homer_core.db.session import make_engine
from homer_mcp_google.messages import build_raw
from homer_sim.state import DEFAULT_SEED, KNOWN_TOKEN

from .conftest import (
    OLLAMA_URL,
    STARTUP_TIMEOUT,
    VENV_BIN,
    free_port,
    process_env,
    running_server,
)

TIMEZONE = "Asia/Karachi"
ZONE = ZoneInfo(TIMEZONE)
TOMORROW_EVENT = {
    "id": "evt_e2e",
    "start": "10:00",
    "end": "11:00",
    "summary": "Studio visit with Elena Marchetti",
    "location": "Studio",
    "description": "",
    "attendees": ["elena.marchetti@example.test"],
}


@dataclass(frozen=True)
class Stack:
    home: Path
    url: str
    sim_url: str

    @property
    def hosts(self) -> set[str]:
        return {urlsplit(OLLAMA_URL).netloc, urlsplit(self.sim_url).netloc}

    def sent_count(self) -> int:
        return self.counts()["sent"]

    def counts(self) -> dict[str, int]:
        return httpx.get(f"{self.sim_url}/_sim/state").json()

    def gmail(self, path: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.sim_url}/gmail/v1/users/me{path}",
            headers={"Authorization": f"Bearer {KNOWN_TOKEN}"},
        )
        response.raise_for_status()
        return response.json()

    def label_names(self, message_id: str) -> set[str]:
        names = {label["id"]: label["name"] for label in self.gmail("/labels")["labels"]}
        return {names[label] for label in self.gmail(f"/messages/{message_id}")["labelIds"]}

    def sent_bodies(self) -> list[str]:
        found = self.gmail("/messages?q=in:sent&maxResults=50").get("messages", [])
        return [self.gmail(f"/messages/{m['id']}?format=full")["snippet"] for m in found]

    def brief_rows(self) -> list[tuple[str, str]]:
        with sqlite3.connect(self.home / "data" / "homer.db") as connection:
            return connection.execute("SELECT kind, content FROM daily_briefs").fetchall()

    def make_due(self, followup_id: int) -> None:
        with Session(make_engine(self.home)) as session:
            followup = session.get(FollowUp, followup_id)
            assert followup is not None
            followup.due_at = datetime.now(UTC) - timedelta(hours=1)
            session.add(followup)
            session.commit()

    def logged_hosts(self) -> set[str]:
        with sqlite3.connect(self.home / "data" / "homer.db") as connection:
            rows = connection.execute("SELECT DISTINCT host FROM outbound_log").fetchall()
        return {host for (host,) in rows}

    def create_draft(self, to: str, subject: str, body: str) -> str:
        response = httpx.post(
            f"{self.sim_url}/gmail/v1/users/me/drafts",
            json={"message": {"raw": build_raw(to, subject, body, None)}},
            headers={"Authorization": f"Bearer {KNOWN_TOKEN}"},
        )
        response.raise_for_status()
        return response.json()["id"]


def local_today() -> date:
    return datetime.now(ZONE).date()


def tomorrow_offset() -> int:
    """Days from the simulator's Monday (UTC) to the user's tomorrow: its `weekday` value."""
    now = datetime.now(UTC)
    monday = (now - timedelta(days=now.weekday())).date()
    return (local_today() + timedelta(days=1) - monday).days


def local_offset(days: int) -> int:
    """The simulator `weekday` value of the user's local day `days` from today."""
    return tomorrow_offset() - 1 + days


def seeded_events(extra: tuple[dict[str, Any], ...] = ()) -> list[dict[str, Any]]:
    seed = json.loads(DEFAULT_SEED.read_text())
    return [*seed["events"], {**TOMORROW_EVENT, "weekday": tomorrow_offset()}, *extra]


def tomorrow_titles() -> list[str]:
    return [e["summary"] for e in seeded_events() if e["weekday"] == tomorrow_offset()]


def write_seed(
    home: Path,
    extra: tuple[dict[str, Any], ...] = (),
    contacts: tuple[dict[str, Any], ...] = (),
    owner_name: str | None = None,
) -> Path:
    seed = {**json.loads(DEFAULT_SEED.read_text()), "events": seeded_events(extra)}
    seed["contacts"] = [*seed["contacts"], *contacts]
    if owner_name is not None:
        seed["owner"] = {**seed["owner"], "name": owner_name}
    path = home / "seed.json"
    path.write_text(json.dumps(seed))
    return path


def write_google_token(home: Path) -> None:
    path = home / "credentials" / "google_token.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    token = {
        "token": KNOWN_TOKEN,
        "refresh_token": "sim-refresh-token",
        "client_id": "sim-client-id",
        "client_secret": "sim-client-secret",
        "scopes": [],
    }
    path.write_text(json.dumps(token))


def wait_for_simulator(process: subprocess.Popen[bytes], url: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"simulator exited with {process.returncode}")
        try:
            httpx.get(f"{url}/_sim/state", timeout=1.0).raise_for_status()
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"simulator not up after {STARTUP_TIMEOUT}s")


def running_simulator(seed: Path) -> tuple[subprocess.Popen[bytes], str]:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    command = [str(VENV_BIN / "homer-sim"), "--port", str(port), "--seed", str(seed)]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_for_simulator(process, url)
    return process, url


@contextmanager
def real_stack(
    home: Path,
    web_search: bool = False,
    extra_events: tuple[dict[str, Any], ...] = (),
    contacts: tuple[dict[str, Any], ...] = (),
    owner_name: str | None = None,
) -> Iterator[Stack]:
    write_google_token(home)
    simulator, sim_url = running_simulator(write_seed(home, extra_events, contacts, owner_name))
    env = process_env(
        home,
        free_port(),
        GOOGLE_API_BASE=sim_url,
        GOOGLE_TOKEN_URL=f"{sim_url}/token",
        WEB_SEARCH=str(web_search).lower(),
        TIMEZONE=TIMEZONE,
    )
    try:
        with running_server(home, env) as url:
            yield Stack(home, url, sim_url)
    finally:
        simulator.terminate()
        simulator.wait(timeout=10)
