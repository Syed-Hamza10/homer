"""step 4 caches, briefs and follow-ups

Revision ID: c4d8e1f6a2b7
Revises: a3c1e9b2d4f5
Create Date: 2026-10-20 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "c4d8e1f6a2b7"
down_revision: str | None = "a3c1e9b2d4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("thread_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("sender", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("subject", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("snippet", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("received_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("labels_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("unread", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "message_id", name="uq_email_cache_user_message"),
    )
    with op.batch_alter_table("email_cache", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_email_cache_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_email_cache_message_id"), ["message_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_email_cache_thread_id"), ["thread_id"], unique=False)

    op.create_table(
        "calendar_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("start_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("end_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("location", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("attendees_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("updated_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "event_id", name="uq_calendar_cache_user_event"),
    )
    with op.batch_alter_table("calendar_cache", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_calendar_cache_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_calendar_cache_event_id"), ["event_id"], unique=False)

    op.create_table(
        "daily_briefs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("day", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("daily_briefs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_daily_briefs_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_daily_briefs_kind"), ["kind"], unique=False)
        batch_op.create_index(batch_op.f("ix_daily_briefs_day"), ["day"], unique=False)

    op.create_table(
        "follow_ups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("subject", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("contact", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("due_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("draft_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("updated_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("follow_ups", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_follow_ups_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_follow_ups_thread_id"), ["thread_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_follow_ups_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("follow_ups", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_follow_ups_status"))
        batch_op.drop_index(batch_op.f("ix_follow_ups_thread_id"))
        batch_op.drop_index(batch_op.f("ix_follow_ups_user_id"))
    op.drop_table("follow_ups")

    with op.batch_alter_table("daily_briefs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_daily_briefs_day"))
        batch_op.drop_index(batch_op.f("ix_daily_briefs_kind"))
        batch_op.drop_index(batch_op.f("ix_daily_briefs_user_id"))
    op.drop_table("daily_briefs")

    with op.batch_alter_table("calendar_cache", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_calendar_cache_event_id"))
        batch_op.drop_index(batch_op.f("ix_calendar_cache_user_id"))
    op.drop_table("calendar_cache")

    with op.batch_alter_table("email_cache", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_email_cache_thread_id"))
        batch_op.drop_index(batch_op.f("ix_email_cache_message_id"))
        batch_op.drop_index(batch_op.f("ix_email_cache_user_id"))
    op.drop_table("email_cache")
