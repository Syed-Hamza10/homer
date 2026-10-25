import sqlite3
import tarfile
from pathlib import Path

from achilles_core.services.backup import create_backup, prune_backups


def make_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / "data").mkdir(parents=True)
    (home / "credentials").mkdir()
    with sqlite3.connect(home / "data" / "achilles.db") as connection:
        connection.execute("create table notes (id integer primary key, body text)")
        connection.execute("insert into notes (body) values ('hello')")
        connection.commit()
    (home / "credentials" / "google_token.json").write_text("{}")
    (home / ".env").write_text("ACHILLES_PASSPHRASE=secret\n")
    return home


def test_backup_leaves_secrets_out_by_default(tmp_path: Path) -> None:
    home = make_home(tmp_path)
    path = create_backup(home)

    assert path.exists()
    assert path.stat().st_mode & 0o777 == 0o600
    with tarfile.open(path) as archive:
        names = set(archive.getnames())
        assert "data/achilles.db" in names
        assert not names & {"credentials", "credentials/google_token.json", ".env"}
        extracted = archive.extractfile("data/achilles.db")
        assert extracted is not None


def test_backup_includes_secrets_on_request(tmp_path: Path) -> None:
    home = make_home(tmp_path)
    path = create_backup(home, include_secrets=True)

    assert path.stat().st_mode & 0o777 == 0o600
    with tarfile.open(path) as archive:
        names = set(archive.getnames())
        assert {"data/achilles.db", "credentials/google_token.json", ".env"} <= names


def test_prune_keeps_the_newest_backups(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    for name in ("achilles-001.tar.gz", "achilles-002.tar.gz", "achilles-003.tar.gz"):
        (backups / name).write_text("x")

    removed = prune_backups(backups, 2)

    assert [path.name for path in removed] == ["achilles-001.tar.gz"]
    assert sorted(path.name for path in backups.iterdir()) == [
        "achilles-002.tar.gz",
        "achilles-003.tar.gz",
    ]
