import re
from typing import Any

from homer_core.agent.dates import WEEKDAY
from homer_core.agent.intents import ChatIntent, Intent, ReadCalendar, Remember, WebSearch
from homer_core.agent.router import words
from homer_core.agent.voice import capitalised

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
SEARCH_ASKED = re.compile(
    r"\b(?:search|look (?:it |that )?up|google|online|on the (?:web|internet)|browse)\b",
    re.IGNORECASE,
)
PERSONAL = re.compile(
    r"\bmy (?:wife|husband|sister|brother|mom|mum|mother|dad|father|son|daughter|kids?|child"
    r"|children|dog|cat|pet|fish|friend|boss|colleague|partner|name|birthday|family|parents?"
    r"|team|assistant|address|favou?rite)\b|\b(?:about me|do i|did i|am i|have i|was i)\b",
    re.IGNORECASE,
)
NOT_NAMES = frozenset({"your", "you", "the", "my", "user", "remember"})
CALENDAR_ASKED = re.compile(
    r"\b(?:calendar|schedule|agenda|meetings?|events?|appointments?|free|busy|available"
    r"|plans?|booked|my day|day look|gaps?)\b",
    re.IGNORECASE,
)


def is_small_talk(message: str) -> bool:
    found = words(message)
    return 0 < len(found) <= SMALL_TALK_MAX_WORDS and set(found) <= SMALL_TALK_WORDS


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


def searched(intent: WebSearch, message: str, facts: list[str]) -> bool:
    """A search runs when the user asked for one, or the answer changes over time and is not
    about the user or someone in their facts."""
    if SEARCH_ASKED.search(message):
        return True
    return intent.needs_live_data and not personal(message, facts)


def refined(
    intents: list[Intent],
    message: str,
    previous: list[dict[str, Any]],
    facts: list[str] | None = None,
) -> list[Intent]:
    """Code rules over the model's intents: web search only for live data, the user's own
    words for a single remembered fact, and no calendar listing the message did not ask for
    next to another request."""
    if len(intents) == 1 and isinstance(intents[0], Remember):
        fact = told_fact(message)
        return [intents[0].model_copy(update={"fact": fact})] if fact else intents
    others = any(not isinstance(intent, ReadCalendar) for intent in intents)
    unasked = others and not calendar_asked(message, previous)
    result: list[Intent] = []
    for intent in intents:
        if isinstance(intent, WebSearch) and not searched(intent, message, facts or []):
            intent = ChatIntent(kind="chat")
        if isinstance(intent, ReadCalendar) and unasked:
            continue
        result.append(intent)
    return result or [ChatIntent(kind="chat")]
