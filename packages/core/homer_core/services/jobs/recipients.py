import json
import re
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from typing import Any

from homer_core.services.approvals import SEND_ACTION, newest
from homer_core.services.jobs.choice import Choice, Option, option_id
from homer_core.services.jobs.turn import JobError, ReconnectRequired, Turn

CONTACTS_TTL_SECONDS = 300.0
RECENT_SENDERS = 10
CANDIDATES = 5
WEEK_DAYS = 7
CONTACT = "Contact"
EMAILED = "You emailed them"
RECEIVED = "Emailed you"
SENT_LABEL = "SENT"
NOT_A_PERSON = re.compile(
    r"no-?reply|do-?not-?reply|notification|updates|newsletter|mailer-daemon|drive-shares",
    re.IGNORECASE,
)
SERVICE_NAME = re.compile(r"\b(?:via|by)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Person:
    name: str
    email: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.email})" if self.name else self.email

    @property
    def shown(self) -> str:
        return self.name or self.email


@dataclass(frozen=True)
class Candidate(Person):
    source: str = ""

    @property
    def id(self) -> str:
        return option_id(self.email)

    @property
    def option(self) -> Option:
        detail = f"{self.email} · {self.source}" if self.name else self.source
        return Option(self.id, self.shown, detail, {"name": self.name, "email": self.email})


def listed(result: Any, key: str) -> list[dict[str, Any]]:
    items = result.get(key, []) if isinstance(result, dict) else result
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


async def contacts(turn: Turn, word: str) -> list[Person]:
    key = word.lower()
    cached = turn.runtime.contacts.get(key)
    if cached is not None and cached[0] > time.monotonic():
        found = cached[1]
    else:
        found = listed(await turn.call("google", "contacts_search", {"query": word}), "contacts")
        turn.runtime.contacts[key] = (time.monotonic() + CONTACTS_TTL_SECONDS, found)
    return [Person(c.get("name", ""), c.get("email", "").lower()) for c in found if c.get("email")]


async def recent_senders(turn: Turn, word: str) -> list[Person]:
    args = {"query": f"from:{word}", "max_results": RECENT_SENDERS}
    messages = listed(await turn.call("google", "mail_search", args), "messages")
    senders = [parseaddr(message.get("from", "")) for message in messages]
    return [Person(name, email.lower()) for name, email in senders if email]


def matching[P: Person](people: list[P], who: str) -> list[P]:
    """The people whose name or address holds every word, the exact name only when one has it;
    one per address, the first kept, with a name from a later one when it had none."""
    words = who.lower().split()
    found = [
        person
        for person in people
        if all(word in f"{person.name} {person.email}".lower() for word in words)
    ]
    exact = [person for person in found if person.name.lower() == who.lower()]
    unique: dict[str, P] = {}
    for person in exact or found:
        kept = unique.setdefault(person.email, person)
        if not kept.name and person.name:
            unique[person.email] = replace(kept, name=person.name)
    return list(unique.values())


def is_person(person: Person) -> bool:
    """False for robot senders: no-reply and notification addresses, and names like
    "Sam (via Google Drive)"."""
    return not NOT_A_PERSON.search(person.email) and not SERVICE_NAME.search(person.name)


