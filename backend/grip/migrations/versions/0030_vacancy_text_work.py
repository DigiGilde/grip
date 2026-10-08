"""Standard vacancy texts, the course of a text, and where a vacancy stands published.

Revision ID: 0030_vacancy_text_work
Revises: 0029_quote_draft
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_vacancy_text_work"
down_revision: str | None = "0029_quote_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.text("now()")


def _person(
    name: str, table: str, *, ondelete: str = "SET NULL"
) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [name], ["person.id"], name=op.f(f"fk_{table}_{name}_person"), ondelete=ondelete
    )


def upgrade() -> None:
    t = "vacancy_text_shared_section"
    op.create_table(
        t,
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("heading", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("shipped_version", sa.String(40), nullable=True),
        sa.Column("changed_by_id", UUID, nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        _person("changed_by_id", t),
        sa.PrimaryKeyConstraint("key", name=op.f(f"pk_{t}")),
    )

    t = "vacancy_text_template"
    op.create_table(
        t,
        sa.Column(
            "id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("catalogue_role_id", UUID, nullable=True),
        sa.Column("role_name", sa.String(255), nullable=False),
        sa.Column("aliases", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("scale_min", sa.Integer(), nullable=True),
        sa.Column("scale_max", sa.Integer(), nullable=True),
        sa.Column("function_group", sa.String(255), nullable=True),
        sa.Column("origin", sa.String(10), nullable=False),
        sa.Column("reviewed_by_id", UUID, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sections", postgresql.JSONB(), nullable=False),
        sa.Column("shipped_version", sa.String(40), nullable=True),
        sa.Column("changed_by_id", UUID, nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.CheckConstraint(
            "origin IN ('example', 'derived', 'manual')",
            name=op.f(f"ck_{t}_origin_valid"),
        ),
        sa.CheckConstraint(
            "btrim(role_name) <> ''", name=op.f(f"ck_{t}_role_not_empty")
        ),
        sa.ForeignKeyConstraint(
            ["catalogue_role_id"],
            ["catalogue_role.id"],
            name=op.f(f"fk_{t}_catalogue_role_id_catalogue_role"),
            ondelete="SET NULL",
        ),
        _person("reviewed_by_id", t),
        _person("changed_by_id", t),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
    )
    op.create_index(
        "uq_vacancy_text_template_role_lower",
        t,
        [sa.text("lower(role_name)")],
        unique=True,
    )

    op.add_column(
        "vacancy_text", sa.Column("template_label", sa.String(255), nullable=True)
    )
    op.drop_constraint(op.f("ck_vacancy_text_source"), "vacancy_text", type_="check")
    op.create_check_constraint(
        op.f("ck_vacancy_text_source"),
        "vacancy_text",
        "source IN ('human', 'model', 'template')",
    )

    t = "vacancy_text_review"
    op.create_table(
        t,
        sa.Column(
            "id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("vacancy_id", UUID, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("text_id", UUID, nullable=False),
        sa.Column("offered_by_id", UUID, nullable=True),
        sa.Column(
            "offered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancy.id"],
            name=op.f(f"fk_{t}_vacancy_id_vacancy"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["text_id"],
            ["vacancy_text.id"],
            name=op.f(f"fk_{t}_text_id_vacancy_text"),
            ondelete="CASCADE",
        ),
        _person("offered_by_id", t),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint(
            "vacancy_id", "kind", "round", name=op.f(f"uq_{t}_vacancy_id")
        ),
    )
    op.create_index("ix_vacancy_text_review_vacancy", t, ["vacancy_id", "kind"])

    t = "vacancy_text_verdict"
    op.create_table(
        t,
        sa.Column(
            "id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("review_id", UUID, nullable=False),
        sa.Column("reviewer_id", UUID, nullable=False),
        sa.Column("verdict", sa.String(10), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.CheckConstraint(
            "verdict IS NULL OR verdict IN ('agreed', 'remarks')",
            name=op.f(f"ck_{t}_verdict_valid"),
        ),
        sa.CheckConstraint(
            "(verdict IS NULL) = (decided_at IS NULL)",
            name=op.f(f"ck_{t}_decided_complete"),
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["vacancy_text_review.id"],
            name=op.f(f"fk_{t}_review_id_vacancy_text_review"),
            ondelete="CASCADE",
        ),
        _person("reviewer_id", t, ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint("review_id", "reviewer_id", name=op.f(f"uq_{t}_review_id")),
    )

    t = "vacancy_text_remark"
    op.create_table(
        t,
        sa.Column(
            "id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("vacancy_id", UUID, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("text_id", UUID, nullable=True),
        sa.Column("section", sa.String(200), server_default="", nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_id", UUID, nullable=True),
        sa.Column("parent_id", UUID, nullable=True),
        sa.Column("resolved_by_id", UUID, nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancy.id"],
            name=op.f(f"fk_{t}_vacancy_id_vacancy"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["text_id"],
            ["vacancy_text.id"],
            name=op.f(f"fk_{t}_text_id_vacancy_text"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["vacancy_text_remark.id"],
            name=op.f(f"fk_{t}_parent_id_vacancy_text_remark"),
            ondelete="CASCADE",
        ),
        _person("author_id", t),
        _person("resolved_by_id", t),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
    )
    op.create_index("ix_vacancy_text_remark_vacancy", t, ["vacancy_id", "kind"])

    t = "vacancy_publication"
    op.create_table(
        t,
        sa.Column(
            "id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("vacancy_id", UUID, nullable=False),
        sa.Column("place", sa.String(20), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("published_on", sa.Date(), nullable=False),
        sa.Column("recorded_by_id", UUID, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False
        ),
        sa.CheckConstraint(
            "place IN ('internal', 'government_wide', 'external')",
            name=op.f(f"ck_{t}_place_valid"),
        ),
        sa.CheckConstraint("url LIKE 'https://%'", name=op.f(f"ck_{t}_url_https")),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancy.id"],
            name=op.f(f"fk_{t}_vacancy_id_vacancy"),
            ondelete="CASCADE",
        ),
        _person("recorded_by_id", t),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint("vacancy_id", "place", name=op.f(f"uq_{t}_vacancy_id")),
    )


def downgrade() -> None:
    op.drop_table("vacancy_publication")
    op.drop_table("vacancy_text_remark")
    op.drop_table("vacancy_text_verdict")
    op.drop_table("vacancy_text_review")
    op.execute("DELETE FROM vacancy_text WHERE source = 'template'")
    op.drop_constraint(op.f("ck_vacancy_text_source"), "vacancy_text", type_="check")
    op.create_check_constraint(
        op.f("ck_vacancy_text_source"), "vacancy_text", "source IN ('human', 'model')"
    )
    op.drop_column("vacancy_text", "template_label")
    op.drop_table("vacancy_text_template")
    op.drop_table("vacancy_text_shared_section")
