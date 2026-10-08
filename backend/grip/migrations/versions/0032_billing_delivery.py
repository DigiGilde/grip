"""Billing per period: the terms of an assignment and deliveries.

Revision ID: 0032_billing_delivery
Revises: 0031_passkeys
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_billing_delivery"
down_revision: str | None = "0031_passkeys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.text("now()")


def upgrade() -> None:
    t = "billing_terms"
    op.create_table(
        t,
        sa.Column("assignment_id", UUID, nullable=False),
        sa.Column("rhythm", sa.String(10), nullable=False),
        sa.Column("details", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "names_on_specification",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("updated_by_id", UUID, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.CheckConstraint(
            "rhythm IN ('month', 'quarter')", name=op.f(f"ck_{t}_rhythm_valid")
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignment.id"],
            name=op.f(f"fk_{t}_assignment_id_assignment"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["person.id"],
            name=op.f(f"fk_{t}_updated_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("assignment_id", name=op.f(f"pk_{t}")),
    )

    t = "billing_delivery"
    op.create_table(
        t,
        sa.Column(
            "id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("assignment_id", UUID, nullable=False),
        sa.Column("period_key", sa.String(10), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("rhythm", sa.String(10), nullable=False),
        sa.Column("reference", sa.String(80), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("via", sa.String(10), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("document_ref", sa.String(500), nullable=True),
        sa.Column("document_sha256", sa.String(64), nullable=True),
        sa.Column("delivered_by_id", UUID, nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.CheckConstraint("via IN ('mail', 'self')", name=op.f(f"ck_{t}_via_valid")),
        sa.CheckConstraint(
            "period_end >= period_start", name=op.f(f"ck_{t}_period_valid")
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignment.id"],
            name=op.f(f"fk_{t}_assignment_id_assignment"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["delivered_by_id"],
            ["person.id"],
            name=op.f(f"fk_{t}_delivered_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
    )
    op.create_index(op.f(f"ix_{t}_assignment_id"), t, ["assignment_id"])

    # A record of billing data belongs to the delivery it went with. Records
    # from before deliveries per period existed keep an empty reference.
    op.add_column("billing_export", sa.Column("delivery_id", UUID, nullable=True))
    op.create_foreign_key(
        op.f("fk_billing_export_delivery_id_billing_delivery"),
        "billing_export",
        "billing_delivery",
        ["delivery_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_billing_export_delivery_id"), "billing_export", ["delivery_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_billing_export_delivery_id"), "billing_export")
    op.drop_constraint(
        op.f("fk_billing_export_delivery_id_billing_delivery"),
        "billing_export",
        type_="foreignkey",
    )
    op.drop_column("billing_export", "delivery_id")
    op.drop_index(op.f("ix_billing_delivery_assignment_id"), "billing_delivery")
    op.drop_table("billing_delivery")
    op.drop_table("billing_terms")
