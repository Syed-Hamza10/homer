import re
from typing import Any

from homer_core.agent.dates import WEEKDAY
from homer_core.agent.intents import (
    Calculate,
    ChatIntent,
    Forget,
    Intent,
    ReadCalendar,
    ReadEmail,
    Recall,
    Remember,
    WebSearch,
)
from homer_core.agent.router import CONVERSATIONAL, words
from homer_core.agent.voice import capitalised
from homer_core.services.calc import parse
from homer_core.services.facts import keywords
from homer_core.services.jobs.read_email import ATTENTION, SENT, UNREAD

SMALL_TALK_WORDS = frozenset(
    {"hi", "hello", "hey", "yo", "hiya", "sup", "whats", "up", "howdy", "morning", "evening"}
    | {"afternoon", "night", "good", "thanks", "thank", "you", "thx", "ty", "cheers", "ok"}
    | {"okay", "k", "kk", "cool", "great", "nice", "awesome", "perfect", "fine", "sure"}
    | {"alright", "no", "nope", "nah", "yes", "yep", "yeah", "lol", "haha", "hmm", "got", "it"}
    | {"understood", "np", "worries", "bye", "goodbye", "later", "see", "ya", "so", "much"}
    | {"how", "are", "is", "it", "going", "wow", "oh", "ah", "a", "lot", "again", "anyway"}
    | {"there", "the", "best", "youre", "welcome", "appreciate", "all", "folks", "buddy"}
)
SMALL_TALK_MAX_WORDS = 6
LEAD = (
    r"^(?:(?:btw|by the way|also|and|so|oh|ok|okay|please|pls|hey|homer|now|can you|could you"
    r"|i want you to|you should)[,:]?\s+)*"
)
RECALL = re.compile(
    LEAD + r"(?:what|anything)(?: else)?\s+(?:do|did|have)\s+"
    r"you\s+(?P<verb>remember|recall|know|saved|stored|got|noted|have (?:saved|stored|noted))"
    r"(?:\s+about\s+(?P<about>.+?))?\s*[?.!]*$",
    re.IGNORECASE,
)
REMEMBER_ASKED = re.compile(
    LEAD + r"(?:do|did|can) you (?:still )?(?:remember|recall)"
    r"\s+(?P<about>.+?)\s*[?.!]*$",
    re.IGNORECASE,
)
FORGET = re.compile(
    LEAD + r"forget\s+(?:about\s+)?(?P<about>.+?)\s*[.!]*$",
    re.IGNORECASE,
)
SELF = frozenset({"me", "myself", "us", "my life"})
REMEMBER_FRONT = re.compile(
    LEAD + r"(?:remember|note|keep in mind|don't forget|do not forget|memori[sz]e)"
    r"(?:\s+(?:that|this))?[,:]?\s+(?P<fact>(?!to\b).+?)\s*[.!]*$",
    re.IGNORECASE,
)
REMEMBER_BACK = re.compile(
    LEAD + r"(?P<fact>.+?)[,;.\s-]+(?:please\s+)?"
    r"(?:remember|note|keep in mind)(?:\s+(?:that|this|it))?(?:\s+please)?\s*[.!]*$",
    re.IGNORECASE,
)
PRONOUNS = [
    (r"\bI am\b", "you are"),
    (r"\bI'm\b|\bIm\b", "you're"),
    (r"\bI was\b", "you were"),
    (r"\bI've\b", "you've"),
    (r"\bI'll\b", "you'll"),
    (r"\bI'd\b", "you'd"),
    (r"\bI\b", "you"),
    (r"\bmyself\b", "yourself"),
    (r"\bmine\b", "yours"),
    (r"\bmy\b", "your"),
    (r"\bme\b", "you"),
]
TIME_SENSITIVE = re.compile(
    r"\b(?:news|headlines?|latest|newest|recent(?:ly)?|current(?:ly)?|now|right now|today"
    r"|tonight|tomorrow|yesterday|last night|this (?:week|month|year|morning|weekend|season)"
    r"|next week|weather|forecast|rain|snow|temperature|price|prices|cost|stock|shares?|market"
    r"|rate|rates|score|scores|won|win|wins|lost|beat|result|results|match|game|fixture"
    r"|standings|election|polls?|announce[ds]?|announcement|launch(?:ed|es)?|release[ds]?"
    r"|update[ds]?|traffic|open now|ceo|president|prime minister|chancellor|king|queen|pope"
    r"|still|anymore|finals?|champions?|championship|title|winners?|finish(?:ed)?|playoffs?"
    r"|tournament|series|mayor|governor|minister|20\d\d)\b",
    re.IGNORECASE,
)
SEARCH_ASKED = re.compile(
    r"\b(?:search|look (?:it |that )?up|google|online|on the (?:web|internet)|browse)\b",
    re.IGNORECASE,
)
OTHER_REQUEST = re.compile(
    r"\b(?:and|then|also|,)\s+(?:please\s+)?(?:e-?mail|send|book|schedule|remind|search|find|add"
    r"|cancel|move|reply|draft|check)\b",
    re.IGNORECASE,
)
PERSONAL = re.compile(
    r"\bmy (?:wife|husband|sister|brother|mom|mum|mother|dad|father|son|daughter|kids?|child"
    r"|children|dog|cat|pet|fish|friend|boss|colleague|partner|name|birthday|family|parents?"
    r"|team|assistant|address|favou?rite)\b|\b(?:about me|do i|did i|am i|have i|was i)\b",
    re.IGNORECASE,
)
NOT_NAMES = frozenset({"your", "you", "the", "my", "user", "remember"})
MAIL_QUESTION = re.compile(
    LEAD + r"(?:any|anything|do i have|is (?:there|anything)"
    r"|are there|got any|what(?:'s| is| are)?|whats|show me|check|did|have|has|list)\b",
    re.IGNORECASE,
)
MAIL_WORDS = re.compile(r"\b(?:e-?mails?|mail|inbox|messages?)\b", re.IGNORECASE)
CALENDAR_ASKED = re.compile(
    r"\b(?:calendar|schedule|agenda|meetings?|events?|appointments?|free|busy|available"
    r"|plans?|booked|my day|day look)\b",
    re.IGNORECASE,
)


