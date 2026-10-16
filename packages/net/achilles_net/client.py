import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from achilles_net.allowlist import Allowlist, BlockedHostError, host_key

STARTED_AT = "achilles_started_at"


@dataclass(frozen=True)
class OutboundCall:
    method: str
    host: str
    path: str
    status: int | None
    duration_ms: int


LogFn = Callable[[OutboundCall], Awaitable[None] | None]


def no_log(call: OutboundCall) -> None:
    return None


class AllowlistedClient(httpx.AsyncClient):
    def __init__(self, allowlist: Allowlist, log: LogFn = no_log, **kwargs: Any) -> None:
        kwargs.setdefault("follow_redirects", True)
        super().__init__(**kwargs)
        self._allowlist = allowlist
        self._log = log
        hooks = self.event_hooks
        self.event_hooks = {
            "request": [self._check, *hooks["request"]],
            "response": [*hooks["response"], self._record],
        }

    async def _check(self, request: httpx.Request) -> None:
        url = str(request.url)
        try:
            self._allowlist.check(url)
        except BlockedHostError as error:
            await self._emit(request, error.host, status=None, duration_ms=0)
            raise
        request.extensions[STARTED_AT] = time.perf_counter()

    async def _record(self, response: httpx.Response) -> None:
        request = response.request
        started_at = request.extensions[STARTED_AT]
        duration_ms = round((time.perf_counter() - started_at) * 1000)
        await self._emit(request, host_key(str(request.url)), response.status_code, duration_ms)

    async def _emit(
        self, request: httpx.Request, host: str, status: int | None, duration_ms: int
    ) -> None:
        call = OutboundCall(request.method, host, request.url.path, status, duration_ms)
        result = self._log(call)
        if inspect.isawaitable(result):
            await result
