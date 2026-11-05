import functools
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from importlib.metadata import version
from typing import Any

from fastmcp import FastMCP

from homer_mcp_google.auth import ReconnectRequired
from homer_mcp_google.client import GoogleClient, GoogleError
from homer_mcp_google.messages import build_raw, headers_of, neutral_message
from homer_mcp_google.slots import free_slots, parse_time, parse_working_hours
from homer_net import BlockedHostError

GMAIL = "/gmail/v1/users/me"
CALENDAR = "/calendar/v3/calendars/primary/events"
FREE_BUSY = "/calendar/v3/freeBusy"
PEOPLE = "/v1/people:searchContacts"
MAX_RESULTS = 25
PREVIEW_BODY_CHARS = 300
RECENT_DRAFTS = 5
TIER_1 = {"mail_send", "cal_create", "cal_update", "cal_delete"}
TOOL_NAMES = [
    "health",
    "mail_search",
    "mail_get",
    "mail_thread",
    "mail_changes_since",
    "mail_draft",
    "mail_draft_update",
    "mail_draft_delete",
    "mail_send",
    "mail_label",
    "mail_archive",
    "cal_list",
    "cal_find_free_slots",
    "cal_create",
    "cal_update",
    "cal_delete",
    "contacts_search",
    "mail_profile",
    "execute",
]

Tool = Callable[..., Awaitable[dict[str, Any]]]


def guarded(fn: Tool) -> Tool:
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return await fn(*args, **kwargs)
        except ReconnectRequired:
            return {"error": "google_reconnect_required"}
        except GoogleError as error:
            return {"error": "google_error", "status": error.status, "message": error.message}
        except BlockedHostError as error:
            return {"error": "blocked_host", "host": error.host}
        except ValueError as error:
            return {"error": "invalid_argument", "message": str(error)}

    return wrapper


def approval(action: str, payload: dict[str, Any], preview: str) -> dict[str, Any]:
    return {"approval_required": True, "action": action, "payload": payload, "preview": preview}


def neutral_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event["id"],
        "title": event.get("summary", ""),
        "start": event["start"].get("dateTime") or event["start"].get("date"),
        "end": event["end"].get("dateTime") or event["end"].get("date"),
        "location": event.get("location", ""),
        "description": event.get("description", ""),
        "attendees": [a["email"] for a in event.get("attendees", [])],
        "metadata": {"status": event.get("status"), "html_link": event.get("htmlLink")},
    }


def event_body(fields: dict[str, Any]) -> dict[str, Any]:
    names = {"title": "summary", "description": "description", "location": "location"}
    body: dict[str, Any] = {names[k]: v for k, v in fields.items() if k in names}
    for key in ("start", "end"):
        if key in fields:
            body[key] = {"dateTime": parse_time(fields[key]).isoformat()}
    if "attendees" in fields:
        body["attendees"] = [{"email": email} for email in fields["attendees"]]
    return body


def span_text(opens: datetime, closes: datetime) -> str:
    return f"{opens:%a %d %b %Y %H:%M}-{closes:%H:%M} ({opens.tzname()})"


def check_span(start: str, end: str, timezone: str | None = None) -> tuple[datetime, datetime]:
    opens, closes = parse_time(start, timezone), parse_time(end, timezone)
    if closes <= opens:
        raise ValueError("end must be after start")
    return opens, closes


