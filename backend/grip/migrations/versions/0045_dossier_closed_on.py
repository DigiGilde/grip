"""Assignment: the day its dossier closed (ADR 0057).

Revision ID: 0045_dossier_closed_on
Revises: 0044_peer_is_example
Create Date: 2026-11-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_dossier_closed_on"
down_revision: str | None = "0044_peer_is_example"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assignment", sa.Column("dossier_closed_on", sa.Date(), nullable=True)
    )
    op.create_index(
        "ix_assignment_dossier_closed_on",
        "assignment",
        ["dossier_closed_on"],
        postgresql_where=sa.text("dossier_closed_on IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_assignment_dossier_closed_on", table_name="assignment")
    op.drop_column("assignment", "dossier_closed_on")
