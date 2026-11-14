"""facts carry the person they are about and when they last changed

Revision ID: b8d4e2f7a3c5
Revises: a7c3d9e1f2b4
Create Date: 2026-11-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "b8d4e2f7a3c5"
down_revision: str | None = "a7c3d9e1f2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("facts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("person", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(
            sa.Column("updated_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True)
        )
    op.execute("UPDATE facts SET updated_at = created_at")
    with op.batch_alter_table("facts", schema=None) as batch_op:
        batch_op.alter_column(
            "updated_at", existing_type=sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table("facts", schema=None) as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("person")