class GoogleTools:
    def __init__(self, client: GoogleClient) -> None:
        self.client = client

    async def health(self) -> dict[str, Any]:
        """Reports whether the server is up and which version it runs."""
        return {"ok": True, "version": version("homer-mcp-google")}

    async def _label_names(self) -> dict[str, str]:
        listing = await self.client.get(f"{GMAIL}/labels")
        return {label["id"]: label["name"] for label in listing.get("labels", [])}

    async def _message(self, message_id: str, names: dict[str, str]) -> dict[str, Any]:
        raw = await self.client.get(f"{GMAIL}/messages/{message_id}", format="full")
        return neutral_message(raw, names, with_body=True)

    @guarded
    async def mail_search(self, query: str, max_results: int = 10) -> dict[str, Any]:
        """Searches mail with Gmail query syntax and returns matching messages with bodies."""
        listing = await self.client.get(
            f"{GMAIL}/messages", q=query, maxResults=min(max_results, MAX_RESULTS)
        )
        names = await self._label_names()
        messages = [await self._message(m["id"], names) for m in listing.get("messages", [])]
        return {"messages": messages}

    @guarded
    async def mail_get(self, message_id: str) -> dict[str, Any]:
        """Returns one message with its full body."""
        return await self._message(message_id, await self._label_names())

    @guarded
    async def mail_thread(self, thread_id: str) -> dict[str, Any]:
        """Returns every message in a thread, oldest first."""
        thread = await self.client.get(f"{GMAIL}/threads/{thread_id}", format="full")
        names = await self._label_names()
        messages = [neutral_message(m, names, with_body=True) for m in thread["messages"]]
        return {"id": thread_id, "messages": messages}

    async def _fresh_cursor(self, stale: bool) -> dict[str, Any]:
        profile = await self.client.get(f"{GMAIL}/profile")
        return {"cursor": profile["historyId"], "changed_ids": [], "stale": stale}

    @guarded
    async def mail_changes_since(self, cursor: str | None = None) -> dict[str, Any]:
        """Returns ids changed since the cursor plus a new cursor. A cursor Gmail no longer knows
        comes back as stale with a fresh cursor, so the caller can backfill with a search."""
        if not cursor:
            return await self._fresh_cursor(stale=False)
        try:
            history = await self.client.get(f"{GMAIL}/history", startHistoryId=cursor)
        except GoogleError as error:
            if error.status != 404:
                raise
            return await self._fresh_cursor(stale=True)
        changed: list[str] = []
        for record in history.get("history", []):
            for key in ("messagesAdded", "labelsAdded", "labelsRemoved"):
                for item in record.get(key, []):
                    if item["message"]["id"] not in changed:
                        changed.append(item["message"]["id"])
        return {"cursor": history["historyId"], "changed_ids": changed, "stale": False}

    async def _draft_message(
        self, to: str, subject: str, body: str, thread_id: str | None
    ) -> dict[str, Any]:
        reply_to = None
        if thread_id:
            thread = await self.client.get(f"{GMAIL}/threads/{thread_id}", format="metadata")
            reply_to = headers_of(thread["messages"][-1])
        message: dict[str, Any] = {"raw": build_raw(to, subject, body, reply_to)}
        if thread_id:
            message["threadId"] = thread_id
        return message

    @staticmethod
    def _draft_result(draft: dict[str, Any]) -> dict[str, Any]:
        return {
            "draft_id": draft["id"],
            "thread_id": draft["message"]["threadId"],
            "metadata": {"message_id": draft["message"]["id"]},
        }

    @guarded
    async def mail_draft(
        self, to: str, subject: str, body: str, thread_id: str | None = None
    ) -> dict[str, Any]:
        """Creates a draft email, optionally as a reply in an existing thread, and sends nothing.
        Returns draft_id; pass it unchanged to mail_send."""
        message = await self._draft_message(to, subject, body, thread_id)
        return self._draft_result(await self.client.post(f"{GMAIL}/drafts", {"message": message}))

    @guarded
    async def mail_draft_update(
        self, draft_id: str, to: str, subject: str, body: str, thread_id: str | None = None
    ) -> dict[str, Any]:
        """Replaces the recipient, subject and body of an existing draft. Core use only."""
        message = await self._draft_message(to, subject, body, thread_id)
        draft = await self.client.put(
            f"{GMAIL}/drafts/{draft_id}", {"id": draft_id, "message": message}
        )
        return self._draft_result(draft)

    @guarded
    async def mail_draft_delete(self, draft_id: str) -> dict[str, Any]:
        """Deletes a draft the user discarded. Core use only."""
        await self.client.delete(f"{GMAIL}/drafts/{draft_id}")
        return {"deleted": True, "draft_id": draft_id}

    async def _recent_drafts(self) -> list[dict[str, Any]]:
        listing = await self.client.get(f"{GMAIL}/drafts", maxResults=RECENT_DRAFTS)
        drafts = []
        for item in listing.get("drafts", []):
            draft = await self.client.get(f"{GMAIL}/drafts/{item['id']}", format="metadata")
            headers = headers_of(draft["message"])
            drafts.append(
                {
                    "draft_id": item["id"],
                    "subject": headers.get("subject", ""),
                    "to": headers.get("to", ""),
                }
            )
        return drafts

    @guarded
    async def mail_send(self, draft_id: str) -> dict[str, Any]:
        """Asks the user to approve sending an existing draft. Never sends by itself."""
        try:
            draft = await self.client.get(f"{GMAIL}/drafts/{draft_id}", format="full")
        except GoogleError as error:
            if error.status != 404:
                raise
            return {
                "error": "draft_not_found",
                "draft_id": draft_id,
                "drafts": await self._recent_drafts(),
            }
        message = neutral_message(draft["message"], {}, with_body=True)
        body = message["body"].removeprefix("<untrusted>").removesuffix("</untrusted>")
        preview = (
            f"Send email to {message['to']}\nSubject: {message['subject']}\n\n"
            f"{body[:PREVIEW_BODY_CHARS]}"
        )
        payload = {
            "draft_id": draft_id,
            "to": message["to"],
            "subject": message["subject"],
            "body": body,
            "thread_id": message["thread_id"],
        }
        return approval("mail_send", payload, preview)

    async def _modify_labels(
        self, message_id: str, add: list[str] | None, remove: list[str] | None
    ) -> dict[str, Any]:
        names = await self._label_names()
        ids = {name.lower(): label_id for label_id, name in names.items()}
        add_ids = []
        for name in add or []:
            if name.lower() not in ids:
                created = await self.client.post(f"{GMAIL}/labels", {"name": name})
                ids[name.lower()] = created["id"]
                names[created["id"]] = name
            add_ids.append(ids[name.lower()])
        remove_ids = [ids[name.lower()] for name in remove or [] if name.lower() in ids]
        modified = await self.client.post(
            f"{GMAIL}/messages/{message_id}/modify",
            {"addLabelIds": add_ids, "removeLabelIds": remove_ids},
        )
        return neutral_message(modified, names, with_body=False)

    @guarded
    async def mail_label(
        self, message_id: str, add: list[str] | None = None, remove: list[str] | None = None
    ) -> dict[str, Any]:
        """Adds and removes labels by name on one message, creating missing labels to add."""
        return await self._modify_labels(message_id, add, remove)

    @guarded
    async def mail_archive(self, message_id: str) -> dict[str, Any]:
        """Removes a message from the inbox without deleting it."""
        return await self._modify_labels(message_id, None, ["INBOX"])

    async def _events(self, start: str, end: str) -> list[dict[str, Any]]:
        listing = await self.client.get(
            CALENDAR,
            timeMin=parse_time(start).isoformat(),
            timeMax=parse_time(end).isoformat(),
            singleEvents="true",
            orderBy="startTime",
        )
        return listing.get("items", [])

    @guarded
    async def cal_list(self, start: str, end: str) -> dict[str, Any]:
        """Lists calendar events between two ISO 8601 times."""
        check_span(start, end)
        return {"events": [neutral_event(e) for e in await self._events(start, end)]}

    @guarded
    async def cal_find_free_slots(
        self,
        start: str,
        end: str,
        duration_minutes: int = 30,
        working_hours: str = "09:00-17:00",
        timezone: str | None = None,
    ) -> dict[str, Any]:
        """Proposes up to three free slots of the given length inside working hours on weekdays.
        Times without an offset are read in `timezone` (IANA name), else UTC."""
        opens, closes = check_span(start, end, timezone)
        result = await self.client.post(
            FREE_BUSY,
            {
                "timeMin": opens.isoformat(),
                "timeMax": closes.isoformat(),
                "items": [{"id": "primary"}],
            },
        )
        busy = [
            (parse_time(b["start"]), parse_time(b["end"]))
            for b in result["calendars"]["primary"].get("busy", [])
        ]
        slots = free_slots(
            opens,
            closes,
            busy,
            timedelta(minutes=duration_minutes),
            parse_working_hours(working_hours),
        )
        return {"slots": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in slots]}

    @guarded
    async def cal_create(
        self,
        title: str,
        start: str,
        end: str,
        attendees: list[str] | None = None,
        description: str = "",
        location: str = "",
        timezone: str | None = None,
    ) -> dict[str, Any]:
        """Asks the user to approve creating a calendar event with attendee emails. Never creates
        it by itself; times without an offset are read in `timezone` (IANA name), else UTC."""
        opens, closes = check_span(start, end, timezone)
        payload = {
            "title": title,
            "start": opens.isoformat(),
            "end": closes.isoformat(),
            "attendees": attendees or [],
            "description": description,
            "location": location,
        }
        who = f" with {', '.join(payload['attendees'])}" if payload["attendees"] else ""
        preview = f"Create event '{title}' on {span_text(opens, closes)}{who}"
        return approval("cal_create", payload, preview)

    @guarded
    async def cal_update(
        self,
        event_id: str,
        title: str | None = None,
        start: str | None = None,
        end: str | None = None,
        attendees: list[str] | None = None,
        description: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        """Asks the user to approve changing an event's fields. Never changes it by itself."""
        current = neutral_event(await self.client.get(f"{CALENDAR}/{event_id}"))
        given = {
            "title": title,
            "start": start,
            "end": end,
            "attendees": attendees,
            "description": description,
            "location": location,
        }
        changes = {key: value for key, value in given.items() if value is not None}
        if not changes:
            raise ValueError("nothing to change")
        check_span(changes.get("start", current["start"]), changes.get("end", current["end"]))
        lines = [f"{key}: {current[key]} -> {value}" for key, value in changes.items()]
        preview = f"Update event '{current['title']}':\n" + "\n".join(lines)
        return approval("cal_update", {"event_id": event_id, "changes": changes}, preview)

    @guarded
    async def cal_delete(self, event_id: str) -> dict[str, Any]:
        """Asks the user to approve deleting an event. Never deletes it by itself."""
        current = neutral_event(await self.client.get(f"{CALENDAR}/{event_id}"))
        span = span_text(*check_span(current["start"], current["end"]))
        preview = f"Delete event '{current['title']}' on {span}"
        return approval("cal_delete", {"event_id": event_id}, preview)

    @guarded
    async def contacts_search(self, query: str) -> dict[str, Any]:
        """Finds contacts whose name or email matches the query."""
        found = await self.client.get(PEOPLE, query=query, readMask="names,emailAddresses")
        contacts = [
            {
                "name": (person.get("names") or [{}])[0].get("displayName", ""),
                "email": (person.get("emailAddresses") or [{}])[0].get("value", ""),
            }
            for result in found.get("results", [])
            for person in [result["person"]]
        ]
        return {"contacts": contacts}

    @guarded
    async def mail_profile(self) -> dict[str, Any]:
        """Returns the address of the connected mailbox. Core use only, hidden from the model."""
        profile = await self.client.get(f"{GMAIL}/profile")
        return {"email": profile["emailAddress"]}

    @guarded
    async def execute(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Performs an approved action with its approval payload. Executor use only."""
        match action:
            case "mail_send":
                sent = await self.client.post(f"{GMAIL}/drafts/send", {"id": payload["draft_id"]})
                return {"sent": True, "message_id": sent["id"], "thread_id": sent["threadId"]}
            case "cal_create":
                created = await self.client.post(CALENDAR, event_body(payload))
                return neutral_event(created)
            case "cal_update":
                updated = await self.client.patch(
                    f"{CALENDAR}/{payload['event_id']}", event_body(payload["changes"])
                )
                return neutral_event(updated)
            case "cal_delete":
                await self.client.delete(f"{CALENDAR}/{payload['event_id']}")
                return {"deleted": True, "event_id": payload["event_id"]}
            case "mail_label":
                return await self._modify_labels(
                    payload["message_id"], payload.get("add"), payload.get("remove")
                )
            case "mail_archive":
                return await self._modify_labels(payload["message_id"], None, ["INBOX"])
        raise ValueError(f"unknown action {action!r}")


def register(mcp: FastMCP, tools: GoogleTools) -> None:
    for name in TOOL_NAMES:
        mcp.tool(getattr(tools, name), name=name)
