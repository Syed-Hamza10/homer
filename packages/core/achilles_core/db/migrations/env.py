from alembic import context
from sqlalchemy import Connection
from sqlmodel import SQLModel

import achilles_core.db.models  # noqa: F401
from achilles_core.config import Settings
from achilles_core.db.session import make_engine

target_metadata = SQLModel.metadata


def run_with(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is None:
    with make_engine(Settings().achilles_home).connect() as owned:
        run_with(owned)
else:
    run_with(connection)
