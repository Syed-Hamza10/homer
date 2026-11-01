from datetime import UTC, datetime, timedelta
from typing import Any

from homer_sim.errors import ApiError

TIMEZONE = "UTC"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def event_start(event: dict[str, Any]) -> datetime:
    return parse_time(event["start"]["dateTime"])


def event_end(event: dict[str, Any]) -> datetime:
    return parse_time(event["end"]["dateTime"])


class Calendar:
    def __init__(self, seed: dict[str, Any], now: datetime) -> None:
        self.owner: str = seed["owner"]["email"]
        self.events: dict[str, dict[str, Any]] = {}
        self.counter = 0
        monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for item in seed["events"]:
            day = monday + timedelta(days=item["weekday"])
            self.events[item["id"]] = self._build(
                item["id"],
                {
                    "summary": item["summary"],
                    "description": item["description"],
                    "location": item["location"],
                    "start": {"dateTime": _at(day, item["start"]), "timeZone": TIMEZONE},
                    "end": {"dateTime": _at(day, item["end"]), "timeZone": TIMEZONE},
                    "attendees": [{"email": email} for email in item["attendees"]],
                },
                now,
            )

    def _build(self, event_id: str, body: dict[str, Any], now: datetime) -> dict[str, Any]:
        stamp = now.astimezone(UTC).isoformat()
        attendees = [
            {"responseStatus": "needsAction", **attendee} for attendee in body.get("attendees", [])
        ]
        return {
            "kind": "calendar#event",
            "id": event_id,
            "status": "confirmed",
            "htmlLink": f"https://calendar.example.test/event?eid={event_id}",
            "created": stamp,
            "updated": stamp,
            "summary": body.get("summary", ""),
            "description": body.get("description", ""),
            "location": body.get("location", ""),
            "creator": {"email": self.owner, "self": True},
            "organizer": {"email": self.owner, "self": True},
            "start": body["start"],
            "end": body["end"],
            "attendees": attendees,
        }

    def get(self, event_id: str) -> dict[str, Any]:
        if event_id not in self.events:
            raise ApiError(404, "Not Found")
        return self.events[event_id]

    def active(self) -> list[dict[str, Any]]:
        live = [event for event in self.events.values() if event["status"] == "confirmed"]
        return sorted(live, key=event_start)

    def between(self, time_min: str | None, time_max: str | None) -> list[dict[str, Any]]:
        lower = parse_time(time_min) if time_min else None
        upper = parse_time(time_max) if time_max else None
        return [
            event
            for event in self.active()
            if (lower is None or event_end(event) > lower)
            and (upper is None or event_start(event) < upper)
        ]

    def insert(self, body: dict[str, Any], now: datetime) -> dict[str, Any]:
        for key in ("start", "end"):
            if "dateTime" not in body.get(key, {}):
                raise ApiError(400, f"Missing {key} time.")
        self.counter += 1
        event = self._build(f"evt_{self.counter:04d}", body, now)
        self.events[event["id"]] = event
        return event

    def patch(self, event_id: str, body: dict[str, Any], now: datetime) -> dict[str, Any]:
        event = self.get(event_id)
        if "attendees" in body:
            body = {
                **body,
                "attendees": [{"responseStatus": "needsAction", **a} for a in body["attendees"]],
            }
        event.update(body)
        event["updated"] = now.astimezone(UTC).isoformat()
        return event

    def delete(self, event_id: str) -> None:
        self.get(event_id)["status"] = "cancelled"

    def busy(self, time_min: str, time_max: str) -> list[dict[str, str]]:
        return [
            {"start": event["start"]["dateTime"], "end": event["end"]["dateTime"]}
            for event in self.between(time_min, time_max)
        ]


def _at(day: datetime, clock: str) -> str:
    hour, minute = clock.split(":")
    return day.replace(hour=int(hour), minute=int(minute)).isoformat()
