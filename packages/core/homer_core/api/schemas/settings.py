from typing import Literal

from pydantic import BaseModel, field_validator

from homer_core.platform import known_timezone
from homer_core.services.rules import ClientRules
from homer_core.services.search_settings import KeyedProvider, Provider


class UserSettings(ClientRules):
    timezone: str

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str) -> str:
        if not known_timezone(value):
            raise ValueError(f"unknown timezone: {value}")
        return value

    @property
    def rules(self) -> ClientRules:
        return ClientRules.model_validate(self.model_dump(exclude={"timezone"}))


class SearchIn(BaseModel):
    provider: Provider
    api_provider: KeyedProvider
    fallback: bool
    api_key: str | None = None


class SearchOut(BaseModel):
    provider: Provider
    api_provider: KeyedProvider
    fallback: bool
    key_hint: str | None
    hosts: list[str]


class SearchProbe(BaseModel):
    status: Literal["ok", "blocked", "invalid_key", "limited", "failed", "off"]
    provider: str
    results: int
