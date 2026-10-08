"""Roles of a person: which catalogue roles someone can be staffed in.

Also makes sure the table for runs of the role sync exists: a database that
applied an early copy of 0018 does not have it.

Revision ID: 0019_person_roles
Revises: 0018_role_catalogue
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_person_roles"
down_revision: str | None = "0018_role_catalogue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "person_catalogue_role",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(10), server_default="manual", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('wies', 'manual')",
            name=op.f("ck_person_catalogue_role_source_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_person_catalogue_role_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["catalogue_role.id"],
            name=op.f("fk_person_catalogue_role_role_id_catalogue_role"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person_catalogue_role")),
        sa.UniqueConstraint(
            "person_id", "role_id", name=op.f("uq_person_catalogue_role_person_id")
        ),
    )
    op.create_index(
        op.f("ix_person_catalogue_role_person_id"),
        "person_catalogue_role",
        ["person_id"],
    )
    op.create_index(
        op.f("ix_person_catalogue_role_role_id"), "person_catalogue_role", ["role_id"]
    )

    if not sa.inspect(op.get_bind()).has_table("catalogue_role_sync_run"):
        op.create_table(
            "catalogue_role_sync_run",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column(
                "result",
                postgresql.JSONB(),
                server_default=sa.text("'{}'::jsonb"),
                nullable=False,
            ),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.CheckConstraint(
                "status IN ('completed', 'failed')",
                name=op.f("ck_catalogue_role_sync_run_status_valid"),
            ),
            sa.ForeignKeyConstraint(
                ["started_by_id"],
                ["person.id"],
                name=op.f("fk_catalogue_role_sync_run_started_by_id_person"),
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_catalogue_role_sync_run")),
        )
        op.create_index(
            op.f("ix_catalogue_role_sync_run_finished_at"),
            "catalogue_role_sync_run",
            ["finished_at"],
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_person_catalogue_role_role_id"), table_name="person_catalogue_role"
    )
    op.drop_index(
        op.f("ix_person_catalogue_role_person_id"), table_name="person_catalogue_role"
    )
    op.drop_table("person_catalogue_role")
