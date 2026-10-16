from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from pydantic_ai import RunContext
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.usage import RunUsage

from achilles_core.agent.tools import build_core_toolset
from achilles_core.agent.toolsets import MAX_TOOLS, TOOLSETS, build_toolsets
from achilles_core.mcp.manager import HIDDEN_TOOLS, SERVERS, McpManager
from achilles_mcp_google.server import build as build_google
from achilles_mcp_google.settings import Settings as GoogleSettings
from achilles_mcp_search.server import mcp as search_server
from achilles_mcp_system.server import mcp as system_server

UNUSED_URL = "http://127.0.0.1:1"


def real_servers(tmp_path: Path) -> dict[str, FastMCP]:
    google = build_google(GoogleSettings(home=tmp_path, api_base=UNUSED_URL, token_url=UNUSED_URL))
    return {"google": google, "search": search_server, "system": system_server}


async def names(toolset: AbstractToolset[None]) -> set[str]:
    ctx = RunContext(deps=None, model=TestModel(), usage=RunUsage())
    return set(await toolset.get_tools(ctx))


@pytest.fixture
async def manager(tmp_path: Path) -> AsyncIterator[McpManager]:
    servers = real_servers(tmp_path)
    assert set(servers) == set(SERVERS)
    manager = McpManager(
        {name: MCPToolset(Client(server), id=name) for name, server in servers.items()}
    )
    await manager.start()
    yield manager
    await manager.stop()


async def test_curated_names_exist_on_the_real_servers(manager: McpManager) -> None:
    exposed = set()
    for toolset in manager.toolsets.values():
        exposed |= await names(toolset)
    exposed |= await names(build_core_toolset())
    for name, tools in TOOLSETS.items():
        assert set(tools) <= exposed, name
        assert len(tools) <= MAX_TOOLS, name


async def test_execute_and_health_are_hidden(manager: McpManager) -> None:
    visible = await names(manager.model_toolset())
    assert visible.isdisjoint(HIDDEN_TOOLS)
    assert {"mail_send", "web_search", "parse_datetime"} <= visible
    filtered = build_toolsets(manager.model_toolset(), build_core_toolset())
    for name, toolset in filtered.items():
        assert await names(toolset) == set(TOOLSETS[name]), name
