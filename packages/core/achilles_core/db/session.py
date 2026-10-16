from collections.abc import Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import Request
from sqlalchemy import Engine
from sqlmodel import Session, create_engine

MIGRATIONS = Path(__file__).parent / "migrations"


def make_engine(home: Path) -> Engine:
    return create_engine(
        f"sqlite:///{home / 'data' / 'achilles.db'}", connect_args={"check_same_thread": False}
    )


def run_migrations(engine: Engine) -> None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session
