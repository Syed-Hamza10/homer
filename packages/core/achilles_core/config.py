import os
import secrets
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from achilles_core.platform import system_timezone

HOME = Path(os.environ.get("ACHILLES_HOME", "~/.achilles")).expanduser()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(HOME / ".env", ".env"), extra="ignore")

    achilles_home: Path = HOME
    ollama_url: str = "http://127.0.0.1:11434"
    achilles_passphrase: SecretStr
    web_search: bool = True
    google_api_base: str = "https://www.googleapis.com"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    host: str = "127.0.0.1"
    port: int = 8000
    extra_origins: list[str] = []
    user_name: str = "there"
    timezone: str = Field(default_factory=lambda: system_timezone() or "UTC")
    scheduler_enabled: bool = True

    @field_validator("achilles_home")
    @classmethod
    def expand(cls, value: Path) -> Path:
        return value.expanduser()


def own_origins(settings: Settings) -> set[str]:
    return {
        f"http://127.0.0.1:{settings.port}",
        f"http://localhost:{settings.port}",
        *settings.extra_origins,
    }


def session_secret(settings: Settings) -> str:
    """Reads achilles_home/session_secret, creating it with mode 0600 on first use."""
    path = settings.achilles_home / "session_secret"
    if not path.exists():
        path.touch(mode=0o600)
        path.write_text(secrets.token_urlsafe(32))
    return path.read_text().strip()
