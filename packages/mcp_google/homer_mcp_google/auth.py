import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from homer_mcp_google.settings import Settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts.readonly",
]
NO_BROWSER_FLAG = "--no-browser"


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


def connect(settings: Settings, open_browser: bool = True) -> Path:
    """Runs the consent flow and writes the token with its consent time, mode 0600.

    Without a browser it prints only the sign-in link, for the caller to show the user.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(settings.client_secret_path), SCOPES)
    if open_browser:
        credentials = flow.run_local_server(port=0)
    else:
        credentials = flow.run_local_server(
            port=0, open_browser=False, authorization_prompt_message="{url}"
        )
    token = {**json.loads(credentials.to_json()), "connected_at": datetime.now(UTC).isoformat()}
    TokenStore(settings.token_path).save(token)
    return settings.token_path


def setup() -> None:
    path = connect(Settings.from_env(), open_browser=NO_BROWSER_FLAG not in sys.argv[1:])
    print(f"Google connected. Token written to {path}")
