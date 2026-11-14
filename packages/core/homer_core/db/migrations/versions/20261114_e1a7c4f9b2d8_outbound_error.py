"""outbound_log records why a call failed

Revision ID: e1a7c4f9b2d8
Revises: c9e5f3a8b4d6
Create Date: 2026-11-14 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "e1a7c4f9b2d8"
down_revision: str | None = "c9e5f3a8b4d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("outbound_log", schema=None) as batch_op:
        batch_op.add_column(sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("outbound_log", schema=None) as batch_op:
        batch_op.drop_column("error")
