from typing import Literal

from pydantic import BaseModel

from achilles_core.services.briefs import SelfEmailStatus

Status = Literal["ok", "down"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    ollama: Status
    model: str
    servers: dict[str, Status]
    self_email: SelfEmailStatus
