from datetime import datetime

from fastapi import APIRouter, Query

from homer_core.api.deps import CurrentUser, SessionDep, SettingsDep
from homer_core.services import activity, google_account

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("")
def timeline(
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    before: datetime | None = None,
    kind: activity.ActivityFilter = "all",
    limit: int = Query(default=activity.PAGE_SIZE, ge=1, le=100),
) -> activity.ActivityPage:
    connected_at = google_account.consent_time(google_account.token_path(settings))
    return activity.timeline(session, user, connected_at, before, kind, limit)
