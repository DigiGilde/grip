"""A vacancy and a role in the catalogue count their own changes.

The same column as in 0038_record_version, for two more records people edit
in forms: a save on top of someone else's change is refused
(grip.services.stale).

Revision ID: 0039_record_version_vacancy_role
Revises: 0038_record_version
Create Date: 2026-10-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_record_version_vacancy_role"
down_revision: str | None = "0038_record_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("vacancy", "catalogue_role")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "version")
