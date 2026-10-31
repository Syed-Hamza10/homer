import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastmcp import Client

from achilles_mcp_google.auth import TokenStore
from achilles_mcp_google.client import GoogleClient
from achilles_mcp_google.settings import Settings
from achilles_mcp_google.tools import TOOL_NAMES
from achilles_net import BlockedHostError

pytestmark = pytest.mark.asyncio(loop_scope="session")
Spawn = Callable[..., Client]


async def call(mcp: Client, name: str, **arguments: Any) -> dict[str, Any]:
    result = await mcp.call_tool(name, arguments)
    assert isinstance(result.data, dict)
    return result.data


def this_week() -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday, monday + timedelta(days=7)


async def test_health_and_tool_list(mcp: Client) -> None:
    tools = await mcp.list_tools()
    assert sorted(t.name for t in tools) == sorted(TOOL_NAMES)
    for tool in tools:
        assert tool.description and tool.description.count(". ") <= 1
    health = await call(mcp, "health")
    assert health["ok"] is True and health["version"]


async def test_mail_search_wraps_bodies(mcp: Client, sim: httpx.Client) -> None:
    found = await call(mcp, "mail_search", query="from:maya", max_results=5)
    messages = found["messages"]
    assert len(messages) == 2
    newest = messages[0]
    assert newest["subject"].startswith("Re: Kickoff")
    assert newest["body"].startswith("<untrusted>") and newest["body"].endswith("</untrusted>")
    assert "kickoff slots" in newest["body"] and "<b>" not in newest["body"]
    assert "Clients" in newest["labels"]
    assert newest["metadata"]["label_ids"] and newest["metadata"]["history_id"]
    one = await call(mcp, "mail_get", message_id="msg_009")
    assert "alert(1)" not in one["body"] and "Proposal" in one["body"]
    thread = await call(mcp, "mail_thread", thread_id="thr_001")
    assert [m["id"] for m in thread["messages"]] == ["msg_001", "msg_002", "msg_003"]


async def test_draft_send_needs_approval_then_execute_sends(mcp: Client, sim: httpx.Client) -> None:
    before = sim.get("/_sim/state").json()
    cursor = (await call(mcp, "mail_changes_since"))["cursor"]
    draft = await call(
        mcp,
        "mail_draft",
        to="maya.lindqvist@example.test",
        subject="Re: Kickoff for the Northwind website redesign",
        body="Thursday 14:00 works for us.",
        thread_id="thr_001",
    )
    assert draft["draft_id"] and draft["thread_id"] == "thr_001"
    pending = await call(mcp, "mail_send", draft_id=draft["draft_id"])
    assert pending["approval_required"] is True
    assert pending["action"] == "mail_send"
    assert pending["payload"] == {"draft_id": draft["draft_id"]}
    assert "maya.lindqvist@example.test" in pending["preview"]
    assert "Thursday 14:00" in pending["preview"]
    assert sim.get("/_sim/state").json()["sent"] == before["sent"]
    done = await call(mcp, "execute", action="mail_send", payload=pending["payload"])
    assert done["sent"] is True and done["thread_id"] == "thr_001"
    after = sim.get("/_sim/state").json()
    assert after["sent"] == before["sent"] + 1 and after["drafts"] == 0
    changes = await call(mcp, "mail_changes_since", cursor=cursor)
    assert done["message_id"] in changes["changed_ids"]
    assert int(changes["cursor"]) > int(cursor)
    assert (await call(mcp, "mail_changes_since", cursor=changes["cursor"]))["changed_ids"] == []


async def test_send_with_unknown_draft_id_lists_recent_drafts(
    mcp: Client, sim: httpx.Client
) -> None:
    ids = []
    for to, subject in [("a@example.test", "First"), ("b@example.test", "Second")]:
        ids.append((await call(mcp, "mail_draft", to=to, subject=subject, body="x"))["draft_id"])
    missing = await call(mcp, "mail_send", draft_id="1")
    assert missing["error"] == "draft_not_found" and missing["draft_id"] == "1"
    assert missing["drafts"] == [
        {"draft_id": ids[1], "subject": "Second", "to": "b@example.test"},
        {"draft_id": ids[0], "subject": "First", "to": "a@example.test"},
    ]
    assert sim.get("/_sim/state").json()["sent"] == 3
    assert (await call(mcp, "mail_send", draft_id=ids[0]))["approval_required"] is True


