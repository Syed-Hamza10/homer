"""reminders and approvals

Revision ID: a3c1e9b2d4f5
Revises: 7f7495d0ce9d
Create Date: 2026-10-16 18:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "a3c1e9b2d4f5"
down_revision: str | None = "7f7495d0ce9d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("due_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("reminders", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_reminders_user_id"), ["user_id"], unique=False)

    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("server", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("action", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payload_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payload_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("preview", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("decided_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
        sa.Column("result_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("channel", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_approvals_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_approvals_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_approvals_status"))
        batch_op.drop_index(batch_op.f("ix_approvals_user_id"))
    op.drop_table("approvals")
    with op.batch_alter_table("reminders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_reminders_user_id"))
    op.drop_table("reminders")
