import base64
import html
import re
from email.message import EmailMessage
from html.parser import HTMLParser
from typing import Any

SKIPPED_TAGS = {"script", "style", "head", "title"}
BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIPPED_TAGS:
            self.depth += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED_TAGS:
            self.depth -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.depth == 0:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    extractor = TextExtractor()
    extractor.feed(html)
    text = re.sub(r"[ \t]+", " ", "".join(extractor.parts))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def untrusted(text: str) -> str:
    return f"<untrusted>{text}</untrusted>"


def decode_body(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(errors="replace")


def body_text(payload: dict[str, Any]) -> str:
    plain, html = _collect(payload)
    if plain:
        return plain.strip()
    return html_to_text(html) if html else ""


def _collect(part: dict[str, Any]) -> tuple[str, str]:
    data = part.get("body", {}).get("data")
    mime = part.get("mimeType", "")
    if data and mime == "text/plain":
        return decode_body(data), ""
    if data and mime == "text/html":
        return "", decode_body(data)
    plain, html = "", ""
    for child in part.get("parts", []):
        child_plain, child_html = _collect(child)
        plain, html = plain or child_plain, html or child_html
    return plain, html


def html_body(payload: dict[str, Any]) -> str:
    return _collect(payload)[1]


def attachments_of(part: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    if part.get("filename"):
        found.append(
            {
                "filename": part["filename"],
                "mime_type": part.get("mimeType", ""),
                "size": part.get("body", {}).get("size", 0),
            }
        )
    for child in part.get("parts", []):
        found.extend(attachments_of(child))
    return found


def has_attachment(message: dict[str, Any]) -> bool:
    payload = message.get("payload", {})
    return payload.get("mimeType") == "multipart/mixed" or bool(attachments_of(payload))


def plain_snippet(message: dict[str, Any]) -> str:
    return html.unescape(message.get("snippet", ""))


def headers_of(message: dict[str, Any]) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}


def neutral_message(
    message: dict[str, Any], label_names: dict[str, str], with_body: bool
) -> dict[str, Any]:
    headers = headers_of(message)
    label_ids = message.get("labelIds", [])
    result = {
        "id": message["id"],
        "thread_id": message["threadId"],
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "labels": [label_names.get(label, label) for label in label_ids],
        "snippet": untrusted(message.get("snippet", "")),
        "metadata": {
            "label_ids": label_ids,
            "history_id": message.get("historyId"),
            "internal_date": message.get("internalDate"),
            "message_id_header": headers.get("message-id", ""),
        },
    }
    if with_body:
        result["body"] = untrusted(body_text(message.get("payload", {})))
    return result


def build_raw(to: str, subject: str, body: str, reply_to: dict[str, str] | None) -> str:
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    if reply_to and reply_to.get("message-id"):
        message["In-Reply-To"] = reply_to["message-id"]
        references = f"{reply_to.get('references', '')} {reply_to['message-id']}".strip()
        message["References"] = references
    message.set_content(body)
    message.add_alternative(body_html(body), subtype="html")
    return base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")


def body_html(body: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
    blocks = "".join(
        f"<p>{'<br>'.join(html.escape(line) for line in part.splitlines())}</p>"
        for part in paragraphs
    )
    return f"<html><body>{blocks}</body></html>"
