"""Outgoing invoices: the recorded fact that an invoice was sent.

Revision ID: 0015_outgoing_invoice
Revises: 0014_vacancy_hire
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_outgoing_invoice"
down_revision: str | None = "0014_vacancy_hire"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outgoing_invoice",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("invoice_number", sa.String(length=100), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "source", sa.String(length=20), server_default="manual", nullable=False
        ),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_by_id", sa.UUID(), nullable=True),
        sa.Column("withdrawn_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(invoice_number) <> ''",
            name=op.f("ck_outgoing_invoice_number_not_empty"),
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'financial_system')",
            name=op.f("ck_outgoing_invoice_source_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignment.id"],
            name=op.f("fk_outgoing_invoice_assignment_id_assignment"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_id"],
            ["person.id"],
            name=op.f("fk_outgoing_invoice_recorded_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["withdrawn_by_id"],
            ["person.id"],
            name=op.f("fk_outgoing_invoice_withdrawn_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outgoing_invoice")),
    )
    op.create_index(
        op.f("ix_outgoing_invoice_assignment_id"),
        "outgoing_invoice",
        ["assignment_id"],
        unique=False,
    )
    op.create_table(
        "outgoing_invoice_delivery",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("outgoing_invoice_id", sa.UUID(), nullable=False),
        sa.Column("billing_export_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["billing_export_id"],
            ["billing_export.id"],
            name=op.f("fk_outgoing_invoice_delivery_billing_export_id_billing_export"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["outgoing_invoice_id"],
            ["outgoing_invoice.id"],
            name=op.f(
                "fk_outgoing_invoice_delivery_outgoing_invoice_id_outgoing_invoice"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outgoing_invoice_delivery")),
        sa.UniqueConstraint(
            "billing_export_id",
            name=op.f("uq_outgoing_invoice_delivery_billing_export_id"),
        ),
    )
    op.create_index(
        op.f("ix_outgoing_invoice_delivery_outgoing_invoice_id"),
        "outgoing_invoice_delivery",
        ["outgoing_invoice_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_outgoing_invoice_delivery_outgoing_invoice_id"),
        table_name="outgoing_invoice_delivery",
    )
    op.drop_table("outgoing_invoice_delivery")
    op.drop_index(
        op.f("ix_outgoing_invoice_assignment_id"), table_name="outgoing_invoice"
    )
    op.drop_table("outgoing_invoice")
