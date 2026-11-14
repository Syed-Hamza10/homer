import asyncio
import functools
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from importlib.metadata import version
from typing import Any

from fastmcp import FastMCP

from homer_mcp_google.auth import ReconnectRequired
from homer_mcp_google.client import GoogleClient, GoogleError
from homer_mcp_google.messages import (
    attachments_of,
    build_raw,
    has_attachment,
    headers_of,
    html_body,
    neutral_message,
    plain_snippet,
    untrusted,
)
from homer_mcp_google.slots import free_slots, parse_time, parse_working_hours
from homer_net import BlockedHostError

GMAIL = "/gmail/v1/users/me"
CALENDAR = "/calendar/v3/calendars/primary/events"
FREE_BUSY = "/calendar/v3/freeBusy"
PEOPLE = "/v1/people:searchContacts"
WARM_EVERY_SECONDS = 600.0
COLD_RETRY_SECONDS = 5.0
COLD_MARKERS = ("FAILED_PRECONDITION", "cold cache")
MAX_RESULTS = 25
PREVIEW_BODY_CHARS = 300
RECENT_DRAFTS = 5
PARALLEL_READS = 5
MAX_SLOTS = 10
FOLDER_LABELS = {"INBOX", "STARRED", "SENT", "DRAFT"}
TIER_1 = {"mail_send", "cal_create", "cal_update", "cal_delete"}
TOOL_NAMES = [
    "health",
    "mail_search",
    "mail_get",
    "mail_thread",
    "mail_list_threads",
    "mail_labels",
    "mail_thread_label",
    "mail_changes_since",
    "mail_draft",
    "mail_draft_update",
    "mail_draft_delete",
    "mail_send",
    "mail_label",
    "mail_archive",
    "cal_list",
    "cal_get",
    "cal_find_free_slots",
    "cal_create",
    "cal_update",
    "cal_delete",
    "contacts_search",
    "mail_profile",
    "execute",
]

log = logging.getLogger(__name__)

Tool = Callable[..., Awaitable[dict[str, Any]]]


class ContactsWarming(Exception):
    pass


def is_cold(error: GoogleError) -> bool:
    return error.status == 400 and any(marker in error.message for marker in COLD_MARKERS)


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


def video_link(event: dict[str, Any]) -> str:
    entry_points = (event.get("conferenceData") or {}).get("entryPoints", [])
    videos = [e.get("uri", "") for e in entry_points if e.get("entryPointType") == "video"]
    return event.get("hangoutLink") or next(iter(videos), "")


def neutral_event(event: dict[str, Any]) -> dict[str, Any]:
    attendees = event.get("attendees", [])
    return {
        "id": event["id"],
        "title": event.get("summary", ""),
        "start": event["start"].get("dateTime") or event["start"].get("date"),
        "end": event["end"].get("dateTime") or event["end"].get("date"),
        "all_day": "dateTime" not in event["start"],
        "location": event.get("location", ""),
        "description": event.get("description", ""),
        "attendees": [a["email"] for a in attendees],
        "people": [
            {
                "email": a["email"],
                "name": a.get("displayName", ""),
                "response": a.get("responseStatus", "needsAction"),
                "organizer": bool(a.get("organizer")),
            }
            for a in attendees
        ],
        "organizer": (event.get("organizer") or {}).get("email", ""),
        "video_link": video_link(event),
        "metadata": {"status": event.get("status"), "html_link": event.get("htmlLink")},
    }


def event_body(fields: dict[str, Any], timezone: str | None = None) -> dict[str, Any]:
    names = {"title": "summary", "description": "description", "location": "location"}
    body: dict[str, Any] = {names[k]: v for k, v in fields.items() if k in names}
    zone = {"timeZone": timezone} if timezone else {}
    for key in ("start", "end"):
        if key in fields:
            body[key] = {"dateTime": parse_time(fields[key]).isoformat(), **zone}
    if "attendees" in fields:
        body["attendees"] = [{"email": email} for email in fields["attendees"]]
    return body


def notify(payload: dict[str, Any]) -> dict[str, str]:
    return {"sendUpdates": payload.get("send_updates", "all")}


def mail_content(to: str, subject: str, body: str) -> tuple[str, str, str]:
    return to.strip(), subject.strip(), body.replace("\r\n", "\n").strip()


def zone_of(timezone: str | None) -> dict[str, str]:
    return {"timezone": timezone} if timezone else {}


def span_text(opens: datetime, closes: datetime) -> str:
    return f"{opens:%a %d %b %Y %H:%M}-{closes:%H:%M} ({opens.tzname()})"


