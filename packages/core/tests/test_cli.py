import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session
from typer.testing import CliRunner

from homer_core import cli, platform
from homer_core.cli import app
from homer_core.db.session import make_engine, run_migrations
from homer_core.llm import chat_model_tag
from homer_core.platform import ensure_home
from homer_core.services.rules import get_rules
from homer_core.services.users import ensure_first_user, first_user

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
    monkeypatch.setenv("HOMER_HOME", str(path))
    monkeypatch.setenv("HOMER_PASSPHRASE", "test-pass")
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
    assert "--include-secrets" in result.output
    assert list((home / "backups").glob("homer-*.tar.gz"))


def test_backup_command_can_include_secrets(home: Path) -> None:
    (home / ".env").write_text("HOMER_PASSPHRASE=test-pass\n")
    result = runner.invoke(app, ["backup", "--include-secrets"])
    assert result.exit_code == 0, result.output
    assert "--include-secrets" not in result.output
    archive = next((home / "backups").glob("homer-*.tar.gz"))
    with tarfile.open(archive) as tar:
        assert ".env" in tar.getnames()


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


def test_eval_requires_the_smoke_flag(home: Path) -> None:
    result = runner.invoke(app, ["eval"])
    assert result.exit_code == 2
    assert "--smoke" in result.output


def test_eval_smoke_wraps_homer_eval(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], check: bool) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=3)

    monkeypatch.setattr(cli, "find_executable", lambda name: f"/fake/bin/{name}")
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    result = runner.invoke(app, ["eval", "--smoke"])
    assert result.exit_code == 3
    assert calls == [["/fake/bin/homer-eval", "--runs", "3"]]


@pytest.fixture
def installed(home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    user_home = tmp_path / "user"
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setattr(cli, "HOME", home)
    monkeypatch.setattr(platform.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform.subprocess, "run", lambda command, **_: None)
    agents = user_home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    server = agents / "dev.homer.server.plist"
    ollama = agents / "dev.homer.ollama.plist"
    for path in (server, ollama):
        path.write_text("<plist/>")
    (home / "venv" / "bin").mkdir(parents=True)
    (home / "venv.prev").mkdir()
    return {"server": server, "ollama": ollama}


def test_uninstall_keeps_the_data_by_default(home: Path, installed: dict[str, Path]) -> None:
    result = runner.invoke(app, ["uninstall"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "Your data stays" in result.output
    assert "ollama rm" in result.output
    assert not installed["server"].exists() and not installed["ollama"].exists()
    assert not (home / "venv").exists() and not (home / "venv.prev").exists()
    assert (home / "data" / "homer.db").exists()


def test_uninstall_purge_deletes_the_home(home: Path, installed: dict[str, Path]) -> None:
    result = runner.invoke(app, ["uninstall", "--purge", "--yes"])
    assert result.exit_code == 0, result.output
    assert not home.exists()
    assert not installed["server"].exists()


def test_uninstall_asks_first(home: Path, installed: dict[str, Path]) -> None:
    result = runner.invoke(app, ["uninstall", "--purge"], input="n\n")
    assert result.exit_code == 1
    assert "Nothing removed" in result.output
    assert home.exists() and installed["server"].exists()


def test_uninstall_with_nothing_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli, "HOME", tmp_path / "missing")
    result = runner.invoke(app, ["uninstall"])
    assert result.exit_code == 0
    assert "Nothing to remove" in result.output


def test_restart_without_a_service_says_how_to_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(app, ["restart"])
    assert result.exit_code == 1
    assert "homer serve" in result.output


def test_uninstall_reads_the_manifest_before_deleting_the_venv(
    home: Path, installed: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    manifest = cli.load_manifest
    monkeypatch.setattr(cli, "load_manifest", lambda: events.append("manifest") or manifest())
    monkeypatch.setattr(cli.shutil, "rmtree", lambda path, **_: events.append("delete"))
    assert runner.invoke(app, ["uninstall", "--yes"]).exit_code == 0
    assert events[0] == "manifest" and "delete" in events
