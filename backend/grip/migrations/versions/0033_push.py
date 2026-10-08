"""Notifications on a person's device: subscriptions, preference, queue.

Revision ID: 0033_push
Revises: 0032_billing_delivery
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_push"
down_revision: str | None = "0032_billing_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.text("now()")
NEW_ID = sa.text("gen_random_uuid()")


def _person(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["person_id"],
        ["person.id"],
        name=op.f(f"fk_{table}_person_id_person"),
        ondelete="CASCADE",
    )


def _ts(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=None if nullable else NOW,
        nullable=nullable,
    )


def upgrade() -> None:
    t = "push_subscription"
    op.create_table(
        t,
        sa.Column("id", UUID, server_default=NEW_ID, nullable=False),
        sa.Column("person_id", UUID, nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(100), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        _ts("created_at"),
        _ts("last_success_at", nullable=True),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        _person(t),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint("endpoint", name=op.f(f"uq_{t}_endpoint")),
    )
    op.create_index(op.f(f"ix_{t}_person_id"), t, ["person_id"])

    t = "notification_preference"
    op.create_table(
        t,
        sa.Column("person_id", UUID, nullable=False),
        sa.Column("push", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("mail_summary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("kinds", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("quiet_from", sa.Time(), nullable=True),
        sa.Column("quiet_until", sa.Time(), nullable=True),
        sa.Column(
            "weekends_quiet", sa.Boolean(), server_default="true", nullable=False
        ),
        _ts("updated_at"),
        _person(t),
        sa.PrimaryKeyConstraint("person_id", name=op.f(f"pk_{t}")),
    )

    t = "push_outbox"
    op.create_table(
        t,
        sa.Column("id", UUID, server_default=NEW_ID, nullable=False),
        sa.Column("person_id", UUID, nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("badge", sa.Integer(), nullable=True),
        sa.Column("path", sa.String(300), server_default="/", nullable=False),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(10), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(300), nullable=True),
        _ts("created_at"),
        _ts("sent_at", nullable=True),
        _person(t),
        sa.CheckConstraint(
            "status IN ('queued', 'sent', 'failed', 'skipped')",
            name=op.f(f"ck_{t}_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint("dedupe_key", name=op.f(f"uq_{t}_dedupe_key")),
    )
    op.create_index("ix_push_outbox_due", t, ["status", "next_attempt_at"])
    op.create_index("ix_push_outbox_person", t, ["person_id", "created_at"])

    t = "push_notice"
    op.create_table(
        t,
        sa.Column("id", UUID, server_default=NEW_ID, nullable=False),
        sa.Column("person_id", UUID, nullable=False),
        sa.Column("task_id", UUID, nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("notified", sa.Boolean(), server_default="true", nullable=False),
        _ts("created_at"),
        _person(t),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["task.id"],
            name=op.f(f"fk_{t}_task_id_task"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint("person_id", "task_id", "kind", name="uq_push_notice_once"),
    )
    op.create_index(op.f(f"ix_{t}_person_id"), t, ["person_id"])

    t = "push_cursor"
    op.create_table(
        t,
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("seq", sa.BigInteger(), server_default="0", nullable=False),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("name", name=op.f(f"pk_{t}")),
    )


def downgrade() -> None:
    for table in (
        "push_cursor",
        "push_notice",
        "push_outbox",
        "notification_preference",
        "push_subscription",
    ):
        op.drop_table(table)
