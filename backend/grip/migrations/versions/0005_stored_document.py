"""Stored documents: files kept with a record, such as a signed quote.

Revision ID: 0005_stored_document
Revises: 0004_federation
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_stored_document"
down_revision: str | None = "0004_federation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stored_document",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "size_bytes >= 0", name=op.f("ck_stored_document_size_not_negative")
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_stored_document_hash_format")
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["person.id"],
            name=op.f("fk_stored_document_uploaded_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_document")),
    )
    op.create_index(
        op.f("ix_stored_document_sha256"), "stored_document", ["sha256"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_stored_document_sha256"), table_name="stored_document")
    op.drop_table("stored_document")
