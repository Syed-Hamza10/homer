from fastmcp import FastMCP

from achilles_mcp_google.auth import TokenStore
from achilles_mcp_google.client import GoogleClient
from achilles_mcp_google.settings import Settings
from achilles_mcp_google.tools import GoogleTools, register


def build(settings: Settings) -> FastMCP:
    mcp = FastMCP("achilles-google", instructions="Mail, calendar and contacts for one user.")
    client = GoogleClient(settings, TokenStore(settings.token_path))
    register(mcp, GoogleTools(client))
    return mcp


def main() -> None:
    build(Settings.from_env()).run(show_banner=False)
