from datetime import UTC, datetime

from fastapi import APIRouter

from homer_core.api.deps import ConnectorDep, CurrentUser, RuntimeDep, SettingsDep
from homer_core.services.google_account import GoogleStatus, live_status, local_status

router = APIRouter(prefix="/api/google", tags=["google"])


@router.get("/status")
async def status(
    user: CurrentUser, settings: SettingsDep, runtime: RuntimeDep, connector: ConnectorDep
) -> GoogleStatus:
    found = await live_status(settings, runtime.manager, datetime.now(UTC))
    return found.model_copy(update={"connecting": connector.running})


@router.post("/connect", status_code=202)
def connect(user: CurrentUser, settings: SettingsDep, connector: ConnectorDep) -> GoogleStatus:
    connector.start(settings)
    return local_status(settings, datetime.now(UTC)).model_copy(update={"connecting": True})
