import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from homer_mcp_google.settings import Settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts.readonly",
]


class ReconnectRequired(Exception):
    """No token file, or Google refused the refresh token (expired or revoked)."""


class TokenStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise ReconnectRequired(str(self.path))
        return json.loads(self.path.read_text())

    def save(self, token: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600)
        self.path.chmod(0o600)
        self.path.write_text(json.dumps(token, indent=2))


def connect(settings: Settings) -> Path:
    """Runs the consent flow in the browser; writes the token with its consent time, mode 0600."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(settings.client_secret_path), SCOPES)
    credentials = flow.run_local_server(port=0)
    token = {**json.loads(credentials.to_json()), "connected_at": datetime.now(UTC).isoformat()}
    TokenStore(settings.token_path).save(token)
    return settings.token_path


def setup() -> None:
    path = connect(Settings.from_env())
    print(f"Google connected. Token written to {path}")
