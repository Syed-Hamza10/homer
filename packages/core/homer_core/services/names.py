import re
from email.utils import parseaddr

from sqlmodel import Session, select

from homer_core.db.models import EmailCache, User

ID_PREFIX = re.compile(r"^\S*\d\S*?\s*[-_|:]\s*")
ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LETTERS = re.compile(r"[a-z]{2,}")
HONORIFICS = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "miss",
        "mx",
        "dr",
        "prof",
        "sir",
        "madam",
        "engr",
        "syed",
        "sayed",
        "sayyid",
        "sheikh",
        "shaikh",
        "hafiz",
        "mian",
    }
)


def call_name(display: str) -> str:
    """The first name to greet someone by: no ID-like prefix (e.g. a student number), no
    leading honorific while another name follows."""
    words = [
        word.strip(",")
        for word in ID_PREFIX.sub("", display.strip()).split()
        if "@" not in word and not any(char.isdigit() for char in word)
    ]
    while len(words) > 1 and words[0].rstrip(".").lower() in HONORIFICS:
        words.pop(0)
    first = words[0] if words else ""
    return first.capitalize() if first.isupper() and len(first) > 1 else first


def address_name(address: str) -> str:
    """A readable first name guessed from an address's local part, e.g. "ali30k@x" -> "Ali"."""
    found = LETTERS.search(address.split("@")[0].lower())
    return found.group().capitalize() if found else address


def known_names(session: Session, user: User) -> dict[str, str]:
    """Address -> first name, from the display names on cached mail."""
    names: dict[str, str] = {}
    for sender in session.exec(select(EmailCache.sender).where(EmailCache.user_id == user.id)):
        name, address = parseaddr(sender)
        first = call_name(name)
        if first and address:
            names.setdefault(address.lower(), first)
    return names


def person(sender: str, known: dict[str, str]) -> str:
    name, address = parseaddr(sender)
    return call_name(name) or known.get(address.lower()) or address_name(address or sender)


def humanise(text: str, known: dict[str, str]) -> str:
    """Replaces raw email addresses in text with the person's first name."""
    return ADDRESS.sub(
        lambda found: known.get(found.group().lower()) or address_name(found.group()), text
    )