async def test_stale_cursor_returns_a_fresh_cursor_and_no_gap(
    mcp: Client, sim: httpx.Client
) -> None:
    old = (await call(mcp, "mail_changes_since"))["cursor"]
    await call(mcp, "mail_label", message_id="msg_004", add=["Later"], remove=[])
    sim.post("/_sim/expire-history").raise_for_status()
    stale = await call(mcp, "mail_changes_since", cursor=old)
    assert stale["stale"] is True and stale["changed_ids"] == []
    assert int(stale["cursor"]) > int(old)
    fresh = await call(mcp, "mail_changes_since", cursor=stale["cursor"])
    assert fresh == {"cursor": stale["cursor"], "changed_ids": [], "stale": False}


async def test_label_and_archive(mcp: Client, sim: httpx.Client) -> None:
    labelled = await call(mcp, "mail_label", message_id="msg_011", add=["Urgent"], remove=[])
    assert "Urgent" in labelled["labels"]
    archived = await call(mcp, "mail_archive", message_id="msg_011")
    assert "INBOX" not in archived["labels"] and "Urgent" in archived["labels"]


async def test_execute_runs_approved_label_and_archive(mcp: Client, sim: httpx.Client) -> None:
    labels_before = sim.get("/_sim/state").json()["labels"]
    labelled = await call(
        mcp,
        "execute",
        action="mail_label",
        payload={"message_id": "msg_005", "add": ["Follow up"], "remove": ["Invoices"]},
    )
    assert "Follow up" in labelled["labels"] and "Invoices" not in labelled["labels"]
    archived = await call(mcp, "execute", action="mail_archive", payload={"message_id": "msg_005"})
    assert "INBOX" not in archived["labels"] and "Follow up" in archived["labels"]
    assert sim.get("/_sim/state").json()["labels"] == labels_before


async def test_calendar_list_and_free_slots(mcp: Client, sim: httpx.Client) -> None:
    monday, sunday = this_week()
    listing = await call(mcp, "cal_list", start=monday.isoformat(), end=sunday.isoformat())
    assert [e["title"] for e in listing["events"]][:2] == [
        "Weekly planning",
        "Northwind redesign kickoff prep",
    ]
    assert listing["events"][1]["attendees"] == ["maya.lindqvist@example.test"]
    thursday = monday + timedelta(days=3)
    slots = (
        await call(
            mcp,
            "cal_find_free_slots",
            start=thursday.isoformat(),
            end=(thursday + timedelta(days=2)).isoformat(),
            duration_minutes=60,
            working_hours="09:00-17:00",
        )
    )["slots"]
    assert [(s["start"][5:16], s["end"][11:16]) for s in slots] == [
        (f"{thursday:%m-%dT}12:00", "13:00"),
        (f"{thursday:%m-%dT}16:00", "17:00"),
        (f"{thursday + timedelta(days=1):%m-%dT}09:00", "10:00"),
    ]
    weekend = monday + timedelta(days=5)
    none = await call(
        mcp,
        "cal_find_free_slots",
        start=weekend.isoformat(),
        end=(weekend + timedelta(days=2)).isoformat(),
    )
    assert none["slots"] == []


