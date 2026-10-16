from datetime import datetime

from pydantic import BaseModel


class HostOut(BaseModel):
    host: str
    calls: int
    last_seen: datetime


class HostsResponse(BaseModel):
    hosts: list[HostOut]
    web_search: bool


class UsageResponse(BaseModel):
    input_tokens: int
    output_tokens: int
    requests: int
    spent_usd: float = 0
