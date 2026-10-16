import os
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path

from achilles_net import OutboundCall, SqliteLog
from achilles_net.client import no_log

VERSION = version("achilles-mcp-search")
FALSE_VALUES = {"0", "false", "no", "off"}

LogFn = Callable[[OutboundCall], None]


def web_search_enabled() -> bool:
    return os.environ.get("WEB_SEARCH", "true").strip().lower() not in FALSE_VALUES


def build_log() -> LogFn:
    home = Path(os.environ.get("ACHILLES_HOME", "~/.achilles")).expanduser()
    db = home / "data" / "achilles.db"
    return SqliteLog(db) if db.exists() else no_log
