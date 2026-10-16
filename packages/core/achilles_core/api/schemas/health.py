from typing import Literal

from pydantic import BaseModel

Status = Literal["ok", "down"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    ollama: Status
    model: str
    servers: dict[str, Status]
