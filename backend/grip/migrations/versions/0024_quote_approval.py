"""Internal approval of quotes, the right to give it, and instance settings.

Revision ID: 0024_quote_approval
Revises: 0023_tasks
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_quote_approval"
down_revision: str | None = "0023_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept literal: a migration must not change when the application code does.
_ROLE_ID = "offertegoedkeurder"
_ROLE_LABEL = "Interne goedkeurder van offertes"
_ROLE_DESCRIPTION = (
    "Keurt een gemaakte offerte intern goed of stuurt haar terug, voordat ze "
    "aan de opdrachtgever wordt aangeboden."
)


def upgrade() -> None:
    op.create_table(
        "instance_setting",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["person.id"],
            name=op.f("fk_instance_setting_updated_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_instance_setting")),
    )

    op.create_table(
        "quote_approval",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quote_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_note", sa.Text(), nullable=True),
        sa.Column("decided_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "self_approved",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("withdrawn_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'sent_back', 'withdrawn')",
            name=op.f("ck_quote_approval_status_valid"),
        ),
        sa.CheckConstraint(
            "quote_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_quote_approval_hash_format")
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quote.id"],
            name=op.f("fk_quote_approval_quote_id_quote"),
            ondelete="CASCADE",
        ),
        *[
            sa.ForeignKeyConstraint(
                [column],
                ["person.id"],
                name=op.f(f"fk_quote_approval_{column}_person"),
                ondelete="SET NULL",
            )
            for column in ("requested_by_id", "decided_by_id", "withdrawn_by_id")
        ],
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quote_approval")),
    )
    op.create_index(
        op.f("ix_quote_approval_quote_id"), "quote_approval", ["quote_id"], unique=False
    )
    op.create_index(
        "ix_quote_approval_status",
        "quote_approval",
        ["status", "requested_at"],
        unique=False,
    )
    op.create_index(
        "uq_quote_approval_one_in_force",
        "quote_approval",
        ["quote_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('requested', 'approved')"),
    )

    op.execute(
        sa.text(
            "INSERT INTO role (id, label, description) VALUES (:id, :label, :text) "
            "ON CONFLICT (id) DO NOTHING"
        ).bindparams(id=_ROLE_ID, label=_ROLE_LABEL, text=_ROLE_DESCRIPTION)
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM person_role WHERE role_id = :id").bindparams(id=_ROLE_ID)
    )
    op.execute(sa.text("DELETE FROM role WHERE id = :id").bindparams(id=_ROLE_ID))
    op.drop_index("uq_quote_approval_one_in_force", table_name="quote_approval")
    op.drop_index("ix_quote_approval_status", table_name="quote_approval")
    op.drop_index(op.f("ix_quote_approval_quote_id"), table_name="quote_approval")
    op.drop_table("quote_approval")
    op.drop_table("instance_setting")
