from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from homer_core.agent.runtime import Runtime
from homer_core.auth import SESSION_COOKIE, LoginLimiter, Unauthenticated, read_session
from homer_core.config import Settings
from homer_core.db.models import User
from homer_core.db.session import get_session
from homer_core.services.google_account import Connector
from homer_core.services.scheduler import Scheduler
from homer_net import AllowlistedClient


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_scheduler(request: Request) -> Scheduler:
    return request.app.state.scheduler


def get_http_client(request: Request) -> AllowlistedClient:
    return request.app.state.http_client


def get_connector(request: Request) -> Connector:
    return request.app.state.google_connector


def get_limiter(request: Request) -> LoginLimiter:
    return request.app.state.limiter


def get_secret(request: Request) -> str:
    return request.app.state.session_secret


def current_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    secret: Annotated[str, Depends(get_secret)],
) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user_id = read_session(secret, token) if token else None
    user = session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise Unauthenticated("login required")
    return user


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]
RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
HttpClientDep = Annotated[AllowlistedClient, Depends(get_http_client)]
SchedulerDep = Annotated[Scheduler, Depends(get_scheduler)]
ConnectorDep = Annotated[Connector, Depends(get_connector)]
LimiterDep = Annotated[LoginLimiter, Depends(get_limiter)]
SecretDep = Annotated[str, Depends(get_secret)]
CurrentUser = Annotated[User, Depends(current_user)]
