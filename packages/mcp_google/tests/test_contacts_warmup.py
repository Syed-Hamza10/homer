from typing import Any

import pytest

from homer_mcp_google import tools
from homer_mcp_google.client import GoogleError
from homer_mcp_google.tools import GoogleTools

COLD = GoogleError(
    400, "FAILED_PRECONDITION: Request failed due to cold cache data. Please retry in 5 seconds"
)
FOUND = {"results": [{"person": {"names": [{"displayName": "Ada"}], "emailAddresses": []}}]}


class ScriptedClient:
    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.queries: list[str] = []

    async def get(self, path: str, **params: Any) -> Any:
        self.queries.append(params["query"])
        reply = self.replies.pop(0) if self.replies else {}
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    seen: list[float] = []

    async def sleep(seconds: float) -> None:
        seen.append(seconds)

    monkeypatch.setattr(tools.asyncio, "sleep", sleep)
    return seen


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [1000.0]
    monkeypatch.setattr(tools.time, "monotonic", lambda: now[0])
    return now


async def test_first_search_warms_up_first(clock: list[float]) -> None:
    client = ScriptedClient({}, FOUND)
    found = await GoogleTools(client).contacts_search("ada")  # type: ignore[arg-type]
    assert client.queries == ["", "ada"]
    assert found["contacts"][0]["name"] == "Ada"


async def test_warm_up_repeats_only_after_ten_minutes(clock: list[float]) -> None:
    client = ScriptedClient()
    google = GoogleTools(client)  # type: ignore[arg-type]
    await google.contacts_search("a")
    clock[0] += 599
    await google.contacts_search("b")
    clock[0] += 2
    await google.contacts_search("c")
    assert client.queries == ["", "a", "b", "", "c"]


async def test_failed_warm_up_is_ignored_and_tried_again(clock: list[float]) -> None:
    client = ScriptedClient(GoogleError(500, "boom"), FOUND, {}, {})
    google = GoogleTools(client)  # type: ignore[arg-type]
    assert (await google.contacts_search("ada"))["contacts"][0]["name"] == "Ada"
    await google.contacts_search("ada")
    assert client.queries == ["", "ada", "", "ada"]


async def test_cold_error_is_retried_once_after_five_seconds(
    clock: list[float], waits: list[float]
) -> None:
    client = ScriptedClient({}, COLD, FOUND)
    found = await GoogleTools(client).contacts_search("ada")  # type: ignore[arg-type]
    assert found["contacts"][0]["name"] == "Ada"
    assert waits == [5.0]
    assert client.queries == ["", "ada", "ada"]


async def test_two_cold_errors_return_the_warming_error(
    clock: list[float], waits: list[float]
) -> None:
    client = ScriptedClient({}, COLD, COLD)
    found = await GoogleTools(client).contacts_search("ada")  # type: ignore[arg-type]
    assert found == {"error": "google_contacts_warming"}
    assert client.queries == ["", "ada", "ada"]


async def test_other_errors_are_not_retried(clock: list[float], waits: list[float]) -> None:
    client = ScriptedClient({}, GoogleError(400, "Invalid argument"))
    found = await GoogleTools(client).contacts_search("ada")  # type: ignore[arg-type]
    assert found["error"] == "google_error"
    assert waits == []
