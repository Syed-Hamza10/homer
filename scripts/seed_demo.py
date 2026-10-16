"""Seeds or wipes the demo mailbox and calendar on the simulator or the connected Google account."""

import asyncio
import json
import sys
import tempfile
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Protocol

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_data import (  # noqa: E402
    EVENTS,
    LABELS,
    MARKER,
    THREADS,
    event_body,
    is_demo_event,
    label_names,
    raw_message,
)

from achilles_mcp_google.auth import TokenStore  # noqa: E402
from achilles_mcp_google.client import GoogleClient  # noqa: E402
from achilles_mcp_google.settings import Settings  # noqa: E402
from achilles_net.client import no_log  # noqa: E402
from achilles_sim.state import KNOWN_TOKEN  # noqa: E402

GMAIL = "/gmail/v1/users/me"
EVENTS_PATH = "/calendar/v3/calendars/primary/events"
EVENT_WINDOW_DAYS = 14
PAGE_SIZE = 100


class Target(StrEnum):
    sim = "sim"
    google = "google"


class Transport(Protocol):
    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any: ...


class DryRun:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.counter = 0

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        query = "&".join(f"{k}={v}" for k, v in (params or {}).items())
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        summary = f" {_summary(json)}" if json else ""
        print(f"{method} {url}{summary}")
        self.counter += 1
        if method == "POST" and path.endswith("/labels"):
            return {"id": f"Label_dry_{self.counter}", "name": json["name"]}
        if method == "POST" and path.endswith("/messages"):
            return {"id": f"msg_dry_{self.counter}", "threadId": f"thr_dry_{self.counter}"}
        return {}


def _summary(body: dict[str, Any]) -> str:
    shown = {k: v for k, v in body.items() if k != "raw"}
    if "raw" in body:
        shown["raw"] = f"<{len(body['raw'])} chars>"
    return json.dumps(shown)


async def label_ids(client: Transport) -> dict[str, str]:
    listing = await client.request("GET", f"{GMAIL}/labels")
    ids = {label["name"]: label["id"] for label in listing.get("labels", [])}
    for name in [*LABELS, MARKER]:
        if name not in ids:
            created = await client.request("POST", f"{GMAIL}/labels", json={"name": name})
            ids[name] = created["id"]
    return ids


async def demo_messages(client: Transport) -> list[dict[str, Any]]:
    listing = await client.request(
        "GET",
        f"{GMAIL}/messages",
        params={"q": f"label:{MARKER} -in:trash", "maxResults": PAGE_SIZE},
    )
    return listing.get("messages", [])


async def demo_events(client: Transport, now: datetime) -> list[dict[str, Any]]:
    listing = await client.request(
        "GET",
        EVENTS_PATH,
        params={
            "timeMin": (now - timedelta(days=1)).isoformat(),
            "timeMax": (now + timedelta(days=EVENT_WINDOW_DAYS)).isoformat(),
            "singleEvents": "true",
            "maxResults": PAGE_SIZE,
        },
    )
    return [event for event in listing.get("items", []) if is_demo_event(event)]


async def seed_mail(client: Transport, now: datetime) -> None:
    ids = await label_ids(client)
    if await demo_messages(client):
        print("mail: already seeded, skipped")
        return
    count = 0
    for thread in THREADS:
        thread_id: str | None = None
        for index, item in enumerate(thread.messages):
            body: dict[str, Any] = {
                "raw": raw_message(thread, index, now),
                "labelIds": [ids.get(name, name) for name in label_names(thread, item)],
            }
            if thread_id:
                body["threadId"] = thread_id
            inserted = await client.request(
                "POST", f"{GMAIL}/messages", params={"internalDateSource": "dateHeader"}, json=body
            )
            thread_id = inserted.get("threadId")
            count += 1
    print(f"mail: inserted {count} messages in {len(THREADS)} threads")


async def seed_calendar(client: Transport, now: datetime) -> None:
    if await demo_events(client, now):
        print("calendar: already seeded, skipped")
        return
    for event in EVENTS:
        await client.request(
            "POST", EVENTS_PATH, params={"sendUpdates": "none"}, json=event_body(event, now)
        )
    print(f"calendar: inserted {len(EVENTS)} events")


async def wipe(client: Transport, now: datetime) -> None:
    messages = await demo_messages(client)
    for message in messages:
        await client.request("POST", f"{GMAIL}/messages/{message['id']}/trash")
    events = await demo_events(client, now)
    for event in events:
        await client.request("DELETE", f"{EVENTS_PATH}/{event['id']}")
    print(f"wiped: {len(messages)} messages trashed, {len(events)} events deleted")


def google_client(settings: Settings, token_path: Path) -> GoogleClient:
    return GoogleClient(settings, TokenStore(token_path), log=no_log)


def sim_client(sim_url: str) -> GoogleClient:
    home = Path(tempfile.mkdtemp(prefix="achilles-seed-"))
    store = TokenStore(home / "google_token.json")
    store.save({"token": KNOWN_TOKEN, "refresh_token": "sim-refresh-token"})
    settings = Settings(home=home, api_base=sim_url, token_url=f"{sim_url}/token")
    return google_client(settings, store.path)


async def run(client: Transport, wipe_only: bool) -> None:
    now = datetime.now().astimezone()
    if wipe_only:
        await wipe(client, now)
        return
    await seed_mail(client, now)
    await seed_calendar(client, now)


def main(
    target: Annotated[Target, typer.Option(help="sim: a running achilles-sim; google: the token")],
    sim_url: Annotated[
        str, typer.Option(help="Base URL of achilles-sim")
    ] = "http://127.0.0.1:8900",
    wipe: Annotated[bool, typer.Option("--wipe", help="Remove only items with the marker")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print requests only")] = False,
) -> None:
    if target is Target.google:
        settings = Settings.from_env()
        base_url = settings.api_base
        client: Transport = (
            DryRun(base_url) if dry_run else google_client(settings, settings.token_path)
        )
    else:
        base_url = sim_url
        client = DryRun(base_url) if dry_run else sim_client(sim_url)
    print(f"target: {target.value} at {base_url}" + (" (dry run)" if dry_run else ""))
    asyncio.run(run(client, wipe))


if __name__ == "__main__":
    typer.run(main)
