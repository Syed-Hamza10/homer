from fastapi import APIRouter, Request

from achilles_core import __version__
from achilles_core.api.deps import HttpClientDep, SessionDep, SettingsDep
from achilles_core.api.schemas.health import HealthResponse
from achilles_core.mcp.manager import SERVERS
from achilles_core.services import briefs
from achilles_core.services.ollama import model_tags
from achilles_core.services.rules import ClientRules, get_rules
from achilles_core.services.users import first_user

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(
    request: Request, settings: SettingsDep, client: HttpClientDep, session: SessionDep
) -> HealthResponse:
    try:
        await model_tags(client, settings.ollama_url)
        ollama = "ok"
    except Exception:
        ollama = "down"
    manager = request.app.state.runtime.manager
    user = first_user(session)
    rules = get_rules(session, user.id) if user else ClientRules()
    account = await briefs.account_email(manager) if rules.email_to_self else None
    return HealthResponse(
        status="ok",
        version=__version__,
        ollama=ollama,
        model=request.app.state.model.model_name,
        servers={name: "ok" if name in manager.toolsets else "down" for name in SERVERS},
        self_email=briefs.self_email_status(rules, account),
    )
