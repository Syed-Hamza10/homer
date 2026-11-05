import json
import re

from homer_core.db.models import Approval
from homer_core.services import approval_edits
from homer_core.services.approval_edits import MailEdit
from homer_core.services.jobs.send_email import revise
from homer_core.services.jobs.turn import Turn

UPDATED = "Updated the draft. Edit it or press Send."
LEAD = r"^(?:(?:ok|okay|please|pls|can you|could you|now|also|and|but)[,]?\s+)*"
SUBJECT_TO = re.compile(
    r"\bsubject(?: line)?\s*(?:to|should be|is now|as|:)\s*:?\s*(.+)$", re.IGNORECASE | re.DOTALL
)
SUBJECT_ONLY = re.compile(
    LEAD + r"(?:(?:change|set|make|update|use|rename)\s+)?(?:the\s+)?subject(?: line)?\s"
    r"*(?:to|should be|is now|as|:)",
    re.IGNORECASE,
)
QUOTED = re.compile(r"[\"“‘'](.+?)[\"”’']")


def literal_subject(instruction: str) -> str | None:
    """The subject the user typed after 'subject to' (or in quotes there), taken as is."""
    match = SUBJECT_TO.search(instruction.strip())
    if match is None:
        return None
    text = match.group(1).strip()
    quoted = QUOTED.search(text)
    return quoted.group(1).strip() if quoted else text.rstrip(".").strip()


async def run(turn: Turn, approval: Approval) -> None:
    payload = json.loads(approval.payload_json)
    subject = literal_subject(turn.message)
    body = payload["body"]
    if subject is None or not SUBJECT_ONLY.match(turn.message.strip()):
        text = await revise(turn, payload["subject"], body, turn.message)
        body = text.body
        if subject is None:
            replying = payload["subject"].lower().startswith("re:")
            subject = payload["subject"] if replying else text.subject
    change = MailEdit(to=payload["to"], subject=subject, body=body)
    fresh = await approval_edits.edit(
        turn.session, turn.user, approval.id, turn.runtime.manager, change
    )
    turn.requested(fresh)
    turn.say(UPDATED)
