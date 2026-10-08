"""The feed of updates: when each person last looked.

Revision ID: 0034_update_feed
Revises: 0033_push
Create Date: 2026-10-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_update_feed"
down_revision: str | None = "0033_push"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "update_feed_marker",
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("seen_seq", sa.BigInteger(), nullable=False),
        sa.Column(
            "seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_update_feed_marker_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("person_id", name=op.f("pk_update_feed_marker")),
    )


def downgrade() -> None:
    op.drop_table("update_feed_marker")
