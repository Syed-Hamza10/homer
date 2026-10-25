import sqlite3
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

BACKUP_GLOB = "achilles-*.tar.gz"
SECRETS = ("credentials", ".env")


def snapshot_database(source: Path, target: Path) -> None:
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


def prune_backups(backups: Path, keep: int) -> list[Path]:
    files = sorted(backups.glob(BACKUP_GLOB))
    removed = files[:-keep] if keep > 0 else files
    for path in removed:
        path.unlink()
    return removed


def create_backup(home: Path, keep: int = 14, include_secrets: bool = False) -> Path:
    backups = home / "backups"
    backups.mkdir(mode=0o700, parents=True, exist_ok=True)
    backups.chmod(0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    target = backups / f"achilles-{stamp}.tar.gz"
    members: list[tuple[Path, str]] = []
    with tempfile.TemporaryDirectory() as temporary:
        database = home / "data" / "achilles.db"
        if database.exists():
            snapshot = Path(temporary) / "achilles.db"
            snapshot_database(database, snapshot)
            members.append((snapshot, "data/achilles.db"))
        for name in SECRETS if include_secrets else ():
            path = home / name
            if path.exists():
                members.append((path, name))
        with tarfile.open(target, "w:gz") as archive:
            for path, arcname in members:
                archive.add(path, arcname=arcname)
    target.chmod(0o600)
    prune_backups(backups, keep)
    return target
