import sqlite3
from pathlib import Path

from homer_net import OutboundCall, SqliteLog

SCHEMA = (
    "CREATE TABLE outbound_log (id INTEGER PRIMARY KEY, ts TEXT, method TEXT, host TEXT, "
    "path TEXT, status INTEGER, duration_ms INTEGER)"
)


def test_inserts_row(tmp_path: Path) -> None:
    db = tmp_path / "homer.db"
    sqlite3.connect(db).execute(SCHEMA)
    SqliteLog(db)(OutboundCall("GET", "example.test", "/x", 200, 12))
    rows = (
        sqlite3.connect(db)
        .execute("SELECT method, host, path, status, duration_ms FROM outbound_log")
        .fetchall()
    )
    assert rows == [("GET", "example.test", "/x", 200, 12)]
