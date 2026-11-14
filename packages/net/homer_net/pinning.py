from collections.abc import Awaitable, Callable
from typing import Any

import httpx

PinFn = Callable[[str], Awaitable[str]]


class PinnedTransport(httpx.AsyncHTTPTransport):
    """Resolves each hostname once through `pin`, then connects to that address.

    The original hostname stays in the Host header and is used for TLS SNI and certificate
    checks, so a second DNS answer can never change where the connection goes.
    """

    def __init__(self, pin: PinFn, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pin = pin
        self.pins: dict[str, str] = {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host not in self.pins:
            self.pins[host] = await self._pin(host)
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=self.pins[host]),
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": host},
        )
        return await super().handle_async_request(pinned)
