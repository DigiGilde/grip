"""Federation outbox: why a message did not arrive, since when, until when.

A message that does not arrive is tried again for a number of days from its
first failure (ADR 0061). A message that was final before this revision gets
the reason its last answer gives and the moment it was given up, and starts
set aside: what became of it was settled before, so an upgrade opens no task
for it.

Revision ID: 0048_outbox_retry_window
Revises: 0047_inbox_path_parameters
Create Date: 2026-11-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_outbox_retry_window"
down_revision: str | None = "0047_inbox_path_parameters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FAILURES = (
    "no_connection",
    "timeout",
    "unknown_sender",
    "not_found",
    "receiver_error",
    "configuration",
    "invalid",
    "conflict",
    "gone",
    "other",
)


def upgrade() -> None:
    op.add_column(
        "federation_outbox", sa.Column("failure", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "federation_outbox",
        sa.Column("failing_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "federation_outbox",
        sa.Column("retry_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "federation_outbox",
        sa.Column("set_aside_at", sa.DateTime(timezone=True), nullable=True),
    )
    listed = ", ".join(f"'{failure}'" for failure in FAILURES)
    op.create_check_constraint(
        op.f("ck_federation_outbox_failure_valid"),
        "federation_outbox",
        f"failure IS NULL OR failure IN ({listed})",
    )
    op.execute(
        """
        UPDATE federation_outbox SET
            failing_since = next_attempt_at,
            set_aside_at = now(),
            failure = CASE
                WHEN last_error LIKE 'configuration:%' THEN 'configuration'
                WHEN last_status_code IN (401, 403) AND last_error LIKE 'HTTP %'
                    THEN 'unknown_sender'
                WHEN last_status_code = 404 AND last_error LIKE 'HTTP %'
                    THEN 'not_found'
                WHEN last_status_code IN (400, 422) AND last_error LIKE 'HTTP %'
                    THEN 'invalid'
                WHEN last_status_code = 409 AND last_error LIKE 'HTTP %'
                    THEN 'conflict'
                WHEN last_status_code = 410 AND last_error LIKE 'HTTP %'
                    THEN 'gone'
                WHEN last_status_code BETWEEN 500 AND 599
                    AND last_error LIKE 'HTTP %' THEN 'receiver_error'
                WHEN last_error LIKE 'HTTP %' THEN 'other'
                WHEN last_error LIKE '%Timeout:%' THEN 'timeout'
                ELSE 'no_connection'
            END
        WHERE status IN ('rejected', 'dead')
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_federation_outbox_failure_valid"), "federation_outbox", type_="check"
    )
    op.drop_column("federation_outbox", "set_aside_at")
    op.drop_column("federation_outbox", "retry_until")
    op.drop_column("federation_outbox", "failing_since")
    op.drop_column("federation_outbox", "failure")
