import base64
from datetime import UTC, datetime, timedelta
from email import message_from_bytes, policy
from email.utils import format_datetime, parsedate_to_datetime
from typing import Any

from achilles_sim.errors import ApiError
from achilles_sim.query import matches

SYSTEM_LABELS = ["INBOX", "SENT", "DRAFT", "UNREAD", "IMPORTANT", "STARRED", "SPAM", "TRASH"]
HEADER_NAMES = ["From", "To", "Cc", "Subject", "Date", "Message-ID", "In-Reply-To", "References"]
SNIPPET_LENGTH = 100


def b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class Mailbox:
    def __init__(self, seed: dict[str, Any], now: datetime) -> None:
        self.owner: str = seed["owner"]["email"]
        self.history_id: int = seed["history_id"]
        self.history: list[dict[str, Any]] = []
        self.labels: dict[str, dict[str, Any]] = {
            name: {"id": name, "name": name, "type": "system"} for name in SYSTEM_LABELS
        }
        for label in seed["labels"]:
            self.labels[label["id"]] = {**label, "type": "user"}
        self.messages: dict[str, dict[str, Any]] = {}
        self.drafts: dict[str, str] = {}
        self.counter = 0
        for item in seed["messages"]:
            self.messages[item["id"]] = self._seeded(item, now)

    def _seeded(self, item: dict[str, Any], now: datetime) -> dict[str, Any]:
        sent_at = (now - timedelta(days=item["days_ago"])).replace(
            hour=item["hour"], minute=0, second=0, microsecond=0
        )
        html = item.get("html")
        headers = {
            "From": item["from"],
            "To": item["to"],
            "Subject": item["subject"],
            "Date": format_datetime(sent_at),
            "Message-ID": f"<{item['id']}@example.test>",
        }
        return self._stored(
            item["id"],
            item["thread_id"],
            item["labels"],
            headers,
            "text/html" if html else "text/plain",
            html or item["body"],
            sent_at,
        )

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
        }

    def _next_id(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}_{self.counter:04d}"

    def _bump(self, record: dict[str, Any]) -> None:
        self.history_id += 1
        self.history.append({"id": str(self.history_id), **record})

    def render(self, message: dict[str, Any], fmt: str = "full") -> dict[str, Any]:
        rendered = {
            "id": message["id"],
            "threadId": message["threadId"],
            "labelIds": message["labelIds"],
            "snippet": message["body"][:SNIPPET_LENGTH],
            "historyId": message["historyId"],
            "internalDate": message["internalDate"],
            "sizeEstimate": len(message["body"]),
        }
        if fmt == "minimal":
            return rendered
        headers = [{"name": k, "value": v} for k, v in message["headers"].items()]
        payload: dict[str, Any] = {"mimeType": message["mimeType"], "headers": headers}
        if fmt == "full":
            payload["body"] = {"size": len(message["body"]), "data": b64url(message["body"])}
        return {**rendered, "payload": payload}

    def get(self, message_id: str) -> dict[str, Any]:
        if message_id not in self.messages:
            raise ApiError(404, "Requested entity was not found.")
        return self.messages[message_id]

    def search(self, q: str, now: datetime) -> list[dict[str, Any]]:
        label_ids = {label["name"].lower(): label["id"] for label in self.labels.values()}
        found = [m for m in self.messages.values() if not q or matches(m, q, now, label_ids)]
        return sorted(found, key=lambda m: int(m["internalDate"]), reverse=True)

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
        label = {"id": self._next_id("Label"), "name": name, "type": "user"}
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
        message_id = self._next_id("msg")
        message = self._stored(
            message_id,
            thread_id or self._next_id("thr"),
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
        draft_id = self._next_id("r")
        self.drafts[draft_id] = message["id"]
        return {"id": draft_id, "message": self.render(message, "minimal")}

    def draft(self, draft_id: str) -> dict[str, Any]:
        if draft_id not in self.drafts:
            raise ApiError(404, "Requested entity was not found.")
        return {"id": draft_id, "message": self.render(self.get(self.drafts[draft_id]))}

    def send_draft(self, draft_id: str, now: datetime) -> dict[str, Any]:
        message = self.get(self.drafts.pop(draft_id, ""))
        message["labelIds"] = ["SENT"]
        message["headers"]["Date"] = format_datetime(now.astimezone(UTC))
        message["internalDate"] = str(int(now.timestamp() * 1000))
        self._bump({"messagesAdded": [{"message": self.render(message, "minimal")}]})
        message["historyId"] = str(self.history_id)
        return self.render(message, "minimal")

    def history_since(self, start: str) -> list[dict[str, Any]]:
        return [record for record in self.history if int(record["id"]) > int(start)]
