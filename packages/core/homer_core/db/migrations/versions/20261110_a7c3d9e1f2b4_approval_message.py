"""the assistant message that shows each approval

Revision ID: a7c3d9e1f2b4
Revises: f6a3b8c0d2e4
Create Date: 2026-11-10 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3d9e1f2b4"
down_revision: str | None = "f6a3b8c0d2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BACKFILL = """
UPDATE approvals SET message_id = (
    SELECT MIN(messages.id) FROM messages
    WHERE messages.conversation_id = approvals.conversation_id
      AND messages.role = 'assistant'
      AND messages.created_at >= approvals.created_at
)
WHERE conversation_id IS NOT NULL
"""


def upgrade() -> None:
    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.add_column(sa.Column("message_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_approvals_message_id"), ["message_id"], unique=False)
    op.execute(BACKFILL)


def downgrade() -> None:
    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_approvals_message_id"))
        batch_op.drop_column("message_id")
