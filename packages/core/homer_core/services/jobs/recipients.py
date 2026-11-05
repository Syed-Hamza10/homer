import time
from dataclasses import dataclass
from email.utils import parseaddr
from typing import Any

from homer_core.services.jobs.turn import JobError, Turn

CONTACTS_TTL_SECONDS = 300.0
RECENT_SENDERS = 10


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


def matching(people: list[Person], who: str) -> list[Person]:
    words = who.lower().split()
    found = [
        person
        for person in people
        if all(word in f"{person.name} {person.email}".lower() for word in words)
    ]
    exact = [person for person in found if person.name.lower() == who.lower()]
    unique = {person.email: person for person in exact or found}
    return list(unique.values())


async def resolve(turn: Turn, who: str) -> Person:
    """Finds one address for a name or address; asks the user when there are none or several."""
    who = who.strip()
    if "@" in who:
        name, email = parseaddr(who)
        return Person(name, email.lower())
    if not who:
        raise JobError("Who should it go to? Give me a name or an email address.")
    first = who.split()[0]
    people = matching(await contacts(turn, first), who)
    if not people:
        people = matching(await recent_senders(turn, first), who)
    if len(people) == 1:
        return people[0]
    if not people:
        raise JobError(f"I could not find an email address for {who}. What is their address?")
    options = " or ".join(person.label for person in people)
    raise JobError(f"Which {who} do you mean: {options}?")
