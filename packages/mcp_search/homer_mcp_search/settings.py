import os
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path

from homer_net import OutboundCall, SqliteLog
from homer_net.client import no_log

VERSION = version("homer-mcp-search")
FALSE_VALUES = {"0", "false", "no", "off"}

LogFn = Callable[[OutboundCall], None]


def web_search_enabled() -> bool:
    return os.environ.get("WEB_SEARCH", "true").strip().lower() not in FALSE_VALUES


def build_log() -> LogFn:
    home = Path(os.environ.get("HOMER_HOME", "~/.homer")).expanduser()
    db = home / "data" / "homer.db"
    return SqliteLog(db) if db.exists() else no_log
