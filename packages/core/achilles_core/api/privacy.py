from fastapi import APIRouter

from achilles_core.api.deps import CurrentUser, SessionDep, SettingsDep
from achilles_core.api.schemas.privacy import HostOut, HostsResponse, UsageResponse
from achilles_core.services.privacy import host_usage, token_usage

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


@router.get("/hosts")
def hosts(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> HostsResponse:
    return HostsResponse(
        hosts=[HostOut.model_validate(item, from_attributes=True) for item in host_usage(session)],
        web_search=settings.web_search,
    )


@router.get("/usage")
def usage(user: CurrentUser, session: SessionDep) -> UsageResponse:
    return UsageResponse.model_validate(token_usage(session, user), from_attributes=True)
