from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from pydantic_ai import RunContext
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from homer_core.mcp.manager import SERVERS, McpManager
from homer_mcp_google.server import build as build_google
from homer_mcp_google.settings import Settings as GoogleSettings
from homer_mcp_search.server import mcp as search_server
from homer_mcp_system.server import mcp as system_server

UNUSED_URL = "http://127.0.0.1:1"
JOB_TOOLS = {
    "google": {
        "contacts_search",
        "mail_search",
        "mail_draft",
        "mail_draft_update",
        "cal_list",
        "cal_find_free_slots",
        "cal_create",
        "execute",
    },
    "search": {"web_search", "fetch_page"},
}
TIMEZONE_TOOLS = {"cal_find_free_slots", "cal_create"}


def real_servers(tmp_path: Path) -> dict[str, FastMCP]:
    google = build_google(GoogleSettings(home=tmp_path, api_base=UNUSED_URL, token_url=UNUSED_URL))
    return {"google": google, "search": search_server, "system": system_server}


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


async def test_every_tool_the_jobs_call_exists_on_the_real_servers(manager: McpManager) -> None:
    ctx = RunContext(deps=None, model=TestModel(), usage=RunUsage())
    for server, wanted in JOB_TOOLS.items():
        tools = await manager.toolsets[server].get_tools(ctx)
        assert wanted <= set(tools), server
        for name in TIMEZONE_TOOLS & wanted:
            assert "timezone" in tools[name].tool_def.parameters_json_schema["properties"], name
