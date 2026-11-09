import base64
import html
import re
import secrets
from datetime import UTC, datetime, timedelta
from email import message_from_bytes, policy
from email.utils import format_datetime, parsedate_to_datetime
from typing import Any

from homer_sim.errors import ApiError
from homer_sim.query import matches

SYSTEM_LABELS = [
    *("INBOX", "SENT", "DRAFT", "UNREAD", "IMPORTANT", "STARRED", "SPAM", "TRASH"),
    *("CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES"),
]
HEADER_NAMES = [
    *("From", "To", "Cc", "Subject", "Date", "Message-ID", "In-Reply-To", "References"),
    "List-Unsubscribe",
]
SNIPPET_LENGTH = 100
HIDDEN_LABELS = {"SPAM", "TRASH"}
TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.IGNORECASE | re.DOTALL)
DRAFT_ID_DIGITS = 19


def gmail_id() -> str:
    """16 lowercase hex characters, the shape of Gmail message and thread ids."""
    return secrets.token_hex(8)


def gmail_draft_id() -> str:
    return f"r-{secrets.randbelow(10**DRAFT_ID_DIGITS):0{DRAFT_ID_DIGITS}d}"


def label_number(label_id: str) -> int:
    _, _, number = label_id.partition("_")
    return int(number) if number.isdigit() else 0


def snippet_of(body: str, mime_type: str) -> str:
    text = TAG.sub(" ", body) if mime_type == "text/html" else body
    return " ".join(html.unescape(text).split())[:SNIPPET_LENGTH]


