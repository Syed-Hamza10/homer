import os
import socket
import sqlite3
import sys
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

SCHEMA = (
    "CREATE TABLE outbound_log (id INTEGER PRIMARY KEY, ts TEXT, method TEXT, host TEXT, "
    "path TEXT, status INTEGER, duration_ms INTEGER)"
)

Rows = Callable[[], list[tuple]]


def server_client(home: Path, **env: str) -> Client:
    transport = StdioTransport(
        sys.executable,
        ["-m", "achilles_mcp_search.server"],
        env={**os.environ, "ACHILLES_HOME": str(home), **env},
    )
    return Client(transport)


class CountingHandler(BaseHTTPRequestHandler):
    hits = 0

    def do_GET(self) -> None:
        CountingHandler.hits += 1
        body = b"<html><head><title>Local</title></head><body><p>local page</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return None


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / "data").mkdir(parents=True)
    sqlite3.connect(home / "data" / "achilles.db").execute(SCHEMA)
    return home


@pytest.fixture
def outbound_rows(home: Path) -> Rows:
    def rows() -> list[tuple]:
        return (
            sqlite3.connect(home / "data" / "achilles.db")
            .execute("SELECT method, host, path, status FROM outbound_log")
            .fetchall()
        )

    return rows


@pytest.fixture
async def client(home: Path) -> AsyncIterator[Client]:
    async with server_client(home) as c:
        yield c


@pytest.fixture
async def client_search_off(home: Path) -> AsyncIterator[Client]:
    async with server_client(home, WEB_SEARCH="false") as c:
        yield c


@pytest.fixture
def local_server() -> Iterator[str]:
    CountingHandler.hits = 0
    server = HTTPServer(("127.0.0.1", 0), CountingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


@pytest.fixture
def live_network() -> None:
    try:
        socket.create_connection(("html.duckduckgo.com", 443), timeout=3).close()
    except OSError:
        pytest.skip("network unavailable")


async def test_health(client: Client) -> None:
    result = await client.call_tool("health")
    assert result.data["ok"] is True
    assert isinstance(result.data["version"], str)


async def test_tools_are_listed(client: Client) -> None:
    names = {tool.name for tool in await client.list_tools()}
    assert names == {"health", "web_search", "fetch_page"}


async def test_fetch_page_refuses_local_server(client: Client, local_server: str) -> None:
    result = await client.call_tool("fetch_page", {"url": local_server})
    assert result.data == {"error": "private_address"}
    assert CountingHandler.hits == 0


async def test_fetch_page_refuses_private_ip_without_connecting(
    client: Client, outbound_rows: Rows
) -> None:
    result = await client.call_tool("fetch_page", {"url": "http://10.0.0.1/"})
    assert result.data == {"error": "private_address"}
    assert outbound_rows() == []


async def test_fetch_page_rejects_other_schemes(client: Client) -> None:
    result = await client.call_tool("fetch_page", {"url": "file:///etc/hosts"})
    assert result.data == {"error": "invalid_url"}


async def test_web_search_off_short_circuits(
    client_search_off: Client, outbound_rows: Rows
) -> None:
    for name, args in [
        ("web_search", {"query": "anything"}),
        ("fetch_page", {"url": "http://10.0.0.1/"}),
    ]:
        result = await client_search_off.call_tool(name, args)
        assert result.data == {"error": "web_search_off"}
    assert outbound_rows() == []


async def test_rate_limiter_spaces_calls(client: Client) -> None:
    started = time.perf_counter()
    await client.call_tool("fetch_page", {"url": "http://10.0.0.1/"})
    first_done = time.perf_counter()
    await client.call_tool("fetch_page", {"url": "http://10.0.0.2/"})
    second_done = time.perf_counter()
    assert second_done - first_done >= 0.9
    assert second_done - started < 3


@pytest.mark.e2e
@pytest.mark.usefixtures("live_network")
async def test_web_search_live_and_cached(client: Client, outbound_rows: Rows) -> None:
    args = {"query": "python programming language"}
    first = await client.call_tool("web_search", args)
    assert len(first.data["results"]) >= 1
    top = first.data["results"][0]
    assert top["url"].startswith("http")
    assert top["snippet"].startswith("<untrusted>") and top["snippet"].endswith("</untrusted>")
    assert outbound_rows() == [("POST", "html.duckduckgo.com", "/html/", 200)]

    started = time.perf_counter()
    second = await client.call_tool("web_search", args)
    assert time.perf_counter() - started < 0.5
    assert second.data == first.data
    assert len(outbound_rows()) == 1


@pytest.mark.e2e
@pytest.mark.usefixtures("live_network")
async def test_fetch_page_live(client: Client, outbound_rows: Rows) -> None:
    result = await client.call_tool("fetch_page", {"url": "https://example.com/"})
    assert result.data["url"].startswith("https://example.com")
    assert "Example Domain" in result.data["title"]
    assert result.data["text"].startswith("<untrusted>")
    assert outbound_rows() == [("GET", "example.com", "/", 200)]