def is_small_talk(message: str) -> bool:
    found = words(message)
    return 0 < len(found) <= SMALL_TALK_MAX_WORDS and set(found) <= SMALL_TALK_WORDS


def is_greeting_or_thanks(message: str) -> bool:
    """Small talk with no yes or no in it, which could answer a question Homer asked."""
    return is_small_talk(message) and not set(words(message)) & CONVERSATIONAL


def recall(message: str, facts: list[str]) -> Recall | None:
    """'What do you remember about Dana?'; 'what do you know about X' only when X is the user
    or appears in a remembered fact, so general questions still reach the model."""
    match = RECALL.match(message.strip())
    if match is None:
        return None
    about = (match["about"] or "").strip()
    if match["verb"].lower() == "know":
        known = " ".join(facts).lower()
        mentioned = about and all(word in known for word in about.lower().split())
        if about.lower() not in SELF and not mentioned:
            return None
    return Recall(kind="recall", about=None if about.lower() in SELF else about or None)


def remembered_question(message: str) -> Recall | None:
    """'Do you remember what Zainab doesn't eat?'"""
    match = REMEMBER_ASKED.match(message.strip())
    if match is None or not keywords(match["about"]):
        return None
    return Recall(kind="recall", about=match["about"])


def remember(message: str) -> Remember | None:
    """'Remember that ...' with no other request in the message."""
    match = REMEMBER_FRONT.match(message.strip())
    if match is None or OTHER_REQUEST.search(match["fact"]):
        return None
    fact = told_fact(message)
    return Remember(kind="remember", fact=fact) if fact else None


