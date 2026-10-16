import secrets
import time
from collections import deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from itsdangerous import BadSignature, TimestampSigner
from starlette.responses import JSONResponse

from achilles_core.config import Settings, own_origins
from achilles_core.services.errors import DomainError

SESSION_COOKIE = "achilles_session"
SESSION_MAX_AGE = 7 * 24 * 3600
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class Unauthenticated(DomainError):
    status_code = 401


class InvalidPassphrase(DomainError):
    status_code = 401


class TooManyAttempts(DomainError):
    status_code = 429


class LoginLimiter:
    def __init__(self, limit: int = 5, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.failures: deque[float] = deque()

    def _prune(self, now: float) -> None:
        while self.failures and now - self.failures[0] >= self.window_seconds:
            self.failures.popleft()

    def check(self) -> None:
        self._prune(time.monotonic())
        if len(self.failures) >= self.limit:
            raise TooManyAttempts("too many failed attempts, try again later")

    def record_failure(self) -> None:
        self.failures.append(time.monotonic())

    def reset(self) -> None:
        self.failures.clear()


def verify_passphrase(settings: Settings, passphrase: str, limiter: LoginLimiter) -> None:
    limiter.check()
    expected = settings.achilles_passphrase.get_secret_value()
    if not secrets.compare_digest(passphrase.encode(), expected.encode()):
        limiter.record_failure()
        raise InvalidPassphrase("wrong passphrase")
    limiter.reset()


def sign_session(secret: str, user_id: int) -> str:
    return TimestampSigner(secret).sign(str(user_id)).decode()


def read_session(secret: str, token: str) -> int | None:
    try:
        return int(TimestampSigner(secret).unsign(token, max_age=SESSION_MAX_AGE))
    except (BadSignature, ValueError):
        return None


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=False,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="strict")


async def origin_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    is_api = request.url.path.startswith("/api")
    if is_api and request.method not in SAFE_METHODS:
        origin = request.headers.get("origin")
        if origin not in own_origins(request.app.state.settings):
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)
    return await call_next(request)
