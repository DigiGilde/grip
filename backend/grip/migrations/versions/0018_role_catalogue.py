"""Role catalogue: a budget line refers to a role instead of holding free text.

Existing role texts are taken over into the catalogue: one entry per name,
whatever the capitals or the spacing, in the spelling used most. Every entry
is marked for review, and an audit row per entry lists the spellings it was
made from and the number of lines, so no value is lost and a beheerder can
merge what turns out to be the same role.

Revision ID: 0018_role_catalogue
Revises: 0017_intended_person
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_role_catalogue"
down_revision: str | None = "0017_intended_person"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A role name as it is stored: trimmed, single spaces.
_CLEAN = "regexp_replace(btrim(role), '\\s+', ' ', 'g')"


def upgrade() -> None:
    op.create_table(
        "catalogue_role",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("source", sa.String(10), server_default="manual", nullable=False),
        sa.Column("wies_public_id", sa.String(40), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "needs_review",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            "source IN ('wies', 'manual')", name=op.f("ck_catalogue_role_source_valid")
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''", name=op.f("ck_catalogue_role_name_not_empty")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["person.id"],
            name=op.f("fk_catalogue_role_created_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalogue_role")),
        sa.UniqueConstraint("id", "name", name=op.f("uq_catalogue_role_id")),
    )
    op.create_index(
        "uq_catalogue_role_name_lower",
        "catalogue_role",
        [sa.text("lower(name)")],
        unique=True,
    )
    op.create_index(
        "uq_catalogue_role_wies_public_id",
        "catalogue_role",
        ["wies_public_id"],
        unique=True,
        postgresql_where=sa.text("wies_public_id IS NOT NULL"),
    )

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

    op.add_column(
        "budget_line",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(op.f("ix_budget_line_role_id"), "budget_line", ["role_id"])
    op.alter_column("budget_line", "description", server_default="")

    # --- take over the existing texts -----------------------------------------
    op.execute(
        "UPDATE budget_line SET role = NULL WHERE role IS NOT NULL AND btrim(role) = ''"
    )
    op.execute(
        f"""
        INSERT INTO catalogue_role (name, source, needs_review)
        SELECT name, 'manual', true
        FROM (
            SELECT DISTINCT ON (lower(name)) name
            FROM (
                SELECT {_CLEAN} AS name, count(*) AS lines
                FROM budget_line
                WHERE role IS NOT NULL
                GROUP BY 1
            ) spelled
            ORDER BY lower(name), lines DESC, name
        ) chosen
        """
    )
    op.execute(
        f"""
        INSERT INTO audit_log (action, entity, entity_id, new_value)
        SELECT 'create', 'catalogue_role', c.id::text,
               jsonb_build_object(
                   'name', c.name,
                   'source', 'migration',
                   'taken_over_from', jsonb_agg(DISTINCT b.role),
                   'budget_lines', count(*)
               )
        FROM catalogue_role c
        JOIN budget_line b ON lower({_CLEAN.replace("role", "b.role")}) = lower(c.name)
        GROUP BY c.id, c.name
        """
    )
    op.execute(
        f"""
        UPDATE budget_line b
        SET role_id = c.id, role = c.name
        FROM catalogue_role c
        WHERE b.role IS NOT NULL
          AND lower({_CLEAN.replace("role", "b.role")}) = lower(c.name)
        """
    )

    op.create_foreign_key(
        "fk_budget_line_role_catalogue_role",
        "budget_line",
        "catalogue_role",
        ["role_id", "role"],
        ["id", "name"],
        onupdate="CASCADE",
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_budget_line_role_with_reference"),
        "budget_line",
        "(role_id IS NULL) = (role IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_budget_line_named"),
        "budget_line",
        "description <> '' OR role IS NOT NULL",
    )


def downgrade() -> None:
    # The role texts stay on the lines; only the catalogue goes.
    op.drop_constraint(op.f("ck_budget_line_named"), "budget_line", type_="check")
    op.drop_constraint(
        op.f("ck_budget_line_role_with_reference"), "budget_line", type_="check"
    )
    op.drop_constraint(
        "fk_budget_line_role_catalogue_role", "budget_line", type_="foreignkey"
    )
    op.alter_column("budget_line", "description", server_default=None)
    op.drop_index(op.f("ix_budget_line_role_id"), table_name="budget_line")
    op.drop_column("budget_line", "role_id")
    op.drop_index(
        op.f("ix_catalogue_role_sync_run_finished_at"),
        table_name="catalogue_role_sync_run",
    )
    op.drop_table("catalogue_role_sync_run")
    op.drop_index("uq_catalogue_role_wies_public_id", table_name="catalogue_role")
    op.drop_index("uq_catalogue_role_name_lower", table_name="catalogue_role")
    op.drop_table("catalogue_role")