def mail_question(message: str) -> ReadEmail | None:
    """Unread, needs-attention and "did I email X" questions, which code answers from Gmail."""
    text = message.strip()
    if not MAIL_QUESTION.match(text) or OTHER_REQUEST.search(text) or CALENDAR_ASKED.search(text):
        return None
    pointed = re.search(r"\b(?:sen[dt]|e-?mail(?:ed)?) (?:it|that|this)\b", text, re.I)
    sent = SENT.search(text) and re.match(r"^(?:did|have|has)\b", text, re.I) and not pointed
    mail = MAIL_WORDS.search(text) is not None or re.search(r"\battention\b", text, re.I)
    if sent or (mail and (ATTENTION.search(text) or UNREAD.search(text))):
        return ReadEmail(kind="read_email", question=text)
    return None


def routed(message: str, facts: list[str]) -> list[Intent] | None:
    """Messages code can route without the intent call: small talk, sums and conversions,
    "remember that ...", "forget ..." and questions about what Homer remembers."""
    if is_greeting_or_thanks(message):
        return [ChatIntent(kind="chat")]
    if parse(message) is not None:
        return [Calculate(kind="calculate", expression=message.strip())]
    forget = FORGET.match(message.strip())
    if forget is not None and (keywords(forget["about"]) or forget["about"].lower() == "that"):
        return [Forget(kind="forget", about=forget["about"])]
    asked = (
        remember(message),
        recall(message, facts),
        remembered_question(message),
        mail_question(message),
    )
    for found in asked:
        if found is not None:
            return [found]
    return None


def first_to_second_person(text: str) -> str:
    for pattern, replacement in PRONOUNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return capitalised(text.strip().rstrip(".!")) + "."


def told_fact(message: str) -> str | None:
    """The fact as the user wrote it, in the second person: 'Remember that Dana prefers calls
    after 3pm' gives 'Dana prefers calls after 3pm.'"""
    for pattern in (REMEMBER_FRONT, REMEMBER_BACK):
        match = pattern.match(message.strip())
        if match is not None and len(match["fact"].split()) >= 2:
            return first_to_second_person(match["fact"])
    return None


def needs_search(message: str) -> bool:
    return bool(TIME_SENSITIVE.search(message) or SEARCH_ASKED.search(message))


def names(facts: list[str]) -> set[str]:
    """The capitalised names in remembered facts, such as people and pets."""
    found = {word.lower() for fact in facts for word in re.findall(r"\b[A-Z][\w'-]{2,}", fact)}
    return {word.removesuffix("'s") for word in found} - NOT_NAMES


def personal(message: str, facts: list[str]) -> bool:
    """About the user or someone in their remembered facts, which the web cannot know."""
    return bool(PERSONAL.search(message) or names(facts) & set(words(message)))


def calendar_asked(message: str, previous: list[dict[str, Any]]) -> bool:
    repeated = any(item.get("kind") == "read_calendar" for item in previous)
    return repeated or bool(CALENDAR_ASKED.search(message) or WEEKDAY.search(message))


def refined(
    intents: list[Intent],
    message: str,
    previous: list[dict[str, Any]],
    facts: list[str] | None = None,
) -> list[Intent]:
    """Code rules over the model's intents: web search only for things that change and never
    for personal questions, the user's own words for a single remembered fact, and no calendar
    listing the message did not ask for next to another request."""
    if len(intents) == 1 and isinstance(intents[0], Remember):
        fact = told_fact(message)
        return [intents[0].model_copy(update={"fact": fact})] if fact else intents
    result: list[Intent] = []
    for intent in intents:
        searched = isinstance(intent, WebSearch) and not SEARCH_ASKED.search(message)
        if searched and (not needs_search(message) or personal(message, facts or [])):
            intent = ChatIntent(kind="chat")
        unasked = len(intents) > 1 and not calendar_asked(message, previous)
        if isinstance(intent, ReadCalendar) and unasked:
            continue
        result.append(intent)
    return result or [ChatIntent(kind="chat")]
