"""Every record people edit in a form counts its changes.

The column of 0038 and 0039 for the remaining records. Some of these are
also written by the system (a login, a sync, the task engine); for those the
count goes up only when a person's edit says so (grip.services.stale.touch).

Revision ID: 0040_record_version_everywhere
Revises: 0039_record_version_vacancy_role
Create Date: 2026-10-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_record_version_everywhere"
down_revision: str | None = "0039_record_version_vacancy_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "person",
    "task",
    "organisation",
    "peer",
    "instance_setting",
    "outgoing_invoice",
    "billing_terms",
    "form_template",
    "function_family",
    "function_group",
    "billability_target",
    "vacancy_text_template",
    "vacancy_text_shared_section",
)


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "version")