def sent_at(message: dict[str, Any]) -> datetime | None:
    internal = (message.get("metadata") or {}).get("internal_date")
    if internal:
        return datetime.fromtimestamp(int(internal) / 1000, UTC)
    try:
        moment = parsedate_to_datetime(message.get("date", ""))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def ago(moment: datetime, now: datetime) -> str:
    days = (now.date() - moment.astimezone(now.tzinfo).date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < WEEK_DAYS:
        return f"{days} days ago"
    year = f" {moment.year}" if moment.year != now.year else ""
    return f"on {moment.day} {moment:%b}{year}"


def seen(prefix: str, message: dict[str, Any], now: datetime) -> str:
    moment = sent_at(message)
    return f"{prefix} {ago(moment, now)}" if moment else prefix


def newest_first(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    oldest = datetime.min.replace(tzinfo=UTC)
    return sorted(messages, key=lambda message: sent_at(message) or oldest, reverse=True)


def mailed(
    sent: list[dict[str, Any]], received: list[dict[str, Any]], now: datetime
) -> list[Candidate]:
    """People the user wrote to, newest first, then people who wrote to the user; mailing-list
    senders and the user's own address are left out."""
    me = {
        parseaddr(message.get("from", ""))[1].lower()
        for message in sent + received
        if SENT_LABEL in message.get("labels", [])
    }
    wrote = [
        Candidate(name, email.lower(), seen(EMAILED, message, now))
        for message in newest_first(sent)
        for name, email in getaddresses([message.get("to", "")])
        if email
    ]
    heard = [
        Candidate(name, email.lower(), seen(RECEIVED, message, now))
        for message in newest_first(received)
        if not (message.get("metadata") or {}).get("list_unsubscribe")
        for name, email in [parseaddr(message.get("from", ""))]
        if email
    ]
    return [person for person in wrote + heard if person.email not in me]


async def search(turn: Turn, query: str) -> list[dict[str, Any]]:
    args = {"query": query, "max_results": RECENT_SENDERS}
    return listed(await turn.call("google", "mail_search", args), "messages")


async def candidates(turn: Turn, who: str) -> list[Candidate]:
    """Saved contacts first; unless one contact matches, then people the user emailed and people
    who emailed the user, robots left out, at most five."""
    first = who.split()[0]
    saved = [Candidate(p.name, p.email, CONTACT) for p in await contacts(turn, first)]
    found = matching([person for person in saved if is_person(person)], who)
    if len(found) == 1:
        return found
    sent = await search(turn, f"in:sent to:{first}")
    received = await search(turn, f"from:{first}")
    everyone = saved + mailed(sent, received, turn.now)
    return matching([person for person in everyone if is_person(person)], who)[:CANDIDATES]


def written_here(turn: Turn, who: str) -> Person | None:
    """Someone an email in this chat already went to, when their name or address holds every
    word asked for, so a second email to them needs no lookup."""
    if turn.conversation_id is None:
        return None
    words = who.lower().split()
    for approval in newest(turn.session, turn.user, SEND_ACTION, turn.conversation_id):
        payload = json.loads(approval.payload_json)
        name, email = str(payload.get("to_name", "")), str(payload.get("to", ""))
        if email and words and all(word in f"{name} {email}".lower() for word in words):
            return Person(name, email.lower())
    return None


def slot(who: str) -> str:
    return "person:" + " ".join(who.lower().split())


def which(who: str, people: list[Candidate]) -> Choice:
    shown = who.title() if who.islower() else who
    options = " or ".join(person.label for person in people)
    return Choice(
        slot(who),
        f"Which {shown} do you mean?",
        [person.option for person in people],
        f"Which {shown} do you mean: {options}?",
    )


def typed(turn: Turn, email: str) -> bool:
    return email.lower() in turn.message.lower()


def as_words(email: str) -> str:
    """The name words in an address the model made up: 'accounts@harbor&pine.com' gives
    'accounts harbor pine'."""
    local, _, domain = email.lower().partition("@")
    labels = domain.split(".")[:-1] if "." in domain else [domain]
    return " ".join(w for w in re.split(r"[^a-z0-9]+", " ".join([local, *labels])) if w)


async def name_for(turn: Turn, email: str) -> str:
    """The person's name from contacts or from the headers of mail they sent, else ''."""
    try:
        for source in (contacts, recent_senders):
            for person in await source(turn, email):
                if person.email == email and person.name:
                    return person.name
    except ReconnectRequired:
        raise
    except JobError:
        return ""
    return ""


async def resolve(turn: Turn, who: str, from_header: bool = False) -> Person:
    """Finds one address for a name or address; asks the user when there are none, and offers
    a pick-one card when there are several. A pick from that card, in `turn.picked`, wins. An
    address is used only as the user typed it or as a mail header carries it; one the model
    wrote is searched for by its words instead, so no address is ever made up."""
    who = who.strip()
    if "@" in who:
        name, email = parseaddr(who)
        email = email.lower()
        if from_header:
            return Person(name, email)
        if typed(turn, email):
            return Person(name or await name_for(turn, email), email)
        who = as_words(email)
    if not who:
        raise JobError("Who should it go to? Give me a name or an email address.")
    chosen = turn.picked.get(slot(who))
    if chosen is not None:
        return Person(chosen["name"], chosen["email"])
    known = written_here(turn, who)
    if known is not None:
        return known
    people = await candidates(turn, who)
    if len(people) == 1:
        return Person(people[0].name, people[0].email)
    if not people:
        raise JobError(f"I could not find an email address for {who}. What is their address?")
    raise which(who, people)
