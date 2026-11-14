from pydantic import BaseModel


class ChoiceHint(BaseModel):
    question_id: str
    option_id: str


class ChatRequest(BaseModel):
    conversation_id: int | None = None
    message: str
    choice: ChoiceHint | None = None
