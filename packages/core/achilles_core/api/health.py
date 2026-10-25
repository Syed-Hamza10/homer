from fastapi import APIRouter, Request

from achilles_core import __version__
from achilles_core.api.deps import HttpClientDep, SessionDep, SettingsDep
from achilles_core.api.schemas.health import HealthResponse
from achilles_core.services import health as health_service
from achilles_core.services.rules import ClientRules, get_rules
from achilles_core.services.users import first_user

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(
    request: Request, settings: SettingsDep, client: HttpClientDep, session: SessionDep
) -> HealthResponse:
    user = first_user(session)
    rules = get_rules(session, user.id) if user else ClientRules()
    model = request.app.state.model
    report = await health_service.check(
        settings, client, model.model_name, request.app.state.runtime.manager, rules
    )
    return HealthResponse(
        status="ok", version=__version__, model=model.model_name, **report.model_dump()
    )
