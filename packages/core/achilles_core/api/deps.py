from typing import Annotated

from fastapi import Depends, Request
from pydantic_ai import Agent
from sqlmodel import Session

from achilles_core.agent.agent import Deps
from achilles_core.auth import SESSION_COOKIE, LoginLimiter, Unauthenticated, read_session
from achilles_core.config import Settings
from achilles_core.db.models import User
from achilles_core.db.session import get_session
from achilles_net import AllowlistedClient


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_agent(request: Request) -> Agent[Deps, str]:
    return request.app.state.agent


def get_http_client(request: Request) -> AllowlistedClient:
    return request.app.state.http_client


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
AgentDep = Annotated[Agent[Deps, str], Depends(get_agent)]
HttpClientDep = Annotated[AllowlistedClient, Depends(get_http_client)]
LimiterDep = Annotated[LoginLimiter, Depends(get_limiter)]
SecretDep = Annotated[str, Depends(get_secret)]
CurrentUser = Annotated[User, Depends(current_user)]
