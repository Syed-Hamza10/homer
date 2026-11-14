import os
import secrets
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from homer_core.platform import system_timezone

PASSPHRASE_KEY = "HOMER_PASSPHRASE"


def home_dir() -> Path:
    return Path(os.environ.get("HOMER_HOME", "~/.homer")).expanduser()


HOME = home_dir()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(HOME / ".env", ".env"), extra="ignore")

    homer_home: Path = HOME
    ollama_url: str = "http://127.0.0.1:11434"
    homer_passphrase: SecretStr
    web_search: bool = True
    search_provider: Literal["duckduckgo", "brave", "tavily"] = "duckduckgo"
    search_api_provider: Literal["brave", "tavily"] = "brave"
    search_api_key: SecretStr = SecretStr("")
    search_fallback: bool = True
    google_api_base: str = "https://www.googleapis.com"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    host: str = "127.0.0.1"
    port: int = 8000
    extra_origins: list[str] = []
    user_name: str = "there"
    timezone: str = Field(default_factory=lambda: system_timezone() or "UTC")
    scheduler_enabled: bool = True

    @field_validator("homer_home")
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
    """Reads homer_home/session_secret, creating it with mode 0600 on first use."""
    path = settings.homer_home / "session_secret"
    if not path.exists():
        path.touch(mode=0o600)
        path.write_text(secrets.token_urlsafe(32))
    return path.read_text().strip()


def read_passphrase(home: Path) -> str | None:
    return dotenv_values(home / ".env").get(PASSPHRASE_KEY)


def write_passphrase(home: Path, passphrase: str) -> Path:
    """Replaces the HOMER_PASSPHRASE line in home/.env, or adds it, keeping mode 0600."""
    path = home / ".env"
    escaped = passphrase.replace("\\", "\\\\").replace('"', '\\"')
    line = f'{PASSPHRASE_KEY}="{escaped}"'
    kept = (
        [x for x in path.read_text().splitlines() if not x.startswith(f"{PASSPHRASE_KEY}=")]
        if path.exists()
        else []
    )
    home.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".env.tmp")
    temporary.touch(mode=0o600)
    temporary.write_text("\n".join([*kept, line]) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)
    return path