def b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class Mailbox:
    def __init__(self, seed: dict[str, Any], now: datetime) -> None:
        self.owner: str = seed["owner"]["email"]
        self.owner_name: str = seed["owner"].get("name", "")
        self.history_id: int = seed["history_id"]
        self.history_floor: int = 0
        self.history: list[dict[str, Any]] = []
        self.labels: dict[str, dict[str, Any]] = {
            name: {"id": name, "name": name, "type": "system"} for name in SYSTEM_LABELS
        }
        for label in seed["labels"]:
            self.labels[label["id"]] = {**label, "type": "user"}
        self.messages: dict[str, dict[str, Any]] = {}
        self.drafts: dict[str, str] = {}
        self.label_counter = max((label_number(label["id"]) for label in seed["labels"]), default=0)
        for item in seed["messages"]:
            self.messages[item["id"]] = self._seeded(item, now)

    def _seeded(self, item: dict[str, Any], now: datetime) -> dict[str, Any]:
        sent_at = (now - timedelta(days=item["days_ago"])).replace(
            hour=item["hour"], minute=0, second=0, microsecond=0
        )
        markup = item.get("html")
        headers = {
            "From": item["from"],
            "To": item["to"],
            "Subject": item["subject"],
            "Date": format_datetime(sent_at),
            "Message-ID": f"<{item['id']}@example.test>",
        }
        message = self._stored(
            item["id"],
            item["thread_id"],
            item["labels"],
            headers,
            "text/html" if markup else "text/plain",
            markup or item["body"],
            sent_at,
        )
        message["attachments"] = item.get("attachments", [])
        return message

    def _stored(
        self,
        message_id: str,
        thread_id: str,
        labels: list[str],
        headers: dict[str, str],
        mime_type: str,
        body: str,
        sent_at: datetime,
    ) -> dict[str, Any]:
        return {
            "id": message_id,
            "threadId": thread_id,
            "labelIds": list(labels),
            "historyId": str(self.history_id),
            "internalDate": str(int(sent_at.timestamp() * 1000)),
            "headers": headers,
            "mimeType": mime_type,
            "body": body,
            "attachments": [],
        }

    def _bump(self, record: dict[str, Any]) -> None:
        self.history_id += 1
        self.history.append({"id": str(self.history_id), **record})

    def render(self, message: dict[str, Any], fmt: str = "full") -> dict[str, Any]:
        rendered = {
            "id": message["id"],
            "threadId": message["threadId"],
            "labelIds": message["labelIds"],
            "snippet": snippet_of(message["body"], message["mimeType"]),
            "historyId": message["historyId"],
            "internalDate": message["internalDate"],
            "sizeEstimate": len(message["body"]),
        }
        if fmt == "minimal":
            return rendered
        headers = [{"name": k, "value": v} for k, v in message["headers"].items()]
        attachments = message.get("attachments", [])
        mime_type = "multipart/mixed" if attachments else message["mimeType"]
        payload: dict[str, Any] = {"mimeType": mime_type, "headers": headers}
        if fmt != "full":
            return {**rendered, "payload": payload}
        body = {"size": len(message["body"]), "data": b64url(message["body"])}
        if not attachments:
            return {**rendered, "payload": {**payload, "body": body}}
        parts = [{"partId": "0", "mimeType": message["mimeType"], "filename": "", "body": body}]
        for number, attachment in enumerate(attachments, start=1):
            parts.append(
                {
                    "partId": str(number),
                    "mimeType": attachment["mime_type"],
                    "filename": attachment["filename"],
                    "body": {"attachmentId": f"att-{number}", "size": attachment["size"]},
                }
            )
        return {**rendered, "payload": {**payload, "body": {"size": 0}, "parts": parts}}

    def get(self, message_id: str) -> dict[str, Any]:
        if message_id not in self.messages:
            raise ApiError(404, "Requested entity was not found.")
        return self.messages[message_id]

    def search(
        self, q: str, now: datetime, label_ids: list[str] | None = None, hidden: bool = True
    ) -> list[dict[str, Any]]:
        """Newest first. Spam and trash stay out unless asked for, by label or by `hidden`."""
        names = {label["name"].lower(): label["id"] for label in self.labels.values()}
        wanted = set(label_ids or [])
        skipped = HIDDEN_LABELS - wanted if hidden else set()
        found = [
            m
            for m in self.messages.values()
            if wanted <= set(m["labelIds"])
            and not skipped & set(m["labelIds"])
            and (not q or matches(m, q, now, names))
        ]
        return sorted(found, key=lambda m: int(m["internalDate"]), reverse=True)

    def thread_ids(self, found: list[dict[str, Any]]) -> list[str]:
        """Thread ids of the found messages, newest activity first."""
        ordered: list[str] = []
        for message in found:
            if message["threadId"] not in ordered:
                ordered.append(message["threadId"])
        return ordered

    def label_counts(self, label_id: str) -> dict[str, Any]:
        if label_id not in self.labels:
            raise ApiError(404, "Requested entity was not found.")
        tagged = [m for m in self.messages.values() if label_id in m["labelIds"]]
        unread = [m for m in tagged if "UNREAD" in m["labelIds"]]
        return {
            **self.labels[label_id],
            "messagesTotal": len(tagged),
            "messagesUnread": len(unread),
            "threadsTotal": len({m["threadId"] for m in tagged}),
            "threadsUnread": len({m["threadId"] for m in unread}),
        }

    def modify_thread(
        self, thread_id: str, add: list[str], remove: list[str]
    ) -> list[dict[str, Any]]:
        return [self.modify(m["id"], add, remove) for m in self.thread(thread_id)]

    def thread(self, thread_id: str) -> list[dict[str, Any]]:
        found = [m for m in self.messages.values() if m["threadId"] == thread_id]
        if not found:
            raise ApiError(404, "Requested entity was not found.")
        return sorted(found, key=lambda m: int(m["internalDate"]))

    def modify(self, message_id: str, add: list[str], remove: list[str]) -> dict[str, Any]:
        message = self.get(message_id)
        unknown = [label for label in [*add, *remove] if label not in self.labels]
        if unknown:
            raise ApiError(400, f"Invalid label: {unknown[0]}")
        labels = [label for label in message["labelIds"] if label not in remove]
        labels += [label for label in add if label not in labels]
        message["labelIds"] = labels
        self._bump({"labelsAdded": [{"message": self.render(message, "minimal")}]})
        message["historyId"] = str(self.history_id)
        return message

    def create_label(self, name: str) -> dict[str, Any]:
        self.label_counter += 1
        label = {"id": f"Label_{self.label_counter}", "name": name, "type": "user"}
        self.labels[label["id"]] = label
        return label

    def _from_raw(
        self, raw: str, thread_id: str | None, labels: list[str], sent_at: datetime | None
    ) -> dict[str, Any]:
        parsed = message_from_bytes(b64url_decode(raw), policy=policy.default)
        headers = {name: str(parsed[name]) for name in HEADER_NAMES if parsed[name]}
        headers.setdefault("From", self.owner)
        part = parsed.get_body(("plain", "html"))
        body = part.get_content() if part is not None else ""
        mime_type = part.get_content_type() if part is not None else "text/plain"
        if sent_at is None:
            sent_at = parsedate_to_datetime(headers["Date"])
        message_id = gmail_id()
        message = self._stored(
            message_id,
            thread_id or gmail_id(),
            labels,
            headers,
            mime_type,
            body,
            sent_at,
        )
        self.messages[message_id] = message
        self._bump({"messagesAdded": [{"message": self.render(message, "minimal")}]})
        message["historyId"] = str(self.history_id)
        return message

    def insert(
        self, raw: str, labels: list[str], thread_id: str | None, now: datetime, from_header: bool
    ) -> dict[str, Any]:
        unknown = [label for label in labels if label not in self.labels]
        if unknown:
            raise ApiError(400, f"Invalid label: {unknown[0]}")
        if thread_id and not any(m["threadId"] == thread_id for m in self.messages.values()):
            raise ApiError(404, "Requested entity was not found.")
        return self._from_raw(raw, thread_id, labels, None if from_header else now)

    def trash(self, message_id: str) -> dict[str, Any]:
        return self.modify(message_id, ["TRASH"], ["INBOX", "UNREAD"])

    def create_draft(self, raw: str, thread_id: str | None, now: datetime) -> dict[str, Any]:
        message = self._from_raw(raw, thread_id, ["DRAFT"], now)
        draft_id = gmail_draft_id()
        self.drafts[draft_id] = message["id"]
        return {"id": draft_id, "message": self.render(message, "minimal")}

    def update_draft(
        self, draft_id: str, raw: str, thread_id: str | None, now: datetime
    ) -> dict[str, Any]:
        """Replaces the draft's message, as Gmail's drafts.update does; the draft id stays."""
        if draft_id not in self.drafts:
            raise ApiError(404, "Requested entity was not found.")
        old = self.messages.pop(self.drafts[draft_id])
        message = self._from_raw(raw, thread_id or old["threadId"], ["DRAFT"], now)
        self.drafts[draft_id] = message["id"]
        return {"id": draft_id, "message": self.render(message, "minimal")}

    def delete_draft(self, draft_id: str) -> None:
        if draft_id not in self.drafts:
            raise ApiError(404, "Requested entity was not found.")
        del self.messages[self.drafts.pop(draft_id)]

    def draft(self, draft_id: str, fmt: str = "full") -> dict[str, Any]:
        if draft_id not in self.drafts:
            raise ApiError(404, "Requested entity was not found.")
        return {"id": draft_id, "message": self.render(self.get(self.drafts[draft_id]), fmt)}

    def list_drafts(self) -> list[dict[str, Any]]:
        """Newest first, as Gmail lists them."""
        return [
            {"id": draft_id, "message": self.render(self.get(message_id), "minimal")}
            for draft_id, message_id in reversed(self.drafts.items())
        ]

    def send_draft(self, draft_id: str, now: datetime) -> dict[str, Any]:
        message = self.get(self.drafts.pop(draft_id, ""))
        message["labelIds"] = ["SENT"]
        message["headers"]["Date"] = format_datetime(now.astimezone(UTC))
        message["internalDate"] = str(int(now.timestamp() * 1000))
        self._bump({"messagesAdded": [{"message": self.render(message, "minimal")}]})
        message["historyId"] = str(self.history_id)
        return self.render(message, "minimal")

    def history_since(self, start: str) -> list[dict[str, Any]]:
        if not self.history_floor <= int(start) <= self.history_id:
            raise ApiError(404, "Requested entity was not found.")
        return [record for record in self.history if int(record["id"]) > int(start)]

    def expire_history(self) -> None:
        """Forgets every history record, as Gmail does after about a week."""
        self.history_floor = self.history_id
        self.history = []
