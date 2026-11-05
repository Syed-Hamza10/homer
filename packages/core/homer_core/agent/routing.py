import re
from typing import Any

from homer_core.agent.dates import WEEKDAY
from homer_core.agent.intents import (
    Calculate,
    ChatIntent,
    Forget,
    Intent,
    ReadCalendar,
    Recall,
    Remember,
    WebSearch,
)
from homer_core.agent.router import CONVERSATIONAL, words
from homer_core.services.calc import parse
from homer_core.services.facts import keywords

SMALL_TALK_WORDS = frozenset(
    {"hi", "hello", "hey", "yo", "hiya", "sup", "whats", "up", "howdy", "morning", "evening"}
    | {"afternoon", "night", "good", "thanks", "thank", "you", "thx", "ty", "cheers", "ok"}
    | {"okay", "k", "kk", "cool", "great", "nice", "awesome", "perfect", "fine", "sure"}
    | {"alright", "no", "nope", "nah", "yes", "yep", "yeah", "lol", "haha", "hmm", "got", "it"}
    | {"understood", "np", "worries", "bye", "goodbye", "later", "see", "ya", "so", "much"}
    | {"how", "are", "is", "it", "going", "wow", "oh", "ah", "a", "lot", "again", "anyway"}
)
SMALL_TALK_MAX_WORDS = 6
RECALL = re.compile(
    r"^(?:(?:so|and|hey|ok|okay|homer)[,]?\s+)*(?:what|anything)(?: else)?\s+(?:do|did|have)\s+"
    r"you\s+(?P<verb>remember|recall|know|saved|stored|got|noted|have (?:saved|stored|noted))"
    r"(?:\s+about\s+(?P<about>.+?))?\s*[?.!]*$",
    re.IGNORECASE,
)
FORGET = re.compile(
    r"^(?:(?:please|pls|can you|could you|ok|okay|and|also|now)[,]?\s+)*forget\s+(?:about\s+)?"
    r"(?P<about>.+?)\s*[.!]*$",
    re.IGNORECASE,
)
SELF = frozenset({"me", "myself", "us", "my life"})
REMEMBER_FRONT = re.compile(
    r"^(?:(?:btw|by the way|also|and|oh|ok|okay|please|pls|hey|homer|can you|could you"
    r"|i want you to|you should)[,:]?\s+)*(?:remember|note|keep in mind|don't forget"
    r"|do not forget|memori[sz]e)(?:\s+(?:that|this))?[,:]?\s+(?P<fact>(?!to\b).+?)\s*[.!]*$",
    re.IGNORECASE,
)
REMEMBER_BACK = re.compile(
    r"^(?:(?:btw|by the way|also|and|oh|ok|okay)[,:]?\s+)*(?P<fact>.+?)[,;.\s-]+(?:please\s+)?"
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
    r"|still|anymore|20\d\d)\b",
    re.IGNORECASE,
)
SEARCH_ASKED = re.compile(
    r"\b(?:search|look (?:it |that )?up|google|online|on the (?:web|internet)|browse)\b",
    re.IGNORECASE,
)
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


def routed(message: str, facts: list[str]) -> list[Intent] | None:
    """Messages code can route without the intent call: small talk, sums and conversions,
    "forget ..." and questions about what Homer remembers."""
    if is_greeting_or_thanks(message):
        return [ChatIntent(kind="chat")]
    if parse(message) is not None:
        return [Calculate(kind="calculate", expression=message.strip())]
    forget = FORGET.match(message.strip())
    if forget is not None and (keywords(forget["about"]) or forget["about"].lower() == "that"):
        return [Forget(kind="forget", about=forget["about"])]
    asked = recall(message, facts)
    return [asked] if asked is not None else None


def second_person(text: str) -> str:
    for pattern, replacement in PRONOUNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = text.strip().rstrip(".!")
    return text[:1].upper() + text[1:] + "."


def told_fact(message: str) -> str | None:
    """The fact as the user wrote it, in the second person: 'Remember that Dana prefers calls
    after 3pm' gives 'Dana prefers calls after 3pm.'"""
    for pattern in (REMEMBER_FRONT, REMEMBER_BACK):
        match = pattern.match(message.strip())
        if match is not None and len(match["fact"].split()) >= 2:
            return second_person(match["fact"])
    return None


def needs_search(message: str) -> bool:
    return bool(TIME_SENSITIVE.search(message) or SEARCH_ASKED.search(message))


def calendar_asked(message: str, previous: list[dict[str, Any]]) -> bool:
    repeated = any(item.get("kind") == "read_calendar" for item in previous)
    return repeated or bool(CALENDAR_ASKED.search(message) or WEEKDAY.search(message))


def refined(intents: list[Intent], message: str, previous: list[dict[str, Any]]) -> list[Intent]:
    """Code rules over the model's intents: web search only for things that change, the user's
    own words for a single remembered fact, and no calendar listing the message did not ask
    for next to another request."""
    if len(intents) == 1 and isinstance(intents[0], Remember):
        fact = told_fact(message)
        return [intents[0].model_copy(update={"fact": fact})] if fact else intents
    result: list[Intent] = []
    for intent in intents:
        if isinstance(intent, WebSearch) and not needs_search(message):
            intent = ChatIntent(kind="chat")
        unasked = len(intents) > 1 and not calendar_asked(message, previous)
        if isinstance(intent, ReadCalendar) and unasked:
            continue
        result.append(intent)
    return result or [ChatIntent(kind="chat")]
