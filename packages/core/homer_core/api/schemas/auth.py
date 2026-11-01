from pydantic import BaseModel


class LoginRequest(BaseModel):
    passphrase: str


class MeResponse(BaseModel):
    user_id: int
    name: str
