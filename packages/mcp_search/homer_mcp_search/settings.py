import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from homer_net import OutboundCall, SqliteLog
from homer_net.client import no_log

VERSION = version("homer-mcp-search")
FALSE_VALUES = {"0", "false", "no", "off"}
DUCKDUCKGO = "duckduckgo"
KEYED_HOSTS = {"brave": "api.search.brave.com", "tavily": "api.tavily.com"}

LogFn = Callable[[OutboundCall], None]


@dataclass(frozen=True)
class SearchConfig:
    provider: str = DUCKDUCKGO
    api_provider: str = "brave"
    api_key: str = ""
    fallback: bool = True

    @property
    def key_provider(self) -> str:
        return self.api_provider if self.provider == DUCKDUCKGO else self.provider

    @property
    def primary(self) -> str:
        keyed = self.provider in KEYED_HOSTS and bool(self.api_key)
        return self.provider if keyed else DUCKDUCKGO

    @property
    def backup(self) -> str | None:
        """The keyed service DuckDuckGo falls back to when it shows its bot check."""
        usable = self.api_key and self.fallback and self.key_provider in KEYED_HOSTS
        return self.key_provider if self.primary == DUCKDUCKGO and usable else None


def homer_home() -> Path:
    return Path(os.environ.get("HOMER_HOME", "~/.homer")).expanduser()


def flag(value: str) -> bool:
    return value.strip().lower() not in FALSE_VALUES


def web_search_enabled() -> bool:
    return flag(os.environ.get("WEB_SEARCH", "true"))


def search_config() -> SearchConfig:
    """Reads the file the Settings page writes, so a change applies on the next search;
    without it, the SEARCH_* environment variables."""
    path = homer_home() / "credentials" / "search.json"
    if path.exists():
        saved = json.loads(path.read_text())
        return SearchConfig(
            provider=str(saved.get("provider", DUCKDUCKGO)),
            api_provider=str(saved.get("api_provider", "brave")),
            api_key=str(saved.get("api_key", "")),
            fallback=bool(saved.get("fallback", True)),
        )
    return SearchConfig(
        provider=os.environ.get("SEARCH_PROVIDER", DUCKDUCKGO).strip().lower(),
        api_provider=os.environ.get("SEARCH_API_PROVIDER", "brave").strip().lower(),
        api_key=os.environ.get("SEARCH_API_KEY", "").strip(),
        fallback=flag(os.environ.get("SEARCH_FALLBACK", "true")),
    )


def build_log() -> LogFn:
    db = homer_home() / "data" / "homer.db"
    return SqliteLog(db) if db.exists() else no_log
