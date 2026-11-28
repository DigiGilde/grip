"""Federation inbox: the path parameters of a received message.

Revision ID: 0047_inbox_path_parameters
Revises: 0046_dossier_closed_on
Create Date: 2026-11-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047_inbox_path_parameters"
down_revision: str | None = "0046_dossier_closed_on"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "federation_inbox",
        sa.Column(
            "path_parameters",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("federation_inbox", "path_parameters")
