from typing import Any

from homer_mcp_google.auth import TokenStore
from homer_mcp_google.settings import Settings
from homer_net import Allowlist, AllowlistedClient, SqliteLog
from homer_net.allowlist import host_key
from homer_net.client import LogFn, no_log

TIMEOUT = 30.0


class GoogleError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class GoogleClient:
    def __init__(self, settings: Settings, store: TokenStore, log: LogFn | None = None) -> None:
        """Logs to the core database when it exists unless a log callable is given."""
        self.settings = settings
        self.store = store
        allowlist = Allowlist({host_key(settings.api_base), host_key(settings.token_url)})
        if log is None:
            log = SqliteLog(settings.db_path) if settings.db_path.exists() else no_log
        self.http = AllowlistedClient(allowlist, log=log, timeout=TIMEOUT)

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        token = self.store.load()
        response = await self._send(method, path, token["token"], params, json)
        if response.status_code == 401:
            token = await self._refresh(token)
            response = await self._send(method, path, token["token"], params, json)
        if response.status_code >= 400:
            raise GoogleError(response.status_code, _error_message(response))
        return response.json() if response.content else {}

    async def _send(
        self,
        method: str,
        path: str,
        access_token: str,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
    ) -> Any:
        return await self.http.request(
            method,
            f"{self.settings.api_base}{path}",
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def _refresh(self, token: dict[str, Any]) -> dict[str, Any]:
        response = await self.http.post(
            self.settings.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
                "client_id": token.get("client_id", ""),
                "client_secret": token.get("client_secret", ""),
            },
        )
        if response.status_code >= 400:
            raise GoogleError(response.status_code, _error_message(response))
        refreshed = {**token, "token": response.json()["access_token"]}
        self.store.save(refreshed)
        return refreshed

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return await self.request("POST", path, json=json)

    async def patch(self, path: str, json: dict[str, Any]) -> Any:
        return await self.request("PATCH", path, json=json)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)


def _error_message(response: Any) -> str:
    try:
        return response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return response.text[:200]
