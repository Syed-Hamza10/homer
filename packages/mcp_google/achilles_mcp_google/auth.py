import json
from pathlib import Path
from typing import Any

from achilles_mcp_google.settings import Settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts.readonly",
]


class NotConnected(Exception):
    pass


class TokenStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise NotConnected(str(self.path))
        return json.loads(self.path.read_text())

    def save(self, token: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600)
        self.path.chmod(0o600)
        self.path.write_text(json.dumps(token, indent=2))


def setup() -> None:
    """One-time consent flow in the browser; writes google_token.json with mode 0600."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings = Settings.from_env()
    flow = InstalledAppFlow.from_client_secrets_file(str(settings.client_secret_path), SCOPES)
    credentials = flow.run_local_server(port=0)
    TokenStore(settings.token_path).save(json.loads(credentials.to_json()))
    print(f"Google connected. Token written to {settings.token_path}")
