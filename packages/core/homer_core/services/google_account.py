import json
import math
import os
import subprocess
from collections.abc import Iterable
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
NO_BROWSER_FLAG = "--no-browser"
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
    auth_url: str | None = None


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


def first_link(lines: Iterable[str]) -> str | None:
    return next((line.strip() for line in lines if line.startswith("https://")), None)


class Connector:
    """Runs the setup command's consent flow as a child process, one at a time.

    Without a browser the child prints the sign-in link, which is kept in `auth_url`.
    """

    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.auth_url: str | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, settings: Settings, open_browser: bool = True) -> None:
        if not client_secret_path(settings).exists():
            raise SetupUnavailable("client_secret.json is missing; see docs/GOOGLE_SETUP.md")
        command = find_executable(SETUP_COMMAND)
        if command is None:
            raise SetupUnavailable(f"{SETUP_COMMAND} is not installed")
        if self.running and self.process is not None:
            self.process.terminate()
        self.auth_url = None
        self.process = subprocess.Popen(
            [command] if open_browser else [command, NO_BROWSER_FLAG],
            env={**os.environ, "HOMER_HOME": str(settings.homer_home), "PYTHONUNBUFFERED": "1"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL if open_browser else subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if open_browser or self.process.stdout is None:
            return
        self.auth_url = first_link(self.process.stdout)
        if self.auth_url is None:
            raise SetupUnavailable(
                "Google sign-in did not start; check client_secret.json (docs/GOOGLE_SETUP.md)"
            )
