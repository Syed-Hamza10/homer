import os
from dataclasses import dataclass
from pathlib import Path

GOOGLE_API_BASE = "https://www.googleapis.com"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_PEOPLE_API_BASE = "https://people.googleapis.com"


@dataclass(frozen=True)
class Settings:
    home: Path
    api_base: str
    token_url: str
    people_base: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        api_base = os.environ.get("GOOGLE_API_BASE", GOOGLE_API_BASE).rstrip("/")
        people_default = GOOGLE_PEOPLE_API_BASE if api_base == GOOGLE_API_BASE else api_base
        return cls(
            home=Path(os.environ.get("HOMER_HOME", "~/.homer")).expanduser(),
            api_base=api_base,
            token_url=os.environ.get("GOOGLE_TOKEN_URL", GOOGLE_TOKEN_URL),
            people_base=os.environ.get("GOOGLE_PEOPLE_API_BASE", people_default).rstrip("/"),
        )

    @property
    def people_api(self) -> str:
        return self.people_base or self.api_base

    @property
    def client_secret_path(self) -> Path:
        return self.home / "credentials" / "client_secret.json"

    @property
    def token_path(self) -> Path:
        return self.home / "credentials" / "google_token.json"

    @property
    def db_path(self) -> Path:
        return self.home / "data" / "homer.db"
