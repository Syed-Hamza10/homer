import re

from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session

from achilles_core.platform import Tier
from achilles_core.services.store import read_setting, write_setting

RULES_KEY = "client_rules"
HOURS = re.compile(r"^\d{2}:\d{2}-\d{2}:\d{2}$")


class ClientRules(BaseModel):
    signature: str = ""
    tone: str = "friendly and concise"
    business_hours: str = "09:00-17:00"
    follow_up_days: int = Field(default=3, ge=1, le=30)
    priority_contacts: list[str] = Field(default_factory=list)
    email_to_self: bool = False
    self_email: str = ""
    model_tier: Tier | None = None

    @field_validator("business_hours")
    @classmethod
    def check_hours(cls, value: str) -> str:
        if not HOURS.match(value):
            raise ValueError("business_hours must look like 09:00-17:00")
        return value


def get_rules(session: Session, user_id: int) -> ClientRules:
    stored = read_setting(session, user_id, RULES_KEY)
    return ClientRules.model_validate_json(stored) if stored else ClientRules()


def save_rules(session: Session, user_id: int, rules: ClientRules) -> ClientRules:
    write_setting(session, user_id, RULES_KEY, rules.model_dump_json())
    return rules
