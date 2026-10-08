"""A correction on a delivered billing period is a stored row.

Revision ID: 0036_billing_correction
Revises: 0035_task_situation
Create Date: 2026-10-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_billing_correction"
down_revision: str | None = "0035_task_situation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_correction",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "assignment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assignment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("period_key", sa.String(length=10), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "months",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "causes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "follows_delivery_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("billing_delivery.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("arose_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "arose_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("person.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "delivered_delivery_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("billing_delivery.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_billing_correction_assignment_id", "billing_correction", ["assignment_id"]
    )
    op.create_index(
        "uq_billing_correction_open",
        "billing_correction",
        ["assignment_id", "period_key"],
        unique=True,
        postgresql_where=sa.text("delivered_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_billing_correction_open", table_name="billing_correction")
    op.drop_index(
        "ix_billing_correction_assignment_id", table_name="billing_correction"
    )
    op.drop_table("billing_correction")
