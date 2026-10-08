"""Outgoing mail: a queue of messages the worker sends.

Revision ID: 0028_mail_outbox
Revises: 0027_quote_document
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_mail_outbox"
down_revision: str | None = "0027_quote_document"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mail_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("subject_kind", sa.String(length=40), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("reply_to", sa.String(length=320), nullable=True),
        sa.Column("sender_name", sa.String(length=64), nullable=True),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=True),
        sa.Column("html_body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure", sa.String(length=40), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'sent', 'failed')",
            name=op.f("ck_mail_outbox_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mail_outbox")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_mail_outbox_dedupe_key")),
    )
    op.create_index("ix_mail_outbox_due", "mail_outbox", ["status", "next_attempt_at"])
    op.create_index(
        "ix_mail_outbox_subject",
        "mail_outbox",
        ["subject_kind", "subject_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_mail_outbox_subject", table_name="mail_outbox")
    op.drop_index("ix_mail_outbox_due", table_name="mail_outbox")
    op.drop_table("mail_outbox")
