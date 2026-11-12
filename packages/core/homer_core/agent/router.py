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
    | {"delete"}
)
FILLER_WORDS = frozenset(
    {"it", "ok", "okay", "sure", "looks", "look", "good", "great", "perfect", "fine", "now"}
    | {"please", "pls", "plz", "thanks", "thank", "you", "the", "email", "mail", "draft", "that"}
    | {"this", "go", "just", "then", "and", "alright", "cool", "nice", "all", "right", "sounds"}
    | {"lets", "off", "away", "out", "event", "meeting", "invite", "message", "k", "awesome"}
    | {"for"}
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
    r"(?:you|it|that|this|they|the\s+\w+|my\s+\w+)\s+(?:[\w']+\s+){0,3}?"
    r"(?:send|sent|go(?:ne)? out|went out)\b(?!.*\b(?:link|add|include|mention)\b)",
    re.IGNORECASE,
)
DAY_SUMMARY = re.compile(
    r"\bwhat (?:did|have) i (?:get |got |gotten )?"
    r"(?:done|do|did|accomplish(?:ed)?|send|sent|finish(?:ed)?)\b"
    r"|\bwhat(?:'s| is| else is)? (?:still )?(?:open|left|pending|outstanding|waiting on me)\b"
    r"|\b(?:waiting|pending) on me\b|\bend[- ]of[- ]day (?:summary|recap|digest|review)\b"
    r"|\b(?:recap|wrap[- ]up|summary) of (?:my|the) day\b|\bsummari[sz]e my day\b",
    re.IGNORECASE,
)
SHOW_DRAFT = re.compile(
    r"^(?:(?:ok|okay|so|and|hey|please|pls|can you|could you|can i|let me)[,]?\s+)*"
    r"(?:(?:show|see|open)(?: me)?(?: the| my| that| this)?"
    r" (?:draft|email|mail|message|card|it|that|this)(?: again| please)?"
    r"|where(?:'s| is)(?: the| my| that)? (?:draft|email|mail|card|it))\s*[?.!]*$",
    re.IGNORECASE,
)
QUESTION_START = r"(?:where|what|whats|does|do|did|is|are|was|were|has|have|will|why|how)\b"
DRAFT_QUESTION = re.compile(
    rf"\?\s*$|^{QUESTION_START}|\byes or no\b",
    re.IGNORECASE,
)
ABOUT_DRAFT = re.compile(
    r"\b(?:draft|link|(?:the|this|that|your) (?:e-?mail|message|body)"
    r"|it (?:say|says|mention|mentions|include|includes|contain|contains|have|has)|in it"
    r"|yes or no)\b",
    re.IGNORECASE,
)
ELSEWHERE = re.compile(r"\b(?:from|inbox|unread)\b", re.IGNORECASE)
LINK_EDIT = re.compile(
    r"\b(?:add|include|put|insert|paste|attach|drop|share)\b.*\blink\b", re.IGNORECASE
)
ASKED_STATE = re.compile(
    rf"^(?:so\s+|and\s+)?{QUESTION_START}",
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


def is_edit(message: str) -> bool:
    """True when the message asks to change the email waiting in the conversation."""
    text = message.strip()
    return bool(EDIT.search(text)) and not NEW_REQUEST.match(text) and not NOT_MAIL.search(text)


def asks_for_draft(message: str) -> bool:
    """True for "show me the draft", "show it", "where is it" and the like."""
    return SHOW_DRAFT.match(message.strip()) is not None


def asks_if_sent(message: str) -> bool:
    return SENT_QUESTION.match(message.strip()) is not None


def asks_about_draft(message: str) -> bool:
    """A question about the email being drafted: "where's the link?", "does it say Friday?"."""
    text = message.strip()
    return (
        bool(DRAFT_QUESTION.search(text) and ABOUT_DRAFT.search(text))
        and not ELSEWHERE.search(text)
        and not asks_if_sent(text)
        and not wants_link(text)
    )


def wants_link(message: str) -> bool:
    """An edit that asks to put a link into the email: "add the link of the event in it"."""
    text = message.strip()
    return LINK_EDIT.search(text) is not None and not ASKED_STATE.match(text)


def asks_for_summary(message: str) -> bool:
    """True for "what did I get done today", "what's still open", "what's waiting on me"."""
    return DAY_SUMMARY.search(message) is not None


def asked_recipient(message: str) -> str | None:
    """The person or address after 'to' in a status question, lowercased."""
    for match in RECIPIENT.finditer(message):
        word = match.group(1).lower().rstrip(".")
        if word not in NOT_RECIPIENTS:
            return word
    return None