async def test_calendar_write_tools_need_approval(mcp: Client, sim: httpx.Client) -> None:
    monday, _ = this_week()
    start = monday + timedelta(days=4, hours=14)
    end = start + timedelta(hours=1)
    pending = await call(
        mcp,
        "cal_create",
        title="Northwind kickoff",
        start=start.isoformat(),
        end=end.isoformat(),
        attendees=["maya.lindqvist@example.test"],
    )
    assert pending["approval_required"] and pending["action"] == "cal_create"
    assert "Northwind kickoff" in pending["preview"]
    assert sim.get("/_sim/state").json()["events"] == 6
    created = await call(mcp, "execute", action="cal_create", payload=pending["payload"])
    assert created["title"] == "Northwind kickoff"
    assert created["attendees"] == ["maya.lindqvist@example.test"]
    assert sim.get("/_sim/state").json()["events"] == 7

    update = await call(mcp, "cal_update", event_id=created["id"], title="Kickoff (moved)")
    assert update["action"] == "cal_update" and "Kickoff (moved)" in update["preview"]
    updated = await call(mcp, "execute", action="cal_update", payload=update["payload"])
    assert updated["title"] == "Kickoff (moved)"

    delete = await call(mcp, "cal_delete", event_id=created["id"])
    assert delete["action"] == "cal_delete" and "Kickoff (moved)" in delete["preview"]
    assert sim.get("/_sim/state").json()["events"] == 7
    assert (await call(mcp, "execute", action="cal_delete", payload=delete["payload"]))["deleted"]
    assert sim.get("/_sim/state").json()["events"] == 6

    bad = await call(mcp, "cal_create", title="x", start=end.isoformat(), end=start.isoformat())
    assert bad["error"] == "invalid_argument"
    unknown = await call(mcp, "execute", action="mail_delete_everything", payload={})
    assert unknown["error"] == "invalid_argument"


async def test_mail_profile_returns_the_account_address(mcp: Client) -> None:
    assert await call(mcp, "mail_profile") == {"email": "jordan.reyes@example.test"}


async def test_contacts_search(mcp: Client) -> None:
    found = await call(mcp, "contacts_search", query="keller")
    assert found["contacts"] == [{"name": "Tomas Keller", "email": "tomas.keller@example.test"}]
    assert (await call(mcp, "contacts_search", query="nobody"))["contacts"] == []


async def test_outbound_log_rows(mcp: Client, home: Path) -> None:
    await call(mcp, "contacts_search", query="maya")
    rows = (
        sqlite3.connect(home / "data" / "achilles.db")
        .execute(
            "SELECT method, host, path, status FROM outbound_log WHERE path LIKE '/v1/people%'"
        )
        .fetchall()
    )
    assert rows
    method, host, path, status = rows[-1]
    assert method == "GET" and host.startswith("127.0.0.1:") and status == 200
    assert path == "/v1/people:searchContacts"


async def test_refreshes_stale_token_once(
    sim: httpx.Client, tmp_path: Path, write_token: Callable[..., Path], spawn: Spawn
) -> None:
    token_path = write_token(tmp_path, "stale")
    async with spawn(tmp_path) as client:
        found = await call(client, "contacts_search", query="maya")
    assert found["contacts"][0]["email"] == "maya.lindqvist@example.test"
    assert sim.get("/_sim/state").json()["token_requests"] == 1
    assert '"stale"' not in token_path.read_text()
    assert oct(token_path.stat().st_mode)[-3:] == "600"


async def test_not_connected_without_token(tmp_path: Path, spawn: Spawn) -> None:
    async with spawn(tmp_path) as client:
        result = await call(client, "mail_search", query="anything")
    assert result == {"error": "google_not_connected"}


async def test_refuses_host_outside_allowlist(
    sim_url: str,
    tmp_path: Path,
    write_token: Callable[..., Path],
    create_outbound_log: Callable[[Path], Path],
    free_port: Callable[[], int],
) -> None:
    write_token(tmp_path)
    db = create_outbound_log(tmp_path)
    settings = Settings(home=tmp_path, api_base=sim_url, token_url=f"{sim_url}/token")
    client = GoogleClient(settings, TokenStore(settings.token_path))
    other_port = free_port()
    with pytest.raises(BlockedHostError):
        await client.http.get(f"http://127.0.0.1:{other_port}/v1/people:searchContacts?query=x")
    allowed = await client.get("/v1/people:searchContacts", query="maya", readMask="names")
    assert allowed["results"]
    rows = sqlite3.connect(db).execute("SELECT host, status FROM outbound_log").fetchall()
    assert rows == [(f"127.0.0.1:{other_port}", None), (sim_url.removeprefix("http://"), 200)]


async def test_server_only_ever_contacted_the_simulator(
    mcp: Client, home: Path, sim_url: str
) -> None:
    hosts = (
        sqlite3.connect(home / "data" / "achilles.db")
        .execute("SELECT DISTINCT host FROM outbound_log")
        .fetchall()
    )
    assert hosts == [(sim_url.removeprefix("http://"),)]
