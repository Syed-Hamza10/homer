from pathlib import Path

import pytest
from sqlmodel import Session
from typer.testing import CliRunner

from achilles_core.cli import app
from achilles_core.db.session import make_engine, run_migrations
from achilles_core.llm import chat_model_tag
from achilles_core.platform import ensure_home
from achilles_core.services.rules import get_rules
from achilles_core.services.users import ensure_first_user, first_user

runner = CliRunner()


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home"
    ensure_home(path)
    engine = make_engine(path)
    run_migrations(engine)
    with Session(engine) as session:
        ensure_first_user(session, "Tester", "UTC")
    engine.dispose()
    monkeypatch.setenv("ACHILLES_HOME", str(path))
    monkeypatch.setenv("ACHILLES_PASSPHRASE", "test-pass")
    return path


def test_model_use_saves_the_tier(home: Path) -> None:
    result = runner.invoke(app, ["model", "use", "supported"])
    assert result.exit_code == 0, result.output

    engine = make_engine(home)
    with Session(engine) as session:
        user = first_user(session)
        assert user is not None
        assert get_rules(session, user.id).model_tier == "supported"
    engine.dispose()


def test_model_use_accepts_a_manifest_tag(home: Path) -> None:
    result = runner.invoke(app, ["model", "use", chat_model_tag("degraded")])
    assert result.exit_code == 0, result.output

    engine = make_engine(home)
    with Session(engine) as session:
        user = first_user(session)
        assert user is not None
        assert get_rules(session, user.id).model_tier == "degraded"
    engine.dispose()


def test_model_use_rejects_an_unknown_tier(home: Path) -> None:
    result = runner.invoke(app, ["model", "use", "banana"])
    assert result.exit_code == 2
    assert "choose a tag" in result.output


def test_backup_command_writes_a_file(home: Path) -> None:
    result = runner.invoke(app, ["backup"])
    assert result.exit_code == 0, result.output
    assert "Backup written" in result.output
    assert list((home / "backups").glob("achilles-*.tar.gz"))


def test_privacy_command_prints_the_hosts(home: Path) -> None:
    result = runner.invoke(app, ["privacy"])
    assert result.exit_code == 0
    assert "www.googleapis.com" in result.output
    assert "html.duckduckgo.com" in result.output


def test_forget_removes_the_user(home: Path) -> None:
    result = runner.invoke(app, ["forget", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Deleted" in result.output

    engine = make_engine(home)
    with Session(engine) as session:
        assert first_user(session) is None
    engine.dispose()


def test_forget_requires_confirmation(home: Path) -> None:
    result = runner.invoke(app, ["forget"])
    assert result.exit_code == 1
    assert "Pass --yes" in result.output
