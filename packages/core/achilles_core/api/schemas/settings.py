from pydantic import field_validator

from achilles_core.platform import known_timezone
from achilles_core.services.rules import ClientRules


class UserSettings(ClientRules):
    timezone: str

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str) -> str:
        if not known_timezone(value):
            raise ValueError(f"unknown timezone: {value}")
        return value

    @property
    def rules(self) -> ClientRules:
        return ClientRules.model_validate(self.model_dump(exclude={"timezone"}))
