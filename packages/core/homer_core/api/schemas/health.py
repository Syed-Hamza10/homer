from typing import Literal

from homer_core.services.health import HealthReport


class HealthResponse(HealthReport):
    status: Literal["ok"]
    version: str
    model: str
