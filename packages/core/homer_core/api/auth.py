from fastapi import APIRouter, Response, status

from homer_core.api.deps import (
    CurrentUser,
    LimiterDep,
    SecretDep,
    SessionDep,
    SettingsDep,
)
from homer_core.api.schemas.auth import LoginRequest, MeResponse
from homer_core.auth import (
    Unauthenticated,
    clear_session_cookie,
    set_session_cookie,
    sign_session,
    verify_passphrase,
)
from homer_core.services.users import first_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(
    body: LoginRequest,
    settings: SettingsDep,
    limiter: LimiterDep,
    secret: SecretDep,
    session: SessionDep,
) -> Response:
    verify_passphrase(settings, body.passphrase, limiter)
    user = first_user(session)
    if user is None or user.id is None:
        raise Unauthenticated("no user yet")
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_session_cookie(response, sign_session(secret, user.id))
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response


@router.get("/me")
def me(user: CurrentUser) -> MeResponse:
    return MeResponse(user_id=user.id, name=user.name)
