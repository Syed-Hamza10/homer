from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from homer_core.config import Settings
from homer_core.db.models import utcnow
from homer_core.mcp.manager import SERVERS, McpManager
from homer_core.services import briefs
from homer_core.services.briefs import SelfEmailStatus
from homer_core.services.ollama import model_tags
from homer_core.services.rules import ClientRules
from homer_net import AllowlistedClient

Status = Literal["ok", "down"]


class HealthReport(BaseModel):
    ollama: Status
    model_pulled: Status
    servers: dict[str, Status]
    self_email: SelfEmailStatus
    checked_at: datetime

    @property
    def problems(self) -> list[str]:
        down = [name for name, status in self.servers.items() if status == "down"]
        found = [f"server {name}" for name in down]
        if self.ollama == "down":
            found.append("ollama")
        elif self.model_pulled == "down":
            found.append("model")
        if self.self_email in ("mismatch", "unknown"):
            found.append(f"self_email {self.self_email}")
        return found


async def check(
    settings: Settings,
    client: AllowlistedClient,
    model_name: str,
    manager: McpManager,
    rules: ClientRules,
) -> HealthReport:
    try:
        tags = await model_tags(client, settings.ollama_url)
        ollama: Status = "ok"
        model_pulled: Status = "ok" if model_name in tags else "down"
    except Exception:
        ollama = model_pulled = "down"
    account = await briefs.account_email(manager) if rules.email_to_self else None
    return HealthReport(
        ollama=ollama,
        model_pulled=model_pulled,
        servers={name: "ok" if name in manager.toolsets else "down" for name in SERVERS},
        self_email=briefs.self_email_status(rules, account),
        checked_at=utcnow(),
    )
