import re
from dataclasses import dataclass
from typing import Literal

COMMAND = re.compile(
    r"^/(brief|inbox|digest|slot|draft|followup|remind|approve|reject)\b\s*(.*)$", re.DOTALL
)
APPROVE_WORDS = frozenset(
    {"send", "approve", "approved", "lgtm", "confirm", "confirmed", "yes", "yep", "yeah", "ahead"}
    | {"do", "create", "book", "ship"}
)
REJECT_WORDS = frozenset(
    {"no", "nope", "nah", "cancel", "discard", "reject", "rejected", "dont", "not", "scrap"}
    | {"delete"}
)
FILLER_WORDS = frozenset(
    {"it", "ok", "okay", "sure", "looks", "look", "good", "great", "perfect", "fine", "now"}
    | {"please", "pls", "plz", "thanks", "thank", "you", "the", "email", "mail", "draft", "that"}
    | {"this", "go", "just", "then", "and", "alright", "cool", "nice", "all", "right", "sounds"}
    | {"lets", "off", "away", "out", "event", "meeting", "invite", "message", "k", "awesome"}
)
CONVERSATIONAL = frozenset({"yes", "yep", "yeah", "ok", "okay", "sure", "no", "nope", "nah"})
EDIT = re.compile(
    r"^(?:(?:ok|okay|please|pls|can you|could you|now|also|and|but)[,]?\s+)*"
    r"(?:change|make|rewrite|rephrase|reword|shorten|lengthen|remove|delete|drop|replace|fix"
    r"|tweak|edit|update|add that|add a (?:line|sentence|note|bit)|add (?:my|a) (?:name|signature)"
    r"|mention|say (?:instead|that)|include|set the subject|use the subject|subject)\b"
    r"|\b(?:shorter|longer|more (?:formal|casual|friendly|polite|direct|professional)"
    r"|less (?:formal|casual|stiff)|subject(?: line)? (?:to|should be|is now)|say \w+ instead)\b",
    re.IGNORECASE,
)
NOT_MAIL = re.compile(r"\b(?:meeting|event|calendar|invite|remind(?:er)?)\b", re.IGNORECASE)
NEW_REQUEST = re.compile(
    r"^(?:send|email|e-mail|mail|write|reply|respond|message|what|who|when|where|why|how|which"
    r"|is|are|did|does|do)\b",
    re.IGNORECASE,
)
SENT_QUESTION = re.compile(
    r"^(?:so\s+|and\s+|but\s+|hey\s+)?(?:did|have|has|was|is|were)\s+"
    r"(?:you|it|that|this|they|the\s+\w+|my\s+\w+)\b.*\b(?:send|sent|go(?:ne)? out|went out)\b",
    re.IGNORECASE,
)
RECIPIENT = re.compile(r"\bto\s+([\w.+-]+(?:@[\w.-]+)?)", re.IGNORECASE)
NOT_RECIPIENTS = frozenset({"the", "my", "him", "her", "them", "it", "send", "me", "go"})

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
    """Approve or reject from a short typed reply made only of decision and filler words."""
    found = set(words(message))
    if not found or not found <= APPROVE_WORDS | REJECT_WORDS | FILLER_WORDS:
        return None
    if found & REJECT_WORDS:
        return "reject"
    if found & APPROVE_WORDS and found != {"do"}:
        return "approve"
    return None


def is_conversational(message: str) -> bool:
    """True for a bare yes or no, which may answer something other than an approval."""
    found = words(message)
    return bool(found) and set(found) <= CONVERSATIONAL


def is_edit(message: str) -> bool:
    """True when the message asks to change the email waiting in the conversation."""
    text = message.strip()
    return bool(EDIT.search(text)) and not NEW_REQUEST.match(text) and not NOT_MAIL.search(text)


def asks_if_sent(message: str) -> bool:
    return SENT_QUESTION.match(message.strip()) is not None


def asked_recipient(message: str) -> str | None:
    """The person or address after 'to' in a status question, lowercased."""
    for match in RECIPIENT.finditer(message):
        word = match.group(1).lower().rstrip(".")
        if word not in NOT_RECIPIENTS:
            return word
    return None
