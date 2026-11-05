from datetime import UTC, datetime, timedelta
from typing import Any

from homer_sim.errors import ApiError

TIMEZONE = "UTC"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def moment(edge: dict[str, str]) -> datetime:
    """A timed edge as given; an all-day edge as midnight UTC of its date."""
    if "dateTime" in edge:
        return parse_time(edge["dateTime"])
    return datetime.fromisoformat(edge["date"]).replace(tzinfo=UTC)


def event_start(event: dict[str, Any]) -> datetime:
    return moment(event["start"])


def event_end(event: dict[str, Any]) -> datetime:
    return moment(event["end"])


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
                    "attendees": [
                        a if isinstance(a, dict) else {"email": a} for a in item["attendees"]
                    ],
                    **({"hangoutLink": item["hangout_link"]} if "hangout_link" in item else {}),
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
            **({"hangoutLink": body["hangoutLink"]} if "hangoutLink" in body else {}),
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
            if not {"dateTime", "date"} & set(body.get(key, {})):
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

    def busy(self, time_min: str, time_max: str, calendar: str = "primary") -> list[dict[str, str]]:
        """Busy times of the owner's calendar, or of the events another address attends."""
        return [
            {"start": event_start(event).isoformat(), "end": event_end(event).isoformat()}
            for event in self.between(time_min, time_max)
            if calendar in ("primary", self.owner)
            or calendar in [a["email"] for a in event.get("attendees", [])]
        ]


def _at(day: datetime, clock: str) -> str:
    hour, minute = clock.split(":")
    return day.replace(hour=int(hour), minute=int(minute)).isoformat()
