from typing import Literal

from achilles_core.services.health import HealthReport


class HealthResponse(HealthReport):
    status: Literal["ok"]
    version: str
    model: str
