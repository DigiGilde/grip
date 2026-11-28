"""Messages to another instance that do not arrive, as the domain keeps them.

One row per peer while messages to it do not arrive (ADR 0061). The outbox
reports after its next round, so the table starts empty.

Revision ID: 0049_delivery_trouble
Revises: 0048_outbox_retry_window
Create Date: 2026-11-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049_delivery_trouble"
down_revision: str | None = "0048_outbox_retry_window"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REASONS = (
    "no_connection",
    "timeout",
    "unknown_sender",
    "not_found",
    "receiver_error",
    "configuration",
    "invalid",
    "conflict",
    "gone",
    "other",
)


def upgrade() -> None:
    listed = ", ".join(f"'{reason}'" for reason in REASONS)
    op.create_table(
        "delivery_trouble",
        sa.Column("peer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("peer_name", sa.String(length=200), nullable=False),
        sa.Column("since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("final", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("retry_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"reason IN ({listed})", name=op.f("ck_delivery_trouble_reason_valid")
        ),
        sa.PrimaryKeyConstraint("peer_id", name=op.f("pk_delivery_trouble")),
    )


def downgrade() -> None:
    op.drop_table("delivery_trouble")
