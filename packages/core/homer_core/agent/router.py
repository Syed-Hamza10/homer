import re
from dataclasses import dataclass
from typing import Literal

COMMAND = re.compile(
    r"^/(brief|inbox|digest|slot|draft|followup|remind|approve|reject)\b\s*(.*)$", re.DOTALL
)
APPROVE_WORDS = frozenset(
    {"send", "approve", "approved", "lgtm", "confirm", "confirmed", "yes", "yep", "yeah", "ahead"}
    | {"do", "create", "book", "ship", "fire"}
)
APPROVE_PHRASES = frozenset({"go for it", "ok go for it", "yes go for it", "go for it then"})
REJECT_WORDS = frozenset(
    {"no", "nope", "nah", "cancel", "discard", "reject", "rejected", "dont", "not", "scrap"}
    | {"delete", "never"}
)
FILLER_WORDS = frozenset(
    {"it", "ok", "okay", "sure", "looks", "look", "good", "great", "perfect", "fine", "now"}
    | {"please", "pls", "plz", "thanks", "thank", "you", "the", "email", "mail", "draft", "that"}
    | {"this", "go", "just", "then", "and", "alright", "cool", "nice", "all", "right", "sounds"}
    | {"lets", "off", "away", "out", "event", "meeting", "invite", "message", "k", "awesome"}
    | {"for", "mind"}
)
CONVERSATIONAL = frozenset({"yes", "yep", "yeah", "ok", "okay", "sure", "no", "nope", "nah"})

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


def words(message: str) -> list[str]:
    return re.sub(r"[^\w\s@.]|(?<!\w)\.|\.(?!\w)", "", message.lower().replace("'", "")).split()


def parse_decision(message: str) -> Decision | None:
    """Approve or reject from a short typed reply made only of decision and filler words:
    "send it", "looks good send", "fire it off", "no", "discard", "ok never mind, cancel it"."""
    if " ".join(words(message)) in APPROVE_PHRASES:
        return "approve"
    found = set(words(message))
    if not found or not found <= APPROVE_WORDS | REJECT_WORDS | FILLER_WORDS:
        return None
    if found & REJECT_WORDS:
        return "reject"
    if found & APPROVE_WORDS and found not in ({"do"}, {"do", "for"}):
        return "approve"
    return None


def is_conversational(message: str) -> bool:
    """True for a bare yes or no, which may answer something other than an approval."""
    found = words(message)
    return bool(found) and set(found) <= CONVERSATIONAL
