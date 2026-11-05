"""remembered facts and the resolved intents of each assistant turn

Revision ID: f6a3b8c0d2e4
Revises: d5e2f7a9b1c3
Create Date: 2026-11-06 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "f6a3b8c0d2e4"
down_revision: str | None = "d5e2f7a9b1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("facts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_facts_user_id"), ["user_id"], unique=False)
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("context_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_column("context_json")
    with op.batch_alter_table("facts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_facts_user_id"))
    op.drop_table("facts")
