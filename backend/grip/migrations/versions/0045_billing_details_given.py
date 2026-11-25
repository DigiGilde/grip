"""Billing details the client gives: when, and the client's own copy.

Revision ID: 0045_billing_details_given
Revises: 0044_peer_is_example
Create Date: 2026-11-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045_billing_details_given"
down_revision: str | None = "0044_peer_is_example"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.add_column(
        "billing_terms",
        sa.Column("details_given_at", sa.DateTime(timezone=True), nullable=True),
    )

    t = "client_billing_details"
    op.create_table(
        t,
        sa.Column("assignment_id", UUID, nullable=False),
        sa.Column("details", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("given_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("given_by_id", UUID, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignment.id"],
            name=op.f(f"fk_{t}_assignment_id_assignment"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["given_by_id"],
            ["person.id"],
            name=op.f(f"fk_{t}_given_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("assignment_id", name=op.f(f"pk_{t}")),
    )


def downgrade() -> None:
    op.drop_table("client_billing_details")
    op.drop_column("billing_terms", "details_given_at")
