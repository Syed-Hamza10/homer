import re

import structlog

log = structlog.get_logger(__name__)

HONEST = (
    "I have not sent, scheduled or created anything. Tell me what to do and I will prepare it "
    "for your approval."
)
SENT = (
    r"\bI(?:'ve| have| just| already)*\s+(?:sent|scheduled|booked|created|emailed|forwarded"
    r"|set up|added (?:it|the event|the meeting|a reminder))\b"
    r"|\b(?:email|message|reply|invite|invitation|draft|it)\b(?:[^.\n]|\.(?=\S)){0,80}?"
    r"\b(?:has been|have been|is now)\s+(?:sent|delivered|fired off)\b"
)
SENT_CLAIM = re.compile(SENT, re.IGNORECASE)
CLAIM = re.compile(
    SENT + r"|\b(?:email|message|reply|invite|invitation|event|meeting|reminder)\s+"
    r"(?:has been|have been|was|is now)\s+(?:sent|scheduled|booked|created|added|set)\b"
    r"|\b(?:sent|scheduled|created|booked) successfully\b"
    r"|\bsuccessfully (?:sent|scheduled|created|booked)\b"
    r"|\bsending (?:the |your |an |this |that )?(?:email|message|reply|mail|it|now)\b"
    r"|\bsen(?:d|t|ding)\b.*\bdone\b"
    r"|\b(?:on (?:its|it's) way|gone out|went out|ready to send)\b"
    r"|\b(?:updated|changed|added|edited|rewrote|revised|shortened)\b[^.\n]*"
    r"\b(?:draft|subject|body)\b"
    r"|\b(?:draft|subject|body|email) (?:is |has been |was )?(?:updated|changed|edited)\b",
    re.IGNORECASE | re.DOTALL,
)

CALENDAR_CLAIM = re.compile(
    r"\bI(?:'ve| have| just| already)*\s+(?:cancell?ed|moved|rescheduled|deleted|removed"
    r"|updated|changed|shifted)\b"
    r"|\b(?:event|meeting|lunch|call|appointment|it)\s+(?:has been|have been|was|is now)\s+"
    r"(?:cancell?ed|moved|rescheduled|deleted|removed|updated|changed)\b"
    r"|\b(?:cancell?ed|moved|rescheduled|deleted) (?:it )?(?:successfully|for you)\b"
    r"|\b(?:event|meeting|call)\b[^.\n]{0,80}\bis ready\b",
    re.IGNORECASE,
)


def claims_sending(text: str) -> bool:
    """A first-person "I've sent" or "the email ... has been sent", in any model answer."""
    return SENT_CLAIM.search(text) is not None


def review(text: str, acted: bool) -> str:
    """Returns the text, or a fixed honest sentence when it claims an action nothing backs."""
    if acted or not (CLAIM.search(text) or CALENDAR_CLAIM.search(text)):
        return text
    log.warning("unbacked_action_claim", text=text)
    return HONEST
