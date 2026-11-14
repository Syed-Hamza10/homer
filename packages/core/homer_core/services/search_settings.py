from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from homer_core.config import Settings
from homer_core.privacy_hosts import KEYED_SEARCH_HOSTS, SEARCH_HOSTS

Provider = Literal["duckduckgo", "brave", "tavily"]
KeyedProvider = Literal["brave", "tavily"]


class SearchSettings(BaseModel):
    provider: Provider = "duckduckgo"
    api_provider: KeyedProvider = "brave"
    api_key: str = ""
    fallback: bool = True

    @property
    def key_provider(self) -> KeyedProvider:
        return self.api_provider if self.provider == "duckduckgo" else self.provider

    def hosts(self) -> tuple[str, ...]:
        """The hosts the search server may contact; mirrors `homer_mcp_search.providers.hosts`."""
        if not self.api_key:
            return SEARCH_HOSTS
        keyed = KEYED_SEARCH_HOSTS[self.key_provider]
        if self.provider != "duckduckgo":
            return (keyed,)
        return (*SEARCH_HOSTS, keyed) if self.fallback else SEARCH_HOSTS


def search_path(settings: Settings) -> Path:
    return settings.homer_home / "credentials" / "search.json"


def load_search(settings: Settings) -> SearchSettings:
    """The saved Settings-page choice, else the SEARCH_* environment."""
    path = search_path(settings)
    if path.exists():
        return SearchSettings.model_validate_json(path.read_text())
    return SearchSettings(
        provider=settings.search_provider,
        api_provider=settings.search_api_provider,
        api_key=settings.search_api_key.get_secret_value(),
        fallback=settings.search_fallback,
    )


def save_search(settings: Settings, search: SearchSettings) -> None:
    path = search_path(settings)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.chmod(0o600)
    path.write_text(search.model_dump_json())


def key_hint(key: str) -> str | None:
    return f"…{key[-4:]}" if key else None
