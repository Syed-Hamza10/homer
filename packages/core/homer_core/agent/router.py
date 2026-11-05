import re
from dataclasses import dataclass
from typing import Literal

COMMAND = re.compile(
    r"^/(brief|inbox|digest|slot|draft|followup|remind|approve|reject)\b\s*(.*)$", re.DOTALL
)
POLITE = r"(?:\s*,?\s*(?:please|now|thanks))*[.!]*"
APPROVE = re.compile(
    r"^(?:(?:yes|yep|ok|okay|sure)[,.!]?\s*)?(?:send it|send|approved?|confirm(?:ed)?|go ahead"
    rf"|create it|do it|book it|yes){POLITE}$",
    re.IGNORECASE,
)
REJECT = re.compile(
    r"^(?:no|nope|cancel(?: it)?|discard(?: it)?|reject(?:ed)?|don'?t send(?: it)?"
    rf"|do not send(?: it)?){POLITE}$",
    re.IGNORECASE,
)
CONVERSATIONAL = re.compile(r"^(?:yes|yep|ok|okay|sure|no|nope)[.!]*$", re.IGNORECASE)

Decision = Literal["approve", "reject"]


@dataclass(frozen=True)
class Command:
    name: str
    arg: str


def parse_command(message: str) -> Command | None:
    match = COMMAND.match(message.strip())
    if match is None:
        return None
    return Command(match.group(1), match.group(2).strip())


def parse_decision(message: str) -> Decision | None:
    text = message.strip()
    if APPROVE.match(text):
        return "approve"
    if REJECT.match(text):
        return "reject"
    return None


def is_conversational(message: str) -> bool:
    """True for a bare yes or no, which may answer something other than an approval."""
    return CONVERSATIONAL.match(message.strip()) is not None
