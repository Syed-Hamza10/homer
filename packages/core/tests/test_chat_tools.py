from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models import Model
from structlog.testing import capture_logs

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


DRAFT_ARGS = {"to": "ada@example.test", "subject": "Re: Invoice 42", "body": "Paid today."}
HISTORY_DRAFT_ID = "r-8412837461928374612"


class TestDraftIdHandoff:
    @pytest.fixture
    def model(self, scripted: Scripted, steps: list[Any]) -> Model:
        return scripted("mail", steps, [])

    @pytest.mark.parametrize(
        "steps",
        [[[("mail_draft", DRAFT_ARGS)], [("mail_send", {"draft_id": "1"})], "Asked to send."]],
    )
    def test_guessed_id_is_replaced_by_the_only_draft_of_the_run(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        with capture_logs() as logs:
            frames = post_chat({"message": "Reply to Ada that the invoice is paid and send it"})
        guessed = [c["args"] for c in of(frames, "tool_call") if c["name"] == "mail_send"]
        assert guessed == [{"draft_id": "1"}]
        requested = of(frames, "approval_required")
        assert [a["preview"] for a in requested] == ["Send draft d1"]
        assert logged_in.get("/api/approvals").json()[0]["payload"] == {"draft_id": "d1"}
        assert {"event": "draft_id_substituted", "given": "1", "draft_id": "d1"}.items() <= next(
            entry for entry in logs if entry["event"] == "draft_id_substituted"
        ).items()

    @pytest.mark.parametrize(
        "steps",
        [[[("mail_draft", DRAFT_ARGS)], [("mail_send", {"draft_id": "d1"})], "Asked to send."]],
    )
    def test_real_id_passes_unchanged(self, logged_in: TestClient, post_chat: PostChat) -> None:
        with capture_logs() as logs:
            frames = post_chat({"message": "Reply to Ada and send it"})
        assert [a["preview"] for a in of(frames, "approval_required")] == ["Send draft d1"]
        assert not [entry for entry in logs if entry["event"] == "draft_id_substituted"]

    @pytest.mark.parametrize(
        "steps",
        [
            [
                [("mail_draft", DRAFT_ARGS), ("mail_draft", {**DRAFT_ARGS, "subject": "Lunch"})],
                [("mail_send", {"draft_id": "1"})],
                "Which one?",
            ]
        ],
    )
    def test_guess_among_several_drafts_is_refused_without_calling_the_server(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        frames = post_chat({"message": "Draft two replies and send the first"})
        assert of(frames, "approval_required") == []
        sent = next(r for r in of(frames, "tool_result") if r["name"] == "mail_send")
        assert '"error": "unknown_draft_id"' in sent["summary"]
        assert '"known_draft_ids": ["d1", "d2"]' in sent["summary"]
        assert logged_in.get("/api/approvals").json() == []

    @pytest.mark.parametrize(
        "steps",
        [
            [
                f"Draft {HISTORY_DRAFT_ID} is ready. Shall I send it?",
                [("mail_send", {"draft_id": "1"})],
                "Asked to send.",
            ]
        ],
    )
    def test_draft_mentioned_earlier_in_the_conversation_is_known(
        self, logged_in: TestClient, post_chat: PostChat
    ) -> None:
        first = post_chat({"message": "Draft a reply to Ada"})
        conversation_id = first[0][1]["conversation_id"]
        frames = post_chat({"conversation_id": conversation_id, "message": "Yes, send it"})
        assert [a["preview"] for a in of(frames, "approval_required")] == [
            f"Send draft {HISTORY_DRAFT_ID}"
        ]


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
