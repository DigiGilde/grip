"""Grist import: where a Grist row ended up in grip.

Revision ID: 0008_grist_import_ref
Revises: 0007_cost_item_creator
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_grist_import_ref"
down_revision: str | None = "0007_cost_item_creator"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "grist_import_ref",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("document_key", sa.String(length=100), nullable=False),
        sa.Column("grist_table", sa.String(length=100), nullable=False),
        sa.Column("grist_row_id", sa.Integer(), nullable=False),
        sa.Column("entity", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grist_import_ref")),
        sa.UniqueConstraint(
            "document_key",
            "grist_table",
            "grist_row_id",
            "entity",
            name="uq_grist_import_ref_source",
        ),
    )
    op.create_index(
        op.f("ix_grist_import_ref_entity_id"),
        "grist_import_ref",
        ["entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_grist_import_ref_entity_id"), table_name="grist_import_ref")
    op.drop_table("grist_import_ref")
