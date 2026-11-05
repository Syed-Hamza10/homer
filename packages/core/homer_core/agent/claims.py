import re

import structlog

log = structlog.get_logger(__name__)

HONEST = (
    "I have not sent, scheduled or created anything. Tell me what to do and I will prepare it "
    "for your approval."
)
CLAIM = re.compile(
    r"\bI(?:'ve| have| just| already)*\s+(?:sent|scheduled|booked|created|emailed|forwarded"
    r"|set up|added (?:it|the event|the meeting|a reminder))\b"
    r"|\b(?:email|message|reply|invite|invitation|event|meeting|reminder)\s+"
    r"(?:has been|have been|was|is now)\s+(?:sent|scheduled|booked|created|added|set)\b"
    r"|\b(?:sent|scheduled|created|booked) successfully\b"
    r"|\bsuccessfully (?:sent|scheduled|created|booked)\b",
    re.IGNORECASE,
)


def review(text: str, acted: bool) -> str:
    """Returns the text, or a fixed honest sentence when it claims an action nothing backs."""
    if acted or not CLAIM.search(text):
        return text
    log.warning("unbacked_action_claim", text=text)
    return HONEST
