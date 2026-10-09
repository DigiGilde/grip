"""An index on the changes in the event stream.

Reads of data are written to the same stream as changes, and there are many
more of them. Three things ask for the newest changes and had to step over
every read on the way:

- the mark that says whether anything changed, asked on every request
  (``SELECT seq FROM stream_event WHERE type <> 'data.read' ORDER BY seq
  DESC LIMIT 1``);
- the page Activiteit with changes only (the same, with ``LIMIT 200``);
- the feed "Wat is er gebeurd" (``WHERE type IN (...) AND type <>
  'data.read' ORDER BY seq DESC LIMIT 801``), which before this sorted every
  change ever made.

The index holds only the changes, in order, so each of these reads as many
rows as it returns.

Revision ID: 0042_stream_changes_index
Revises: 0041_text_facts
Create Date: 2026-10-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_stream_changes_index"
down_revision: str | None = "0041_text_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_stream_event_changes",
        "stream_event",
        ["seq"],
        postgresql_where=sa.text("type <> 'data.read'"),
    )


def downgrade() -> None:
    op.drop_index("ix_stream_event_changes", table_name="stream_event")
