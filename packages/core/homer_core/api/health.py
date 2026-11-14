from fastapi import APIRouter, Request, status

from homer_core import __version__
from homer_core.api.deps import (
    CurrentUser,
    HttpClientDep,
    RuntimeDep,
    SessionDep,
    SettingsDep,
)
from homer_core.api.schemas.health import HealthResponse
from homer_core.services import health as health_service
from homer_core.services.ollama import warm_up
from homer_core.services.rules import ClientRules, get_rules
from homer_core.services.users import first_user

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


@router.post("/model/warm", status_code=status.HTTP_204_NO_CONTENT)
async def warm_model(
    request: Request,
    user: CurrentUser,
    settings: SettingsDep,
    client: HttpClientDep,
    runtime: RuntimeDep,
) -> None:
    model = request.app.state.model.model_name
    await warm_up(client, settings.ollama_url, model, runtime.intents)
