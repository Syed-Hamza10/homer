import json
from datetime import UTC, datetime
from email.utils import formataddr, getaddresses
from typing import Any, Literal

from sqlmodel import Session, select

from homer_core.db.models import Approval, EmailCache, User
from homer_core.mcp.manager import PROFILE_TOOL, McpManager
from homer_core.services.errors import DomainError
from homer_core.services.followups import clean_subject
from homer_core.services.inbox import CATEGORY_RULES, DEFAULT_CATEGORY, PRIORITY_LABEL, clean
from homer_core.services.jobs.send_email import request_send
from homer_core.services.mail_html import sanitise

FOLDERS = (
    ("inbox", "Inbox", "INBOX"),
    ("starred", "Starred", "STARRED"),
    ("sent", "Sent", "SENT"),
    ("drafts", "Drafts", "DRAFT"),
    ("all", "All mail", None),
)
FOLDER_LABELS = {key: label for key, _, label in FOLDERS}
TRIAGE_LABELS = {name for name, _ in CATEGORY_RULES} | {DEFAULT_CATEGORY, PRIORITY_LABEL}
QUOTE_CHARS = 4000
ReplyMode = Literal["reply", "reply_all", "forward"]


class GoogleFailed(DomainError):
    status_code = 502


def checked(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise GoogleFailed(f"unexpected answer from the google server: {result!r}")
    if "error" in result:
        raise GoogleFailed(str(result["error"]))
    return result


def unwrap(text: str) -> str:
    return text.removeprefix("<untrusted>").removesuffix("</untrusted>")


def from_millis(value: str | None) -> datetime | None:
    return datetime.fromtimestamp(int(value) / 1000, UTC) if value else None


async def folders(manager: McpManager) -> list[dict[str, Any]]:
    labels = checked(await manager.call("google", "mail_labels", {}))["labels"]
    by_id = {label["id"]: label for label in labels}
    found = [
        {
            "id": key,
            "name": name,
            "kind": "folder",
            "unread": by_id.get(label_id or "", {}).get("unread", 0),
            "total": by_id.get(label_id or "", {}).get("total", 0),
        }
        for key, name, label_id in FOLDERS
    ]
    users = sorted((x for x in labels if x["type"] == "user"), key=lambda x: x["name"].lower())
    for label in users:
        kind = "category" if label["name"] in TRIAGE_LABELS else "label"
        found.append({**label, "kind": kind})
    return found


def thread_row(thread: dict[str, Any]) -> dict[str, Any]:
    return {
        **thread,
        "snippet": clean(thread.get("snippet", "")),
        "received_at": from_millis(thread.get("internal_date")),
    }


async def list_threads(
    manager: McpManager, folder: str, query: str, page_token: str | None, size: int
) -> dict[str, Any]:
    """One page of conversations in a folder (or a label id), narrowed by a Gmail query."""
    args: dict[str, Any] = {
        "query": query,
        "label": FOLDER_LABELS.get(folder, folder),
        "page_token": page_token,
        "max_results": size,
    }
    listing = checked(await manager.call("google", "mail_list_threads", args))
    return {
        "threads": [thread_row(thread) for thread in listing["threads"]],
        "next_page_token": listing.get("next_page_token"),
    }


def message_view(message: dict[str, Any], show_images: bool) -> dict[str, Any]:
    markup = unwrap(message.get("body_html", ""))
    cleaned = sanitise(markup, show_images) if markup.strip() else None
    return {
        "id": message["id"],
        "sender": message.get("from", ""),
        "to": message.get("to", ""),
        "cc": message.get("cc", ""),
        "date": message.get("date", ""),
        "received_at": from_millis((message.get("metadata") or {}).get("internal_date")),
        "labels": message.get("labels", []),
        "unread": "UNREAD" in message.get("labels", []),
        "body_text": unwrap(message.get("body", "")),
        "body_html": cleaned.html if cleaned else None,
        "remote_images": cleaned.remote_images if cleaned else 0,
        "attachments": message.get("attachments", []),
    }


async def read_thread(manager: McpManager, thread_id: str) -> list[dict[str, Any]]:
    args = {"thread_id": thread_id, "html": True}
    return checked(await manager.call("google", "mail_thread", args))["messages"]


async def thread(manager: McpManager, thread_id: str, show_images: bool) -> dict[str, Any]:
    messages = await read_thread(manager, thread_id)
    return {
        "id": thread_id,
        "subject": messages[0].get("subject", "") if messages else "",
        "messages": [message_view(message, show_images) for message in messages],
    }


def sync_cache(session: Session, user: User, thread_id: str, labels: list[str]) -> None:
    rows = session.exec(
        select(EmailCache).where(EmailCache.user_id == user.id, EmailCache.thread_id == thread_id)
    )
    for row in rows:
        row.unread = "UNREAD" in labels
        row.archived = "INBOX" not in labels
        row.labels_json = json.dumps(labels)
        session.add(row)
    session.commit()


async def change_labels(
    session: Session,
    user: User,
    manager: McpManager,
    thread_id: str,
    add: list[str],
    remove: list[str],
) -> dict[str, Any]:
    """Archive, star, read state and labels: tier 2, applied straight away to the thread."""
    args = {"thread_id": thread_id, "add": add, "remove": remove}
    result = checked(await manager.call("google", "mail_thread_label", args))
    sync_cache(session, user, thread_id, result["labels"])
    return result


def addresses(*fields: str) -> list[tuple[str, str]]:
    return [(name, email) for name, email in getaddresses(list(fields)) if "@" in email]


def recipients(found: list[tuple[str, str]], me: str) -> str:
    seen: dict[str, str] = {}
    for name, email in found:
        if email.lower() != me.lower() and email.lower() not in seen:
            seen[email.lower()] = formataddr((name, email))
    return ", ".join(seen.values())


def quoted(message: dict[str, Any]) -> str:
    body = unwrap(message.get("body", ""))[:QUOTE_CHARS]
    lines = "\n".join(f"> {line}" if line else ">" for line in body.splitlines())
    return f"\n\nOn {message.get('date', '')}, {message.get('from', '')} wrote:\n{lines}"


def forwarded(message: dict[str, Any]) -> str:
    header = (
        "---------- Forwarded message ----------\n"
        f"From: {message.get('from', '')}\nDate: {message.get('date', '')}\n"
        f"Subject: {message.get('subject', '')}\nTo: {message.get('to', '')}"
    )
    return f"\n\n{header}\n\n{unwrap(message.get('body', ''))[:QUOTE_CHARS]}"


async def reply_draft(manager: McpManager, thread_id: str, mode: ReplyMode) -> dict[str, Any]:
    """The composer's starting point for a reply, a reply to everyone, or a forward."""
    messages = await read_thread(manager, thread_id)
    if not messages:
        raise GoogleFailed(f"thread {thread_id} has no messages")
    last = messages[-1]
    subject = clean_subject(last.get("subject", ""))
    if mode == "forward":
        return {"to": "", "subject": f"Fwd: {subject}", "body": forwarded(last), "thread_id": None}
    me = str((await manager.call("google", PROFILE_TOOL, {})).get("email", ""))
    sender = addresses(last.get("from", ""))
    from_me = bool(sender) and sender[0][1].lower() == me.lower()
    found = addresses(last.get("to", "")) if from_me else sender
    if mode == "reply_all":
        found = [*sender, *addresses(last.get("to", ""), last.get("cc", ""))]
    return {
        "to": recipients(found, me),
        "subject": f"Re: {subject}",
        "body": quoted(last),
        "thread_id": thread_id,
    }


async def compose(
    session: Session,
    user: User,
    manager: McpManager,
    to: str,
    subject: str,
    body: str,
    thread_id: str | None,
) -> Approval:
    """Saves a Gmail draft and returns the `mail_send` approval for it; nothing is sent here."""
    args = {"to": to, "subject": subject, "body": body, "thread_id": thread_id}
    draft = checked(await manager.call("google", "mail_draft", args))
    if not draft.get("draft_id"):
        raise GoogleFailed(f"could not create the draft: {draft}")
    thread = str(draft.get("thread_id") or thread_id or "")
    return request_send(session, user.id, str(draft["draft_id"]), to, subject, body, thread)
