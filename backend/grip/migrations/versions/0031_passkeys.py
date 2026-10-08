"""Passkeys: a person's own keys, and a passkey assertion with a decision.

Revision ID: 0031_passkeys
Revises: 0030_vacancy_text_work
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_passkeys"
down_revision: str | None = "0030_vacancy_text_work"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.text("now()")


def upgrade() -> None:
    t = "passkey_credential"
    op.create_table(
        t,
        sa.Column(
            "id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("person_id", UUID, nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("aaguid", sa.String(36), nullable=True),
        sa.Column("device_type", sa.String(20), nullable=True),
        sa.Column("backed_up", sa.Boolean(), nullable=True),
        sa.Column(
            "registration", postgresql.JSONB(), server_default="{}", nullable=False
        ),
        sa.Column("oidc_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", UUID, nullable=True),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f(f"fk_{t}_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_id"],
            ["person.id"],
            name=op.f(f"fk_{t}_revoked_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint("credential_id", name=op.f(f"uq_{t}_credential_id")),
    )
    op.create_index(op.f(f"ix_{t}_person_id"), t, ["person_id"])

    # The passkey assertion that came with a decision: kept with the pending
    # step until the decision is made, and with the evidence afterwards.
    op.add_column(
        "signing_intent", sa.Column("passkey", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "decision_evidence", sa.Column("passkey", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("decision_evidence", "passkey")
    op.drop_column("signing_intent", "passkey")
    op.drop_index(op.f("ix_passkey_credential_person_id"), "passkey_credential")
    op.drop_table("passkey_credential")