def check_span(start: str, end: str, timezone: str | None = None) -> tuple[datetime, datetime]:
    opens, closes = parse_time(start, timezone), parse_time(end, timezone)
    if closes <= opens:
        raise ValueError("end must be after start")
    return opens, closes


async def bounded(calls: list[Awaitable[dict[str, Any]]]) -> list[dict[str, Any]]:
    gate = asyncio.Semaphore(PARALLEL_READS)

    async def one(call: Awaitable[dict[str, Any]]) -> dict[str, Any]:
        async with gate:
            return await call

    return list(await asyncio.gather(*(one(call) for call in calls)))


def full_message(message: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    payload = message.get("payload", {})
    return {
        **neutral_message(message, names, with_body=True),
        "cc": headers_of(message).get("cc", ""),
        "body_html": untrusted(html_body(payload)),
        "attachments": attachments_of(payload),
    }


def thread_summary(thread: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    messages = thread.get("messages", [])
    first, latest = headers_of(messages[0]), headers_of(messages[-1])
    label_ids = sorted({label for m in messages for label in m.get("labelIds", [])})
    senders = list(dict.fromkeys(headers_of(m).get("from", "") for m in messages))
    return {
        "id": thread["id"],
        "subject": first.get("subject", ""),
        "from": latest.get("from", ""),
        "to": latest.get("to", ""),
        "senders": senders,
        "date": latest.get("date", ""),
        "internal_date": messages[-1].get("internalDate"),
        "snippet": untrusted(plain_snippet(messages[-1])),
        "message_count": len(messages),
        "unread": "UNREAD" in label_ids,
        "starred": "STARRED" in label_ids,
        "has_attachment": any(has_attachment(m) for m in messages),
        "labels": [names.get(label, label) for label in label_ids],
        "label_ids": label_ids,
    }


class GoogleTools:
    def __init__(self, client: GoogleClient) -> None:
        self.client = client
        self.account: str | None = None
        self.warmed_at: float | None = None

    async def health(self) -> dict[str, Any]:
        """Reports whether the server is up and which version it runs."""
        return {"ok": True, "version": version("homer-mcp-google")}

    async def warm_up(self) -> None:
        """People's searchContacts needs one empty-query request before real searches."""
        try:
            await self.client.get(PEOPLE, query="", readMask="names")
        except Exception as error:
            log.warning("people_warm_up_failed: %s", error)
            return
        self.warmed_at = time.monotonic()

    async def _warmed(self) -> None:
        if self.warmed_at is None or time.monotonic() - self.warmed_at >= WARM_EVERY_SECONDS:
            await self.warm_up()

    async def _search_people(self, query: str) -> dict[str, Any]:
        await self._warmed()
        for attempt in range(2):
            try:
                return await self.client.get(PEOPLE, query=query, readMask="names,emailAddresses")
            except GoogleError as error:
                if not is_cold(error):
                    raise
            self.warmed_at = None
            if attempt == 0:
                await asyncio.sleep(COLD_RETRY_SECONDS)
        raise ContactsWarming

    async def _send_updates(self, *groups: list[str]) -> str:
        """Google's sendUpdates: all when anyone besides the account is invited, so they get
        an email about the change; none for a personal event."""

        invited = {email.lower() for group in groups for email in group}
        if not invited:
            return "none"
        if self.account is None:
            profile = await self.client.get(f"{GMAIL}/profile")
            self.account = str(profile["emailAddress"]).lower()
        return "all" if invited - {self.account} else "none"

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
    async def mail_thread(self, thread_id: str, html: bool = False) -> dict[str, Any]:
        """Returns every message in a thread, oldest first. With html, each message also carries
        cc, its raw HTML body and its attachment names."""
        thread = await self.client.get(f"{GMAIL}/threads/{thread_id}", format="full")
        names = await self._label_names()
        if html:
            return {
                "id": thread_id,
                "messages": [full_message(m, names) for m in thread["messages"]],
            }
        messages = [neutral_message(m, names, with_body=True) for m in thread["messages"]]
        return {"id": thread_id, "messages": messages}

    async def _thread_summary(self, thread_id: str, names: dict[str, str]) -> dict[str, Any]:
        thread = await self.client.get(f"{GMAIL}/threads/{thread_id}", format="metadata")
        return thread_summary(thread, names)

    @guarded
    async def mail_list_threads(
        self,
        query: str = "",
        label: str | None = None,
        page_token: str | None = None,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Lists conversations newest first by Gmail query and optional label id, one page at a
        time. Pass next_page_token back as page_token for the next page."""
        params: dict[str, Any] = {"q": query, "maxResults": min(max_results, MAX_RESULTS)}
        if label:
            params["labelIds"] = label
        if page_token:
            params["pageToken"] = page_token
        listing = await self.client.get(f"{GMAIL}/threads", **params)
        names = await self._label_names()
        reads = [self._thread_summary(t["id"], names) for t in listing.get("threads", [])]
        return {
            "threads": await bounded(reads),
            "next_page_token": listing.get("nextPageToken"),
            "estimate": listing.get("resultSizeEstimate", 0),
        }

    @guarded
    async def mail_labels(self) -> dict[str, Any]:
        """Lists the main folders and the user's labels with conversation totals and unread
        counts."""
        listing = await self.client.get(f"{GMAIL}/labels")
        wanted = [
            label["id"]
            for label in listing.get("labels", [])
            if label.get("type") == "user" or label["id"] in FOLDER_LABELS
        ]
        details = await bounded([self.client.get(f"{GMAIL}/labels/{i}") for i in wanted])
        labels = [
            {
                "id": label["id"],
                "name": label["name"],
                "type": label.get("type", "user"),
                "unread": label.get("threadsUnread", 0),
                "total": label.get("threadsTotal", 0),
            }
            for label in details
        ]
        return {"labels": labels}

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

    async def _label_change(
        self, add: list[str] | None, remove: list[str] | None
    ) -> tuple[dict[str, str], dict[str, list[str]]]:
        """Label names to ids, creating missing labels to add; returns the names by id too."""
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
        return names, {"addLabelIds": add_ids, "removeLabelIds": remove_ids}

    async def _modify_labels(
        self, message_id: str, add: list[str] | None, remove: list[str] | None
    ) -> dict[str, Any]:
        names, change = await self._label_change(add, remove)
        modified = await self.client.post(f"{GMAIL}/messages/{message_id}/modify", change)
        return neutral_message(modified, names, with_body=False)

    @guarded
    async def mail_label(
        self, message_id: str, add: list[str] | None = None, remove: list[str] | None = None
    ) -> dict[str, Any]:
        """Adds and removes labels by name on one message, creating missing labels to add."""
        return await self._modify_labels(message_id, add, remove)

    @guarded
    async def mail_thread_label(
        self, thread_id: str, add: list[str] | None = None, remove: list[str] | None = None
    ) -> dict[str, Any]:
        """Adds and removes labels by name on every message of a thread, creating missing labels
        to add."""
        names, change = await self._label_change(add, remove)
        modified = await self.client.post(f"{GMAIL}/threads/{thread_id}/modify", change)
        label_ids = sorted({x for m in modified.get("messages", []) for x in m.get("labelIds", [])})
        return {"id": thread_id, "labels": [names.get(x, x) for x in label_ids]}

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
    async def cal_get(self, event_id: str) -> dict[str, Any]:
        """Returns one event with attendee responses, organizer and video link."""
        return neutral_event(await self.client.get(f"{CALENDAR}/{event_id}"))

    @guarded
    async def cal_find_free_slots(
        self,
        start: str,
        end: str,
        duration_minutes: int = 30,
        working_hours: str = "09:00-17:00",
        timezone: str | None = None,
        attendees: list[str] | None = None,
        limit: int = 3,
    ) -> dict[str, Any]:
        """Proposes free slots (three unless `limit` says otherwise) of the given length inside
        working hours on weekdays when the user and any attendees are all free; times without an
        offset are read in `timezone` (IANA name), else UTC."""
        opens, closes = check_span(start, end, timezone)
        calendars = [{"id": "primary"}, *({"id": email} for email in attendees or [])]
        result = await self.client.post(
            FREE_BUSY,
            {"timeMin": opens.isoformat(), "timeMax": closes.isoformat(), "items": calendars},
        )
        busy = [
            (parse_time(b["start"]), parse_time(b["end"]))
            for calendar in result["calendars"].values()
            for b in calendar.get("busy", [])
        ]
        slots = free_slots(
            opens,
            closes,
            busy,
            timedelta(minutes=duration_minutes),
            parse_working_hours(working_hours),
            min(max(limit, 1), MAX_SLOTS),
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
            "send_updates": await self._send_updates(attendees or []),
            **zone_of(timezone),
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
        timezone: str | None = None,
    ) -> dict[str, Any]:
        """Asks the user to approve changing an event's fields, never changing it by itself; a
        move carries both start and end, and times without an offset are read in `timezone`."""

        raw = await self.client.get(f"{CALENDAR}/{event_id}")
        current = neutral_event(raw)
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
        opens, closes = check_span(
            changes.get("start", current["start"]), changes.get("end", current["end"]), timezone
        )
        if "start" in changes or "end" in changes:
            changes |= {"start": opens.isoformat(), "end": closes.isoformat()}
        lines = [f"{key}: {current[key]} -> {value}" for key, value in changes.items()]
        preview = f"Update event '{current['title']}':\n" + "\n".join(lines)
        payload = {
            "event_id": event_id,
            "changes": changes,
            "send_updates": await self._send_updates(
                current["attendees"], changes.get("attendees", [])
            ),
            **zone_of(timezone or raw["start"].get("timeZone")),
        }
        return approval("cal_update", payload, preview)

    @guarded
    async def cal_delete(self, event_id: str) -> dict[str, Any]:
        """Asks the user to approve deleting an event. Never deletes it by itself."""
        current = neutral_event(await self.client.get(f"{CALENDAR}/{event_id}"))
        span = span_text(*check_span(current["start"], current["end"]))
        preview = f"Delete event '{current['title']}' on {span}"
        payload = {
            "event_id": event_id,
            "send_updates": await self._send_updates(current["attendees"]),
        }
        return approval("cal_delete", payload, preview)

    @guarded
    async def contacts_search(self, query: str) -> dict[str, Any]:
        """Finds contacts whose name or email matches the query."""
        try:
            found = await self._search_people(query)
        except ContactsWarming:
            return {"error": "google_contacts_warming"}
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
    async def mail_profile(self, with_name: bool = False) -> dict[str, Any]:
        """Returns the address of the connected mailbox, and its display name when asked (empty
        when Gmail does not give one). Core use only, hidden from the model."""
        profile = await self.client.get(f"{GMAIL}/profile")
        name = await self._display_name() if with_name else ""
        return {"email": profile["emailAddress"], "name": name}

    async def _display_name(self) -> str:
        try:
            found = await self.client.get(f"{GMAIL}/settings/sendAs")
        except ReconnectRequired:
            raise
        except Exception:
            return ""
        primary = [entry for entry in found.get("sendAs", []) if entry.get("isPrimary")]
        return str(primary[0].get("displayName") or "") if primary else ""

    async def _recreated_draft(self, approved: tuple[str, str, str], thread_id: str | None) -> str:
        """A new draft with the approved content, in its thread while that thread still exists."""
        try:
            message = await self._draft_message(*approved, thread_id)
        except GoogleError as error:
            if error.status != 404:
                raise
            message = await self._draft_message(*approved, None)
        return (await self.client.post(f"{GMAIL}/drafts", {"message": message}))["id"]

    async def _approved_draft(self, payload: dict[str, Any]) -> str:
        """The id of a draft holding exactly the approved recipient, subject and body: a changed
        draft is rewritten first and a missing one is created again."""
        draft_id = payload["draft_id"]
        approved = mail_content(payload["to"], payload["subject"], payload["body"])
        thread_id = payload.get("thread_id") or None
        try:
            draft = await self.client.get(f"{GMAIL}/drafts/{draft_id}", format="full")
        except GoogleError as error:
            if error.status != 404:
                raise
            return await self._recreated_draft(approved, thread_id)
        current = neutral_message(draft["message"], {}, with_body=True)
        body = current["body"].removeprefix("<untrusted>").removesuffix("</untrusted>")
        if mail_content(current["to"], current["subject"], body) != approved:
            message = await self._draft_message(*approved, thread_id)
            await self.client.put(
                f"{GMAIL}/drafts/{draft_id}", {"id": draft_id, "message": message}
            )
        return draft_id

    @guarded
    async def execute(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Performs an approved action with its approval payload. Executor use only."""
        match action:
            case "mail_send":
                draft_id = await self._approved_draft(payload)
                sent = await self.client.post(f"{GMAIL}/drafts/send", {"id": draft_id})
                return {"sent": True, "message_id": sent["id"], "thread_id": sent["threadId"]}
            case "cal_create":
                body = event_body(payload, payload.get("timezone"))
                created = await self.client.post(CALENDAR, body, params=notify(payload))
                return neutral_event(created)
            case "cal_update":
                body = event_body(payload["changes"], payload.get("timezone"))
                path = f"{CALENDAR}/{payload['event_id']}"
                return neutral_event(await self.client.patch(path, body, params=notify(payload)))
            case "cal_delete":
                await self.client.delete(
                    f"{CALENDAR}/{payload['event_id']}", params=notify(payload)
                )
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
