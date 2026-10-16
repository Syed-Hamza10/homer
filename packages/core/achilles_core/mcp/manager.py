import shutil
import sys
from pathlib import Path
from typing import Any

import structlog
from fastmcp.client import Client
from fastmcp.client.transports import StdioTransport
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset, CombinedToolset, FilteredToolset

from achilles_core.config import Settings
from achilles_core.services.errors import DomainError

log = structlog.get_logger(__name__)

SERVERS = ("google", "search", "system")
EXECUTOR_TOOL = "execute"
HIDDEN_TOOLS = frozenset({EXECUTOR_TOOL, "health"})
INIT_TIMEOUT = 30.0


class ServerUnavailable(DomainError):
    status_code = 503


class ExecuteFailed(Exception):
    """The server ran the action and reported a clear failure; nothing was sent."""


def server_env(settings: Settings) -> dict[str, str]:
    return {
        "ACHILLES_HOME": str(settings.achilles_home),
        "GOOGLE_API_BASE": settings.google_api_base,
        "GOOGLE_TOKEN_URL": settings.google_token_url,
        "WEB_SEARCH": str(settings.web_search).lower(),
    }


def find_executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    candidate = Path(sys.executable).parent / name
    return str(candidate) if candidate.is_file() else None


def stdio_toolset(name: str, command: str, env: dict[str, str]) -> MCPToolset[Any]:
    transport = StdioTransport(command, [], env=env)
    client = Client(transport, init_timeout=INIT_TIMEOUT)
    return MCPToolset(client, id=name, tool_error_behavior="failed")


class McpManager:
    def __init__(self, toolsets: dict[str, MCPToolset[Any]]) -> None:
        self.toolsets = toolsets

    @classmethod
    def discover(cls, settings: Settings) -> "McpManager":
        env = server_env(settings)
        toolsets: dict[str, MCPToolset[Any]] = {}
        for name in SERVERS:
            command = find_executable(f"achilles-mcp-{name}")
            if command is None:
                log.warning("mcp_server_missing", server=name)
                continue
            toolsets[name] = stdio_toolset(name, command, env)
        return cls(toolsets)

    async def start(self) -> None:
        for name, toolset in list(self.toolsets.items()):
            try:
                await toolset.__aenter__()
                log.info("mcp_server_started", server=name)
            except Exception:
                log.exception("mcp_server_failed", server=name)
                del self.toolsets[name]

    async def stop(self) -> None:
        for toolset in self.toolsets.values():
            await toolset.__aexit__(None, None, None)

    def model_toolset(self) -> AbstractToolset[Any]:
        visible = [
            FilteredToolset(toolset, lambda ctx, tool: tool.name not in HIDDEN_TOOLS)
            for toolset in self.toolsets.values()
        ]
        return CombinedToolset(visible)

    async def call(self, server: str, tool: str, args: dict[str, Any]) -> Any:
        toolset = self.toolsets.get(server)
        if toolset is None:
            raise ServerUnavailable(f"server {server} is not running")
        try:
            return await toolset.direct_call_tool(tool, args)
        except ToolFailed as error:
            raise ExecuteFailed(str(error)) from error
