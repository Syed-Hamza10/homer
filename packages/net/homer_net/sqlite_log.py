import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from homer_net.client import OutboundCall

INSERT = (
    "INSERT INTO outbound_log (ts, method, host, path, status, duration_ms) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)


class SqliteLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __call__(self, call: OutboundCall) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                INSERT,
                (
                    datetime.now(UTC).isoformat(),
                    call.method,
                    call.host,
                    call.path,
                    call.status,
                    call.duration_ms,
                ),
            )
