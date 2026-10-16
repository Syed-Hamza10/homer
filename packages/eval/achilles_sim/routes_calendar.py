from typing import Any

from fastapi import APIRouter, Response

from achilles_sim.deps import Authed, Sim
from achilles_sim.events import TIMEZONE

router = APIRouter(prefix="/calendar/v3", dependencies=[Authed])


@router.get("/calendars/primary/events")
def list_events(
    sim: Sim,
    timeMin: str | None = None,
    timeMax: str | None = None,
    maxResults: int = 250,
    singleEvents: bool = False,
    orderBy: str | None = None,
) -> dict[str, Any]:
    events = sim.calendar.between(timeMin, timeMax)[:maxResults]
    return {"kind": "calendar#events", "timeZone": TIMEZONE, "items": events}


@router.post("/calendars/primary/events", status_code=200)
def insert_event(sim: Sim, body: dict[str, Any]) -> dict[str, Any]:
    return sim.calendar.insert(body, sim.now)


@router.get("/calendars/primary/events/{event_id}")
def get_event(sim: Sim, event_id: str) -> dict[str, Any]:
    return sim.calendar.get(event_id)


@router.patch("/calendars/primary/events/{event_id}")
def patch_event(sim: Sim, event_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return sim.calendar.patch(event_id, body, sim.now)


@router.delete("/calendars/primary/events/{event_id}", status_code=204)
def delete_event(sim: Sim, event_id: str) -> Response:
    sim.calendar.delete(event_id)
    return Response(status_code=204)


@router.post("/freeBusy")
def free_busy(sim: Sim, body: dict[str, Any]) -> dict[str, Any]:
    busy = sim.calendar.busy(body["timeMin"], body["timeMax"])
    calendars = {item["id"]: {"busy": busy} for item in body.get("items", [{"id": "primary"}])}
    return {
        "kind": "calendar#freeBusy",
        "timeMin": body["timeMin"],
        "timeMax": body["timeMax"],
        "calendars": calendars,
    }
