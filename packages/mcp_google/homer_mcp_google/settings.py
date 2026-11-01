import os
from dataclasses import dataclass
from pathlib import Path

GOOGLE_API_BASE = "https://www.googleapis.com"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class Settings:
    home: Path
    api_base: str
    token_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            home=Path(os.environ.get("HOMER_HOME", "~/.homer")).expanduser(),
            api_base=os.environ.get("GOOGLE_API_BASE", GOOGLE_API_BASE).rstrip("/"),
            token_url=os.environ.get("GOOGLE_TOKEN_URL", GOOGLE_TOKEN_URL),
        )

    @property
    def client_secret_path(self) -> Path:
        return self.home / "credentials" / "client_secret.json"

    @property
    def token_path(self) -> Path:
        return self.home / "credentials" / "google_token.json"

    @property
    def db_path(self) -> Path:
        return self.home / "data" / "homer.db"
