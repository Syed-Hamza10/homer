import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from homer_mcp_google.auth import TokenStore
from homer_mcp_google.client import GoogleClient
from homer_mcp_google.settings import Settings
from homer_mcp_google.tools import GoogleTools, register


def build(settings: Settings) -> FastMCP:
    client = GoogleClient(settings, TokenStore(settings.token_path))
    tools = GoogleTools(client)

    @asynccontextmanager
    async def lifespan(_: FastMCP) -> AsyncIterator[None]:
        warming = asyncio.create_task(tools.warm_up()) if settings.token_path.exists() else None
        yield
        if warming is not None:
            warming.cancel()

    mcp = FastMCP(
        "homer-google", instructions="Mail, calendar and contacts for one user.", lifespan=lifespan
    )
    register(mcp, tools)
    return mcp


def main() -> None:
    build(Settings.from_env()).run(show_banner=False)
