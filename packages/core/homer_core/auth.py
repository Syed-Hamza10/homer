import secrets
import time
from collections import deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from itsdangerous import BadSignature, TimestampSigner
from pydantic import SecretStr
from starlette.responses import JSONResponse

from homer_core.config import Settings, own_origins, read_passphrase
from homer_core.services.errors import DomainError

SESSION_COOKIE = "homer_session"
SESSION_MAX_AGE = 7 * 24 * 3600
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class Unauthenticated(DomainError):
    status_code = 401


class InvalidPassphrase(DomainError):
    status_code = 401


class TooManyAttempts(DomainError):
    status_code = 429
    headers = {"Retry-After": "60"}


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


def _matches(given: str, expected: str) -> bool:
    return secrets.compare_digest(given.encode(), expected.encode())


def verify_passphrase(settings: Settings, passphrase: str, limiter: LoginLimiter) -> None:
    """On a mismatch, re-reads .env once so `homer passphrase` works without a restart."""
    limiter.check()
    if not _matches(passphrase, settings.homer_passphrase.get_secret_value()):
        current = read_passphrase(settings.homer_home)
        if current is None or not _matches(passphrase, current):
            limiter.record_failure()
            raise InvalidPassphrase("wrong passphrase")
        settings.homer_passphrase = SecretStr(current)
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
