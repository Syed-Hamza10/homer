from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models import Model

from .conftest import JobModel, PostChat
from .test_jobs import said

IMRAN = "Imran Qureshi, your opposing counsel, only takes meetings after 4pm."
MORNINGS = "Imran Qureshi prefers meetings in the mornings, before 11."
OMAR = "Omar's flight lands on Friday."


def remember(fact: str, person: str | None = None) -> list[dict[str, Any]]:
    return [{"kind": "remember", "fact": fact, "about_person": person}]


def correct(about: str, new_fact: str) -> list[dict[str, Any]]:
    return [{"kind": "correct_memory", "about": about, "new_fact": new_fact}]


def texts(client: TestClient) -> list[str]:
    return [fact["text"] for fact in client.get("/api/facts").json()]


class TestCorrection:
    @pytest.fixture
    def model(self, jobs: JobModel) -> Model:
        turns = [
            remember(IMRAN, "Imran Qureshi"),
            remember(OMAR, "Omar"),
            [{"kind": "recall", "about": "Imran"}],
            correct("he", MORNINGS),
            correct("Omar's flight", "Omar's flight lands on Saturday."),
        ]
        return jobs(turns, text="After 4pm.")

    def test_a_correction_replaces_the_fact_instead_of_adding_one(
        self, post_chat: PostChat, logged_in: TestClient
    ) -> None:
        chat = post_chat({"message": f"note: {IMRAN}"})[0][1]["conversation_id"]
        post_chat({"message": f"remember {OMAR}", "conversation_id": chat})
        post_chat({"message": "when does imran take meetings", "conversation_id": chat})
        fixed = post_chat({"message": "actually he prefers mornings", "conversation_id": chat})
        assert said(fixed) == f"Updated: {MORNINGS}"
        assert sorted(texts(logged_in)) == sorted([MORNINGS, OMAR])
        other = post_chat({"message": "oops, the flight is saturday"})
        assert said(other) == "Updated: Omar's flight lands on Saturday."
        assert sorted(texts(logged_in)) == sorted([MORNINGS, "Omar's flight lands on Saturday."])


class TestForget:
    @pytest.fixture
    def model(self, jobs: JobModel) -> Model:
        turns = [
            remember(IMRAN, "Imran Qureshi"),
            remember("Imran Qureshi works at Harbor Legal.", "Imran Qureshi"),
            remember(OMAR, "Omar"),
            [{"kind": "forget", "about": "Imran"}],
            [{"kind": "recall", "about": "Imran"}],
        ]
        return jobs(turns)

    def test_forget_deletes_every_fact_about_the_person(
        self, post_chat: PostChat, logged_in: TestClient
    ) -> None:
        for message in ("one", "two", "three"):
            post_chat({"message": message})
        gone = post_chat({"message": "forget that about imran"})
        assert said(gone).startswith("Forgot 2 things:\n- ")
        assert texts(logged_in) == [OMAR]
        assert said(post_chat({"message": "what do you know about imran now"})) == (
            "I have nothing saved about Imran."
        )


class TestRecall:
    @pytest.fixture
    def model(self, jobs: JobModel) -> Model:
        turns = [
            remember("Your nephew Tariq has his wedding on 12 December.", "Tariq"),
            remember("Your nephew Tariq has his wedding on 19 December.", "Tariq"),
            [{"kind": "recall", "about": "Tariq's wedding"}],
        ]
        answer = {"answer": "Tariq's wedding is on 19 December.", "outdated": [1]}
        return jobs(turns, recalled=answer)

    def test_the_newer_fact_wins_and_the_older_one_is_deleted(
        self, post_chat: PostChat, logged_in: TestClient
    ) -> None:
        post_chat({"message": "one"})
        post_chat({"message": "two"})
        asked = post_chat({"message": "so what date is Tariq's wedding"})
        assert said(asked) == "Tariq's wedding is on 19 December."
        assert texts(logged_in) == ["Your nephew Tariq has his wedding on 19 December."]


class TestRoundSeven:
    @pytest.fixture
    def model(self, jobs: JobModel) -> Model:
        turns = [
            remember("Your pharmacist is Mr Idris and he shuts at 7pm.", "Idris"),
            [{"kind": "send_status", "about": "pharmacist closing time"}],
        ]
        return jobs(turns, recalled={"answer": "He shuts at 7pm."}, text="Chat answer.")

    def test_a_terse_fact_question_sent_to_mail_status_recalls_the_fact(
        self, post_chat: PostChat
    ) -> None:
        post_chat({"message": "keep in mind my pharmacist is Mr Idris and he shuts at 7pm"})
        assert said(post_chat({"message": "pharmacist closing time, one line"})) == (
            "He shuts at 7pm."
        )
