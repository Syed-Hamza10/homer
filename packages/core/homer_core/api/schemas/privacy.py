from datetime import datetime

from pydantic import BaseModel


class HostOut(BaseModel):
    host: str
    calls: int
    last_seen: datetime


class HostsResponse(BaseModel):
    hosts: list[HostOut]
    web_search: bool
    web_search_configured: bool
    search_hosts: list[str]


class UsageResponse(BaseModel):
    input_tokens: int
    output_tokens: int
    requests: int
    spent_usd: float = 0


class WebSearchRequest(BaseModel):
    enabled: bool


class WebSearchResponse(BaseModel):
    enabled: bool
    restart_required: bool


class WipeRequest(BaseModel):
    confirm: bool


class WipeResponse(BaseModel):
    deleted: dict[str, int]
