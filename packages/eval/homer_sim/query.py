import shlex
from datetime import UTC, datetime, timedelta
from typing import Any

UNITS = {"d": 1, "w": 7, "m": 30, "y": 365}
FLAGS = {"unread": "UNREAD", "starred": "STARRED", "important": "IMPORTANT"}


def matches(message: dict[str, Any], q: str, now: datetime, label_ids: dict[str, str]) -> bool:
    return all(_term_matches(message, term, now, label_ids) for term in shlex.split(q))


def _term_matches(
    message: dict[str, Any], term: str, now: datetime, label_ids: dict[str, str]
) -> bool:
    if term.startswith("-"):
        return not _term_matches(message, term[1:], now, label_ids)
    key, _, value = term.partition(":")
    key, value = key.lower(), value.lower()
    headers = {k.lower(): v.lower() for k, v in message["headers"].items()}
    labels = message["labelIds"]
    match key:
        case "from" | "to" | "subject" if value:
            return value in headers.get(key, "")
        case "is":
            return FLAGS.get(value) in labels
        case "in":
            return value.upper() in labels
        case "label":
            return label_ids.get(value, value.upper()) in labels
        case "newer_than":
            return _sent_at(message) >= now - _span(value)
        case "older_than":
            return _sent_at(message) < now - _span(value)
        case "has":
            return False
    haystack = " ".join([*headers.values(), message["body"].lower()])
    return term.lower() in haystack


def _span(value: str) -> timedelta:
    return timedelta(days=int(value[:-1]) * UNITS[value[-1]])


def _sent_at(message: dict[str, Any]) -> datetime:
    return datetime.fromtimestamp(int(message["internalDate"]) / 1000, tz=UTC)
