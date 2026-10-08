"""Initial schema: person, functions, sessions, audit log.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The functions a person can hold in an instance. Kept literal here on
# purpose: a migration must not change when the application code does.
_ROLES = [
    (
        "beheerder",
        "Beheerder",
        "Beheert tarievenkaarten, gebruikers en functies; mag gesloten jaren "
        "wijzigen met een auditregel.",
    ),
    (
        "planner",
        "Planner",
        "Bewerkt inzet en open rollen over alle opdrachten.",
    ),
    (
        "lezer",
        "Lezer",
        "Ziet opdrachten en totalen in.",
    ),
    (
        "aanvrager",
        "Aanvrager",
        "Doet aanvragen als opdrachtgever.",
    ),
    (
        "tekenbevoegde",
        "Tekenbevoegde",
        "Accepteert offertes namens de eenheid.",
    ),
]


def upgrade() -> None:
    op.create_table(
        "person",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("oidc_subject", sa.String(length=255), nullable=True),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["person.id"],
            name=op.f("fk_person_manager_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person")),
        sa.UniqueConstraint("oidc_subject", name=op.f("uq_person_oidc_subject")),
    )
    op.create_index(op.f("ix_person_manager_id"), "person", ["manager_id"])
    op.create_index(
        "uq_person_email_lower", "person", [sa.text("lower(email)")], unique=True
    )

    role = op.create_table(
        "role",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role")),
    )
    op.bulk_insert(
        role,
        [{"id": i, "label": label, "description": d} for i, label, d in _ROLES],
    )

    op.create_table(
        "person_role",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", sa.String(length=50), nullable=False),
        sa.Column(
            "start_date",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("granted_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name=op.f("ck_person_role_period_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_id"],
            ["person.id"],
            name=op.f("fk_person_role_granted_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_person_role_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["role.id"],
            name=op.f("fk_person_role_role_id_role"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person_role")),
    )
    op.create_index(op.f("ix_person_role_person_id"), "person_role", ["person_id"])
    op.create_index(op.f("ix_person_role_role_id"), "person_role", ["role_id"])
    op.create_index(
        op.f("ix_person_role_granted_by_id"), "person_role", ["granted_by_id"]
    )

    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("entity", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["person.id"],
            name=op.f("fk_audit_log_actor_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_actor_id"), "audit_log", ["actor_id"])
    op.create_index(op.f("ix_audit_log_occurred_at"), "audit_log", ["occurred_at"])
    op.create_index("ix_audit_log_entity", "audit_log", ["entity", "entity_id"])

    op.create_table(
        "http_session",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_http_session")),
    )
    op.create_index(op.f("ix_http_session_expires_at"), "http_session", ["expires_at"])


def downgrade() -> None:
    op.drop_table("http_session")
    op.drop_table("audit_log")
    op.drop_table("person_role")
    op.drop_table("role")
    op.drop_table("person")
