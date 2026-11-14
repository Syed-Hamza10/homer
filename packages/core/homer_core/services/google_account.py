import json
import math
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from homer_core.config import Settings
from homer_core.mcp.manager import (
    PROFILE_TOOL,
    ExecuteFailed,
    McpManager,
    ServerUnavailable,
    find_executable,
)
from homer_core.services.errors import DomainError

TOKEN_LIFETIME = timedelta(days=7)
WARN_DAYS_LEFT = 2
SETUP_COMMAND = "homer-mcp-google-setup"
RECONNECT_ERROR = "google_reconnect_required"

GoogleState = Literal["not_connected", "connected", "expiring", "expired"]


class SetupUnavailable(DomainError):
    status_code = 409


class GoogleStatus(BaseModel):
    state: GoogleState
    email: str | None = None
    connected_at: datetime | None = None
    days_left: int | None = None
    connecting: bool = False
    client_secret_found: bool = False
    client_secret_path: str = ""


def token_path(settings: Settings) -> Path:
    return settings.homer_home / "credentials" / "google_token.json"


def client_secret_path(settings: Settings) -> Path:
    return settings.homer_home / "credentials" / "client_secret.json"


def consent_time(path: Path) -> datetime | None:
    """The `connected_at` stamp written at consent; the file's mtime for older tokens."""
    if not path.exists():
        return None
    try:
        stamp = json.loads(path.read_text()).get("connected_at")
    except (OSError, ValueError, AttributeError):
        stamp = None
    if stamp:
        return datetime.fromisoformat(stamp)
    return datetime.fromtimestamp(path.stat().st_mtime, UTC)


def status_at(connected_at: datetime | None, now: datetime) -> GoogleStatus:
    if connected_at is None:
        return GoogleStatus(state="not_connected")
    left = connected_at + TOKEN_LIFETIME - now
    days_left = max(0, math.ceil(left / timedelta(days=1)))
    state: GoogleState = "connected"
    if days_left == 0:
        state = "expired"
    elif days_left <= WARN_DAYS_LEFT:
        state = "expiring"
    return GoogleStatus(state=state, connected_at=connected_at, days_left=days_left)


def local_status(settings: Settings, now: datetime) -> GoogleStatus:
    secret = client_secret_path(settings)
    return status_at(consent_time(token_path(settings)), now).model_copy(
        update={"client_secret_found": secret.exists(), "client_secret_path": str(secret)}
    )


async def live_status(settings: Settings, manager: McpManager, now: datetime) -> GoogleStatus:
    """The token file's dates, checked against Google through the hidden profile tool."""
    status = local_status(settings, now)
    if status.state in ("not_connected", "expired"):
        return status
    try:
        profile = await manager.call("google", PROFILE_TOOL, {})
    except (ExecuteFailed, ServerUnavailable):
        return status
    if not isinstance(profile, dict):
        return status
    if profile.get("error") == RECONNECT_ERROR:
        return status.model_copy(update={"state": "expired", "days_left": 0})
    return status.model_copy(update={"email": profile.get("email")})


class Connector:
    """Runs the setup command's browser consent flow as a child process, one at a time."""

    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, settings: Settings) -> None:
        if not client_secret_path(settings).exists():
            raise SetupUnavailable("client_secret.json is missing; see docs/GOOGLE_SETUP.md")
        command = find_executable(SETUP_COMMAND)
        if command is None:
            raise SetupUnavailable(f"{SETUP_COMMAND} is not installed")
        if self.running and self.process is not None:
            self.process.terminate()
        self.process = subprocess.Popen(
            [command],
            env={**os.environ, "HOMER_HOME": str(settings.homer_home)},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
