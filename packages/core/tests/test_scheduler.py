from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp.client import Client
from pydantic_ai.mcp import MCPToolset
from sqlmodel import Session, select

from homer_core.config import Settings
from homer_core.db.models import EmailCache
from homer_core.mcp.manager import McpManager
from homer_core.services.scheduler import CURSOR_KEY, Scheduler
from homer_core.services.store import read_setting
from homer_core.services.users import first_user
from homer_mcp_google.messages import build_raw

from .conftest import sim_google_server


@pytest.fixture
async def sim_manager(tmp_path: Path, sim: FastAPI) -> AsyncIterator[McpManager]:
    server = sim_google_server(tmp_path / "google", sim)
    manager = McpManager(
        {"google": MCPToolset(Client(server), id="google", tool_error_behavior="failed")}
    )
    await manager.start()
    yield manager
    await manager.stop()


def cached_and_cursor(app: FastAPI) -> tuple[int, str | None]:
    with Session(app.state.engine) as session:
        user = first_user(session)
        rows = session.exec(select(EmailCache).where(EmailCache.user_id == user.id)).all()
        return len(rows), read_setting(session, user.id, CURSOR_KEY)


async def test_poll_caches_every_change_and_retries_a_failed_fetch(
    app: FastAPI, settings: Settings, logged_in: TestClient, sim: FastAPI, sim_manager: McpManager
) -> None:
    runtime = SimpleNamespace(manager=sim_manager)
    scheduler = Scheduler(settings, app.state.engine, runtime, app.state.http_client)
    await scheduler.poll_mail()
    _, start = cached_and_cursor(app)
    state = sim.state.sim
    raw = build_raw("me@example.test", "Note", "Hi.", None)
    ids = [state.mailbox.insert(raw, ["INBOX"], None, state.now, False)["id"] for _ in range(60)]
    state.failing_once.add(ids[30])

    await scheduler.poll_mail()
    assert cached_and_cursor(app) == (59, start)

    await scheduler.poll_mail()
    cached, cursor = cached_and_cursor(app)
    assert cached == 60
    assert int(cursor) >= int(start) + 60
