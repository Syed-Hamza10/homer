import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from homer_core.db.models import Message
from homer_core.services.jobs.turn import JobError, Turn

EVENT = "choice"


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    detail: str
    value: dict[str, Any]


@dataclass(frozen=True)
class Answer:
    message: str
    intent: dict[str, Any]
    picked: dict[str, dict[str, Any]]


class Choice(JobError):
    """A question answered by picking one option. `slot` names what is being chosen, so the job
    finds the pick in `turn.picked` when it runs again; str() is the question in plain words with
    every option, for wherever no card is shown."""

    def __init__(self, slot: str, prompt: str, options: list[Option], text: str) -> None:
        super().__init__(text)
        self.slot = slot
        self.prompt = prompt
        self.options = options


def option_id(key: str) -> str:
    return hashlib.sha1(key.lower().encode()).hexdigest()[:10]


def card(record: dict[str, Any]) -> dict[str, Any]:
    """What the browser sees of a stored question."""
    keys = ("question_id", "prompt", "options", "allow_other", "answered")
    return {key: record.get(key) for key in keys}


def ask(turn: Turn, choice: Choice) -> None:
    """Says the question and streams its card; a turn shows one card, a later question is said
    in full."""
    if turn.question is not None:
        turn.say(str(choice))
        return
    turn.question = {
        "question_id": uuid.uuid4().hex[:12],
        "prompt": choice.prompt,
        "options": [{"id": o.id, "label": o.label, "detail": o.detail} for o in choice.options],
        "allow_other": True,
        "answered": None,
        "text": str(choice),
        "message": turn.message,
        "intent": dict(turn.resolved[-1]) if turn.resolved else {},
        "slot": choice.slot,
        "values": {o.id: o.value for o in choice.options},
    }
    turn.say(choice.prompt)
    turn.emit(EVENT, card(turn.question))


def take(session: Session, stored: list[Message], question_id: str, picked: str) -> Answer | None:
    """Marks the stored question answered with the picked option and returns what the job needs
    to go on; None when the question is unknown, already answered or the option is not one of
    its own."""
    for message in reversed(stored):
        if not message.choice_json:
            continue
        record = json.loads(message.choice_json)
        if record.get("question_id") != question_id:
            continue
        value = record.get("values", {}).get(picked)
        if record.get("answered") or value is None:
            return None
        record["answered"] = picked
        message.choice_json = json.dumps(record)
        session.add(message)
        session.commit()
        return Answer(record["message"], record["intent"], {record["slot"]: value})
    return None


def shown(message: Message) -> str:
    """The message as the model reads it later: a question with every option written out."""
    if message.choice_json:
        return str(json.loads(message.choice_json).get("text") or message.content)
    return message.content
