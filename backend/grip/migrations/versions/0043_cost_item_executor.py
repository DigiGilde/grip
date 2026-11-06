"""A cost item can be kept by another organisation (ADR 0052, 0053).

At the organisation that asks, a cost item with an executor is a reference:
the request to the executor is numbered and has a status, and description
and amount are empty once the executor applied it. At the executor, the
cost item records who asked for it and the URI of their reference.

Revision ID: 0043_cost_item_executor
Revises: 0042_stream_changes_index
Create Date: 2026-10-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_cost_item_executor"
down_revision: str | None = "0042_stream_changes_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "cost_item", "description", existing_type=sa.String(length=500), nullable=True
    )
    op.alter_column(
        "cost_item",
        "budgeted_cents",
        existing_type=sa.BigInteger(),
        existing_server_default="0",
        nullable=True,
    )
    op.add_column(
        "cost_item", sa.Column("executor_organisation_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "cost_item",
        sa.Column("request_sequence", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "cost_item", sa.Column("request_status", sa.String(length=20), nullable=True)
    )
    op.add_column("cost_item", sa.Column("request_period", sa.Date(), nullable=True))
    op.add_column(
        "cost_item",
        sa.Column(
            "executor_has_item",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "cost_item", sa.Column("requester_organisation_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "cost_item", sa.Column("reference_uri", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "cost_item",
        sa.Column(
            "reference_sequence", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.create_index(
        op.f("ix_cost_item_executor_organisation_id"),
        "cost_item",
        ["executor_organisation_id"],
    )
    op.create_index(
        op.f("ix_cost_item_requester_organisation_id"),
        "cost_item",
        ["requester_organisation_id"],
    )
    op.create_unique_constraint(
        op.f("uq_cost_item_reference_uri"), "cost_item", ["reference_uri"]
    )
    op.create_foreign_key(
        op.f("fk_cost_item_executor_organisation_id_organisation"),
        "cost_item",
        "organisation",
        ["executor_organisation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_cost_item_requester_organisation_id_organisation"),
        "cost_item",
        "organisation",
        ["requester_organisation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        op.f("ck_cost_item_own_item_has_content"),
        "cost_item",
        "executor_organisation_id IS NOT NULL "
        "OR (description IS NOT NULL AND budgeted_cents IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_cost_item_reference_not_requested"),
        "cost_item",
        "executor_organisation_id IS NULL OR reference_uri IS NULL",
    )
    op.create_check_constraint(
        op.f("ck_cost_item_request_status_valid"),
        "cost_item",
        "request_status IS NULL OR request_status IN "
        "('waiting', 'applied', 'refused', 'undelivered')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM cost_item WHERE executor_organisation_id IS NOT NULL")
    op.drop_constraint(
        op.f("ck_cost_item_request_status_valid"), "cost_item", type_="check"
    )
    op.drop_constraint(
        op.f("ck_cost_item_reference_not_requested"), "cost_item", type_="check"
    )
    op.drop_constraint(
        op.f("ck_cost_item_own_item_has_content"), "cost_item", type_="check"
    )
    op.drop_constraint(
        op.f("fk_cost_item_requester_organisation_id_organisation"),
        "cost_item",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_cost_item_executor_organisation_id_organisation"),
        "cost_item",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("uq_cost_item_reference_uri"), "cost_item", type_="unique")
    op.drop_index(
        op.f("ix_cost_item_requester_organisation_id"), table_name="cost_item"
    )
    op.drop_index(op.f("ix_cost_item_executor_organisation_id"), table_name="cost_item")
    op.drop_column("cost_item", "reference_sequence")
    op.drop_column("cost_item", "reference_uri")
    op.drop_column("cost_item", "requester_organisation_id")
    op.drop_column("cost_item", "executor_has_item")
    op.drop_column("cost_item", "request_period")
    op.drop_column("cost_item", "request_status")
    op.drop_column("cost_item", "request_sequence")
    op.drop_column("cost_item", "executor_organisation_id")
    op.alter_column(
        "cost_item",
        "budgeted_cents",
        existing_type=sa.BigInteger(),
        existing_server_default="0",
        nullable=False,
    )
    op.alter_column(
        "cost_item", "description", existing_type=sa.String(length=500), nullable=False
    )
