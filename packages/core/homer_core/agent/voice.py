import re
from collections.abc import Callable

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart

LEAK = re.compile(
    r"\b(?:provided|given|supplied|above|attached|following|available) (?:text|context|emails?"
    r"|documents?|pages?|data|information|messages?|list|search results|results|snippets?)\b"
    r"|\b(?:text|context|emails?|documents?|pages?|data|information|search results)"
    r" (?:provided|given|supplied|above|below)\b"
    r"|\bthe user(?:'s)?\b|\bas an AI\b|\bas a (?:large )?language model\b",
    re.IGNORECASE,
)
LEAD = re.compile(
    r"^\s*(?:based (?:on|solely on)|according to|from|looking at|in) (?:the )?(?:provided |given "
    r"|available |above |following )?(?:text|context|emails?|documents?|pages?|data|information"
    r"|search results|results|snippets?)(?: (?:provided|given|above|below))?\s*[,:]\s*",
    re.IGNORECASE,
)
USER_WORDS = (
    (re.compile(r"\bthe user's\b", re.IGNORECASE), "your"),
    (re.compile(r"\bthe user is\b", re.IGNORECASE), "you are"),
    (re.compile(r"\bthe user has\b", re.IGNORECASE), "you have"),
    (re.compile(r"\bthe user\b", re.IGNORECASE), "you"),
)
SENTENCE = re.compile(r"(?<=[.!?])\s+")
NON_ANSWER = re.compile(
    r"\b(?:does not|doesn't|do not|don't)\s+(?:say|mention|contain|include|state|specify|provide"
    r"|show|list|give|report)\b|\bno (?:specific |further |clear )?(?:information|details|mention"
    r"|data|results?|score|headlines|news items|dates|stories|figures)\b"
    r"|\bnot (?:mentioned|specified|included|stated|listed|provided"
    r"|available|reported)\b|\bimpossible to (?:determine|say|tell)\b"
    r"|\b(?:cannot|can't|unable to) (?:determine|find|tell|say|confirm|name|give)\b"
    r"|\bonly (?:mentions?|describes?|lists?|covers?|says|shows?|gives?|focuses)\b"
    r"|\bno (?:current |exact |specific )?(?:numerical )?(?:value|price|figure|number)\b"
    r"|\b(?:content|text|page|result) focuses\b|\bprovided\b",
    re.IGNORECASE,
)
HINT = (
    "\nSpeak straight to the person as 'you'. Never mention provided text, context, pages, "
    "emails provided, 'the user' or being an AI."
)


def leaks(text: str) -> bool:
    return LEAK.search(text) is not None


def second_person(text: str) -> str:
    for pattern, replacement in USER_WORDS:
        text = pattern.sub(replacement, text)
    return text


def capitalised(text: str) -> str:
    return text[:1].upper() + text[1:]


def non_answer(text: str) -> bool:
    """Says what the text lacks ("does not mention", "no information") instead of answering."""
    return NON_ANSWER.search(text) is not None


def drop_sentences(text: str, unwanted: Callable[[str], object]) -> str:
    """Removes each sentence `unwanted` flags, line by line; a line left empty goes too."""
    lines = []
    for line in text.split("\n"):
        kept = [s for s in SENTENCE.split(line.strip()) if s and not unwanted(s)]
        if kept or not line.strip():
            lines.append(" ".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def scrubbed(text: str) -> str:
    """Drops a "Based on the provided text," opening, turns "the user" into "you" and removes
    any sentence that still talks about its sources."""
    return capitalised(drop_sentences(second_person(LEAD.sub("", text.strip())), leaks))


def phrase(history: list[ModelMessage], variants: tuple[str, ...], **values: str) -> str:
    """The first variant, or the next one when the last reply already used a variant, so the
    same fixed line does not come back twice in a row."""
    last = next(
        (
            part.content
            for message in reversed(history)
            if isinstance(message, ModelResponse)
            for part in message.parts
            if isinstance(part, TextPart)
        ),
        "",
    )
    for index, variant in enumerate(variants):
        if variant.split("{")[0].strip() and variant.split("{")[0].strip() in last:
            return variants[(index + 1) % len(variants)].format(**values)
    return variants[0].format(**values)
