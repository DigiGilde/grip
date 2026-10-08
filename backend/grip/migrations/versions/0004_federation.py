"""Federation: peers, outbox and inbox.

Revision ID: 0004_federation
Revises: 0003_vacancies
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_federation"
down_revision: str | None = "0003_vacancies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "peer",
        _uuid_pk(),
        sa.Column("peer_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("organisation_tooi_uri", sa.String(length=500), nullable=False),
        sa.Column("base_uri", sa.String(length=500), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "grant_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("jwks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("jwks_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('counterpart', 'parent', 'child', 'corpus')",
            name=op.f("ck_peer_role_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_peer")),
        sa.UniqueConstraint("peer_id", name=op.f("uq_peer_peer_id")),
    )
    op.create_index(op.f("ix_peer_base_uri"), "peer", ["base_uri"])

    op.create_table(
        "federation_outbox",
        _uuid_pk(),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("peer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service", sa.String(length=100), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="pending", nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'rejected', 'dead')",
            name=op.f("ck_federation_outbox_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["peer_id"],
            ["peer.id"],
            name=op.f("fk_federation_outbox_peer_id_peer"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_federation_outbox")),
        sa.UniqueConstraint(
            "peer_id", "message_id", name=op.f("uq_federation_outbox_peer_id")
        ),
    )
    op.create_index(
        op.f("ix_federation_outbox_peer_id"), "federation_outbox", ["peer_id"]
    )
    op.create_index(
        "ix_federation_outbox_due", "federation_outbox", ["status", "next_attempt_at"]
    )

    op.create_table(
        "federation_inbox",
        _uuid_pk(),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("peer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["peer_id"],
            ["peer.id"],
            name=op.f("fk_federation_inbox_peer_id_peer"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_federation_inbox")),
        sa.UniqueConstraint(
            "peer_id", "message_id", name=op.f("uq_federation_inbox_peer_id")
        ),
    )
    op.create_index(
        op.f("ix_federation_inbox_peer_id"), "federation_inbox", ["peer_id"]
    )
    op.create_index(
        "ix_federation_inbox_unprocessed",
        "federation_inbox",
        ["processed_at", "received_at"],
    )


def downgrade() -> None:
    op.drop_table("federation_inbox")
    op.drop_table("federation_outbox")
    op.drop_index(op.f("ix_peer_base_uri"), table_name="peer")
    op.drop_table("peer")
