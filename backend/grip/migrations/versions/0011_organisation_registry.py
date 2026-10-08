"""Organisations from the public register: hierarchy, types, source, sync runs.

Revision ID: 0011_organisation_registry
Revises: 0010_verbal_agreement
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_organisation_registry"
down_revision: str | None = "0010_verbal_agreement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organisation", sa.Column("label", sa.String(300), nullable=True))
    op.add_column(
        "organisation",
        sa.Column("source", sa.String(10), server_default="manual", nullable=False),
    )
    op.add_column(
        "organisation",
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "organisation",
        sa.Column(
            "abbreviations",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "organisation",
        sa.Column(
            "organisation_types",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("organisation", sa.Column("main_type", sa.String(100), nullable=True))
    op.add_column(
        "organisation",
        sa.Column("related_ministry_tooi", sa.String(500), nullable=True),
    )
    op.add_column(
        "organisation", sa.Column("registry_id", sa.String(40), nullable=True)
    )
    op.add_column(
        "organisation", sa.Column("source_url", sa.String(500), nullable=True)
    )
    op.add_column("organisation", sa.Column("end_date", sa.Date(), nullable=True))
    op.create_foreign_key(
        op.f("fk_organisation_parent_id_organisation"),
        "organisation",
        "organisation",
        ["parent_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_organisation_source_valid"),
        "organisation",
        "source IN ('registry', 'manual')",
    )
    op.create_index(op.f("ix_organisation_source"), "organisation", ["source"])
    op.create_index(op.f("ix_organisation_parent_id"), "organisation", ["parent_id"])
    op.create_index(op.f("ix_organisation_main_type"), "organisation", ["main_type"])
    op.create_index(op.f("ix_organisation_end_date"), "organisation", ["end_date"])
    op.create_index(
        "uq_organisation_registry_id",
        "organisation",
        ["registry_id"],
        unique=True,
        postgresql_where=sa.text("registry_id IS NOT NULL"),
    )

    op.create_table(
        "organisation_sync_run",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
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
            name=op.f("ck_organisation_sync_run_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["started_by_id"],
            ["person.id"],
            name=op.f("fk_organisation_sync_run_started_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisation_sync_run")),
    )
    op.create_index(
        op.f("ix_organisation_sync_run_finished_at"),
        "organisation_sync_run",
        ["finished_at"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_organisation_sync_run_finished_at"),
        table_name="organisation_sync_run",
    )
    op.drop_table("organisation_sync_run")
    op.drop_index("uq_organisation_registry_id", table_name="organisation")
    op.drop_index(op.f("ix_organisation_end_date"), table_name="organisation")
    op.drop_index(op.f("ix_organisation_main_type"), table_name="organisation")
    op.drop_index(op.f("ix_organisation_parent_id"), table_name="organisation")
    op.drop_index(op.f("ix_organisation_source"), table_name="organisation")
    op.drop_constraint(
        op.f("ck_organisation_source_valid"), "organisation", type_="check"
    )
    op.drop_constraint(
        op.f("fk_organisation_parent_id_organisation"),
        "organisation",
        type_="foreignkey",
    )
    for column in (
        "end_date",
        "source_url",
        "registry_id",
        "related_ministry_tooi",
        "main_type",
        "organisation_types",
        "abbreviations",
        "parent_id",
        "source",
        "label",
    ):
        op.drop_column("organisation", column)
