import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from achilles_sim.events import Calendar
from achilles_sim.mailbox import Mailbox

DEFAULT_SEED = Path(__file__).with_name("seed.json")
KNOWN_TOKEN = "sim-access-token"


class State:
    def __init__(self, seed_path: Path = DEFAULT_SEED) -> None:
        self.seed_path = seed_path
        self.reset()

    def reset(self) -> None:
        seed = json.loads(self.seed_path.read_text())
        self.now = datetime.now(UTC).replace(microsecond=0)
        self.mailbox = Mailbox(seed, self.now)
        self.calendar = Calendar(seed, self.now)
        self.contacts: list[dict[str, Any]] = seed["contacts"]
        self.tokens: set[str] = {KNOWN_TOKEN}
        self.token_requests = 0

    def issue_token(self) -> str:
        token = f"sim-access-{secrets.token_hex(8)}"
        self.tokens.add(token)
        self.token_requests += 1
        return token

    def search_contacts(self, query: str) -> list[dict[str, Any]]:
        needle = query.lower()
        return [
            contact
            for contact in self.contacts
            if needle in f"{contact['given']} {contact['family']} {contact['email']}".lower()
        ]

    def counts(self) -> dict[str, int]:
        labels = [label for m in self.mailbox.messages.values() for label in m["labelIds"]]
        return {
            "messages": len(self.mailbox.messages),
            "sent": labels.count("SENT"),
            "drafts": len(self.mailbox.drafts),
            "labels": len(self.mailbox.labels),
            "history_id": self.mailbox.history_id,
            "events": len(self.calendar.active()),
            "contacts": len(self.contacts),
            "token_requests": self.token_requests,
        }
