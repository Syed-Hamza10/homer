import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from homer_core.agent.voice import leaks, phrase, scrubbed

VARIANTS = ("Draft to {who} is ready.", "Here's the draft to {who}.")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Based on the emails provided, Elena asked for the budget numbers.",
            "Elena asked for the budget numbers.",
        ),
        (
            "Elena wants the deck by Friday. The provided text does not say more.",
            "Elena wants the deck by Friday.",
        ),
        (
            "The user's contact Rosa prefers short emails.",
            "Your contact Rosa prefers short emails.",
        ),
        ("Lunch with Tomas is at 16:00.", "Lunch with Tomas is at 16:00."),
    ],
)
def test_scrubbed_speaks_to_the_user(text: str, expected: str) -> None:
    assert scrubbed(text) == expected
    assert not leaks(scrubbed(text))


@pytest.mark.parametrize(
    "text", ["As an AI, I cannot know.", "The context provided is short.", "the user asked"]
)
def test_leaks(text: str) -> None:
    assert leaks(text)


def history(reply: str) -> list[ModelRequest | ModelResponse]:
    return [
        ModelRequest(parts=[UserPromptPart(content="email Rosa")]),
        ModelResponse(parts=[TextPart(content=reply)]),
    ]


def test_phrase_moves_on_when_the_last_reply_used_a_variant() -> None:
    assert phrase([], VARIANTS, who="Rosa") == "Draft to Rosa is ready."
    assert phrase(history("Draft to Rosa is ready."), VARIANTS, who="Elena") == (
        "Here's the draft to Elena."
    )
    assert phrase(history("Here's the draft to Rosa."), VARIANTS, who="Elena") == (
        "Draft to Elena is ready."
    )
    assert phrase(history("Hello"), VARIANTS, who="Elena") == "Draft to Elena is ready."
