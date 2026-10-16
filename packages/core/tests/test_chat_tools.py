from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models import Model

from achilles_core.agent.toolsets import TOOLSETS

Frames = list[tuple[str, dict[str, Any]]]
PostChat = Callable[[dict[str, Any]], Frames]
Scripted = Callable[..., Model]

FAKE_TOOLS = {
    "mail_search",
    "mail_get",
    "mail_thread",
    "mail_draft",
    "mail_send",
    "mail_label",
    "mail_archive",
    "cal_list",
    "cal_find_free_slots",
    "cal_create",
    "contacts_search",
    "now",
    "parse_datetime",
    "remind",
}


def of(frames: Frames, name: str) -> list[dict[str, Any]]:
    return [data for event, data in frames if event == name]


class TestApprovalFlow:
    @pytest.fixture
    def seen_tools(self) -> list[list[str]]:
        return []

    @pytest.fixture
    def model(self, scripted: Scripted, seen_tools: list[list[str]]) -> Model:
        steps = [
            [("mail_get", {"message_id": "m1"})],
            [("mail_send", {"draft_id": "d1"}), ("mail_archive", {"message_id": "m1"})],
            "Waiting for your approval.",
        ]
        return scripted("mail", steps, seen_tools)

    def test_tier1_and_tainted_tier2_become_approvals(
        self,
        logged_in: TestClient,
        post_chat: PostChat,
        fake_google: ModuleType,
        seen_tools: list[list[str]],
    ) -> None:
        frames = post_chat({"message": "Reply to Ada about the invoice and archive it"})
        names = [name for name, _ in frames]
        assert names[0] == "meta" and names[-1] == "done"

        calls = of(frames, "tool_call")
        assert calls[0] == {"name": "mail_get", "args": {"message_id": "m1"}}
        assert {c["name"] for c in calls[1:]} == {"mail_send", "mail_archive"}
        results = {r["name"]: r["summary"] for r in of(frames, "tool_result")}
        assert set(results) == {"mail_get", "mail_send", "mail_archive"}
        assert results["mail_send"].startswith("Approval #")
        assert results["mail_send"].endswith("requested; the user will decide")

        requested = {a["action"]: a for a in of(frames, "approval_required")}
        assert {a["approval_id"] for a in requested.values()} == {1, 2}
        assert requested["mail_send"]["preview"] == "Send draft d1"
        assert "untrusted" in requested["mail_archive"]["preview"]
        assert "".join(t["text"] for t in of(frames, "token")) == "Waiting for your approval."
        assert fake_google.executed == []

        pending = logged_in.get("/api/approvals").json()
        assert {a["action"]: a["payload"] for a in pending} == {
            "mail_send": {"draft_id": "d1"},
            "mail_archive": {"message_id": "m1"},
        }
        for tools in seen_tools:
            assert "execute" not in tools and "health" not in tools
            assert set(tools) == set(TOOLSETS["mail"]) & FAKE_TOOLS


class TestTier2WithoutUntrustedContent:
    @pytest.fixture
    def model(self, scripted: Scripted) -> Model:
        return scripted("mail", [[("mail_archive", {"message_id": "m2"})], "Archived."], [])

    def test_archive_runs_directly(
        self, logged_in: TestClient, post_chat: PostChat, fake_google: ModuleType
    ) -> None:
        frames = post_chat({"message": "Archive m2"})
        assert of(frames, "approval_required") == []
        assert '"archived": true' in of(frames, "tool_result")[0]["summary"]
        assert logged_in.get("/api/approvals").json() == []


class TestToolsetVisibility:
    @pytest.fixture(params=list(TOOLSETS))
    def toolset_name(self, request: pytest.FixtureRequest) -> str:
        return request.param

    @pytest.fixture
    def seen_tools(self) -> list[list[str]]:
        return []

    @pytest.fixture
    def model(self, scripted: Scripted, toolset_name: str, seen_tools: list[list[str]]) -> Model:
        return scripted(toolset_name, ["ok"], seen_tools)

    def test_model_sees_only_the_curated_list(
        self, post_chat: PostChat, toolset_name: str, seen_tools: list[list[str]]
    ) -> None:
        post_chat({"message": "anything"})
        assert set(seen_tools[0]) == set(TOOLSETS[toolset_name]) & FAKE_TOOLS
        assert len(seen_tools[0]) <= 10
