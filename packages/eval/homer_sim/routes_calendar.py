from typing import Any

from fastapi import APIRouter, Response

from homer_sim.deps import Authed, Sim
from homer_sim.events import TIMEZONE

router = APIRouter(prefix="/calendar/v3", dependencies=[Authed])


@router.get("/calendars/primary/events")
def list_events(
    sim: Sim,
    timeMin: str | None = None,
    timeMax: str | None = None,
    maxResults: int = 250,
    singleEvents: bool = False,
    orderBy: str | None = None,
    pageToken: str = "0",
) -> dict[str, Any]:
    events = sim.calendar.between(timeMin, timeMax)
    size = min(maxResults, sim.events_page_size)
    offset = int(pageToken)
    response = {
        "kind": "calendar#events",
        "timeZone": TIMEZONE,
        "items": events[offset : offset + size],
    }
    if offset + size < len(events):
        response["nextPageToken"] = str(offset + size)
    return response


@router.post("/calendars/primary/events", status_code=200)
def insert_event(sim: Sim, body: dict[str, Any], sendUpdates: str | None = None) -> dict[str, Any]:
    event = sim.calendar.insert(body, sim.now)
    sim.record_write("insert", event["id"], sendUpdates, body)
    return event


@router.get("/calendars/primary/events/{event_id}")
def get_event(sim: Sim, event_id: str) -> dict[str, Any]:
    return sim.calendar.get(event_id)


@router.patch("/calendars/primary/events/{event_id}")
def patch_event(
    sim: Sim, event_id: str, body: dict[str, Any], sendUpdates: str | None = None
) -> dict[str, Any]:
    event = sim.calendar.patch(event_id, body, sim.now)
    sim.record_write("patch", event_id, sendUpdates, body)
    return event


@router.delete("/calendars/primary/events/{event_id}", status_code=204)
def delete_event(sim: Sim, event_id: str, sendUpdates: str | None = None) -> Response:
    sim.calendar.delete(event_id)
    sim.record_write("delete", event_id, sendUpdates, {})
    return Response(status_code=204)


@router.post("/freeBusy")
def free_busy(sim: Sim, body: dict[str, Any]) -> dict[str, Any]:
    calendars = {
        item["id"]: (
            {"errors": [{"domain": "global", "reason": "notFound"}], "busy": []}
            if item["id"] in sim.unknown_calendars
            else {"busy": sim.calendar.busy(body["timeMin"], body["timeMax"], item["id"])}
        )
        for item in body.get("items", [{"id": "primary"}])
    }
    return {
        "kind": "calendar#freeBusy",
        "timeMin": body["timeMin"],
        "timeMax": body["timeMax"],
        "calendars": calendars,
    }
