"""Cost item: who added it.

Until a budget line covers a cost item nobody manages it through an
assignment; the creator does.

Revision ID: 0007_cost_item_creator
Revises: 0006_peer_financial
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_cost_item_creator"
down_revision: str | None = "0006_peer_financial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cost_item", sa.Column("created_by_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_cost_item_created_by_id"), "cost_item", ["created_by_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_cost_item_created_by_id_person"),
        "cost_item",
        "person",
        ["created_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_cost_item_created_by_id_person"), "cost_item", type_="foreignkey"
    )
    op.drop_index(op.f("ix_cost_item_created_by_id"), table_name="cost_item")
    op.drop_column("cost_item", "created_by_id")
