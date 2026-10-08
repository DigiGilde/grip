"""Proof of a decision: signing intents, evidence, and the link from each decision.

Revision ID: 0025_decision_proof
Revises: 0024_quote_approval
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_decision_proof"
down_revision: str | None = "0024_quote_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decision_evidence",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("action", sa.String(length=12), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("quote_id", sa.UUID(), nullable=False),
        sa.Column("quote_hash", sa.String(length=64), nullable=False),
        sa.Column("statement", sa.LargeBinary(), nullable=False),
        sa.Column("statement_hash", sa.String(length=64), nullable=False),
        sa.Column("statement_jws", sa.Text(), nullable=False),
        sa.Column("id_token", sa.Text(), nullable=True),
        sa.Column("idp_jwks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "idp_discovery", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "instance_jwks", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("timestamp_reply", sa.LargeBinary(), nullable=True),
        sa.Column("timestamp_authority", sa.String(length=500), nullable=True),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('accept', 'reject', 'approve', 'send_back')",
            name=op.f("ck_decision_evidence_action_valid"),
        ),
        sa.CheckConstraint(
            "channel IN ('signing_link', 'own_instance', 'internal', 'uploaded_pdf')",
            name=op.f("ck_decision_evidence_channel_valid"),
        ),
        sa.CheckConstraint(
            "quote_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_decision_evidence_hash_format"),
        ),
        sa.CheckConstraint(
            "statement_hash = encode(sha256(statement), 'hex')",
            name=op.f("ck_decision_evidence_hash_of_statement"),
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_decision_evidence_person_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quote.id"],
            name=op.f("fk_decision_evidence_quote_id_quote"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_evidence")),
        sa.UniqueConstraint(
            "statement_hash", name=op.f("uq_decision_evidence_statement_hash")
        ),
    )
    op.create_index(
        op.f("ix_decision_evidence_email"), "decision_evidence", ["email"], unique=False
    )
    op.create_index(
        "ix_decision_evidence_quote",
        "decision_evidence",
        ["quote_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "signing_intent",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("action", sa.String(length=12), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("quote_id", sa.UUID(), nullable=False),
        sa.Column("quote_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "nonce_inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("return_path", sa.String(length=500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_id", sa.UUID(), nullable=True),
        sa.Column("failure", sa.String(length=60), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('accept', 'reject', 'approve', 'send_back')",
            name=op.f("ck_signing_intent_action_valid"),
        ),
        sa.CheckConstraint(
            "channel IN ('signing_link', 'own_instance', 'internal')",
            name=op.f("ck_signing_intent_channel_valid"),
        ),
        sa.CheckConstraint(
            "quote_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_signing_intent_hash_format")
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["decision_evidence.id"],
            name=op.f("fk_signing_intent_evidence_id_decision_evidence"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_signing_intent_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quote.id"],
            name=op.f("fk_signing_intent_quote_id_quote"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signing_intent")),
        sa.UniqueConstraint("nonce", name=op.f("uq_signing_intent_nonce")),
    )
    op.create_index(
        "ix_signing_intent_expires", "signing_intent", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_signing_intent_quote_id"), "signing_intent", ["quote_id"], unique=False
    )
    op.add_column(
        "quote_acceptance", sa.Column("evidence_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_quote_acceptance_evidence_id_decision_evidence"),
        "quote_acceptance",
        "decision_evidence",
        ["evidence_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("quote_approval", sa.Column("evidence_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_quote_approval_evidence_id_decision_evidence"),
        "quote_approval",
        "decision_evidence",
        ["evidence_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("quote_rejection", sa.Column("evidence_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_quote_rejection_evidence_id_decision_evidence"),
        "quote_rejection",
        "decision_evidence",
        ["evidence_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    for table in ("quote_rejection", "quote_approval", "quote_acceptance"):
        op.drop_constraint(
            op.f(f"fk_{table}_evidence_id_decision_evidence"), table, type_="foreignkey"
        )
        op.drop_column(table, "evidence_id")
    op.drop_index(op.f("ix_signing_intent_quote_id"), table_name="signing_intent")
    op.drop_index("ix_signing_intent_expires", table_name="signing_intent")
    op.drop_table("signing_intent")
    op.drop_index("ix_decision_evidence_quote", table_name="decision_evidence")
    op.drop_index(op.f("ix_decision_evidence_email"), table_name="decision_evidence")
    op.drop_table("decision_evidence")
