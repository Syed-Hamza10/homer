import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e
Frames = list[tuple[str, dict[str, Any]]]


def token_text(frames: Frames) -> str:
    return "".join(data["text"] for name, data in frames if name == "token")


def test_doctor_passes(home: Path, server_env: dict[str, str], doctor_command: list[str]) -> None:
    result = subprocess.run(
        doctor_command, cwd=home, env=server_env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_chat_streams_and_persists(
    first_reply: Frames, logged_in: httpx.Client, prompt: str
) -> None:
    names = [name for name, _ in first_reply]
    assert names[0] == "meta"
    assert "token" in names
    assert names[-1] == "done"
    assert first_reply[-1][1]["output_tokens"] > 0
    assert "PONG" in token_text(first_reply)

    conversations = logged_in.get("/api/conversations").json()
    assert len(conversations) == 1
    conversation_id = first_reply[0][1]["conversation_id"]
    assert conversations[0]["id"] == conversation_id
    messages = logged_in.get(f"/api/conversations/{conversation_id}/messages").json()
    assert [m["role"] for m in messages[:2]] == ["user", "assistant"]
    assert messages[0]["content"] == prompt
    assert "PONG" in messages[1]["content"]


def test_follow_up_uses_history(first_reply: Frames, follow_up_reply: Frames) -> None:
    assert follow_up_reply[0][1]["conversation_id"] == first_reply[0][1]["conversation_id"]
    assert follow_up_reply[-1][0] == "done"
    assert "PONG" in token_text(follow_up_reply)


def test_outbound_log_only_ollama(home: Path, follow_up_reply: Frames) -> None:
    with sqlite3.connect(home / "data" / "homer.db") as connection:
        hosts = connection.execute("SELECT DISTINCT host FROM outbound_log").fetchall()
        calls = connection.execute("SELECT COUNT(*) FROM outbound_log").fetchone()[0]
        requests = connection.execute("SELECT requests FROM token_counter").fetchone()[0]
    assert hosts == [("127.0.0.1:11434",)]
    assert calls >= 2
    assert requests >= 2


def test_unauthenticated_is_rejected(client: httpx.Client) -> None:
    assert client.get("/api/conversations").status_code == 401
