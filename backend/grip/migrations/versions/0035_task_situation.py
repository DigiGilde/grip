"""A task remembers the situation it is told in.

Revision ID: 0035_task_situation
Revises: 0034_update_feed
Create Date: 2026-10-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_task_situation"
down_revision: str | None = "0034_update_feed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("task", sa.Column("situation", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("task", "situation")
