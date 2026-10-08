"""Vacancies: the procedure, advice and approval, texts, and form templates.

Revision ID: 0003_vacancies
Revises: 0002_domain
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_vacancies"
down_revision: str | None = "0002_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "form_template",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("uploaded_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["person.id"],
            name=op.f("fk_form_template_uploaded_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_form_template")),
    )
    op.create_index(
        "uq_form_template_active_kind",
        "form_template",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "vacancy",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("budget_line_id", sa.UUID(), nullable=True),
        sa.Column("function_title", sa.String(length=255), nullable=False),
        sa.Column("fgr_function_name", sa.String(length=255), nullable=True),
        sa.Column("scale", sa.Integer(), nullable=True),
        sa.Column("fte", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("declarable", sa.Boolean(), nullable=False),
        sa.Column("vacancy_type", sa.String(length=30), nullable=False),
        sa.Column("contract_type", sa.String(length=40), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "channels",
            postgresql.ARRAY(sa.String(length=20)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("requester_id", sa.UUID(), nullable=True),
        sa.Column("addressee_name", sa.String(length=255), nullable=True),
        sa.Column("requested_on", sa.Date(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
            "contract_type IN ('temporary_project', 'temporary_before_permanent')",
            name=op.f("ck_vacancy_contract_type"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'requested', 'approved', 'rejected', 'open', "
            "'filled', 'withdrawn')",
            name=op.f("ck_vacancy_status"),
        ),
        sa.CheckConstraint(
            "vacancy_type IN ('regulier', 'specialistisch', 'beoogd', 'gerede')",
            name=op.f("ck_vacancy_vacancy_type"),
        ),
        sa.CheckConstraint(
            "declarable = false OR budget_line_id IS NOT NULL",
            name=op.f("ck_vacancy_declarable_has_budget_line"),
        ),
        sa.CheckConstraint("fte > 0", name=op.f("ck_vacancy_fte_positive")),
        sa.ForeignKeyConstraint(
            ["budget_line_id"],
            ["budget_line.id"],
            name=op.f("fk_vacancy_budget_line_id_budget_line"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["person.id"],
            name=op.f("fk_vacancy_requester_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancy")),
    )
    op.create_index(
        op.f("ix_vacancy_budget_line_id"), "vacancy", ["budget_line_id"], unique=False
    )
    op.create_index(
        op.f("ix_vacancy_requester_id"), "vacancy", ["requester_id"], unique=False
    )
    op.create_index(op.f("ix_vacancy_status"), "vacancy", ["status"], unique=False)
    op.create_table(
        "vacancy_decision",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("vacancy_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("person_name", sa.String(length=255), nullable=False),
        sa.Column("agreed", sa.Boolean(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('hr_advice', 'control_advice', 'approval')",
            name=op.f("ck_vacancy_decision_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_vacancy_decision_person_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_id"],
            ["person.id"],
            name=op.f("fk_vacancy_decision_recorded_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancy.id"],
            name=op.f("fk_vacancy_decision_vacancy_id_vacancy"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancy_decision")),
        sa.UniqueConstraint(
            "vacancy_id", "kind", name=op.f("uq_vacancy_decision_vacancy_id")
        ),
    )
    op.create_index(
        op.f("ix_vacancy_decision_vacancy_id"),
        "vacancy_decision",
        ["vacancy_id"],
        unique=False,
    )
    op.create_table(
        "vacancy_step",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("vacancy_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("ended_on", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('request', 'hr_advice', 'control_advice', 'approval', "
            "'internal_opening', 'priority_candidates', "
            "'government_wide_opening', 'external_market')",
            name=op.f("ck_vacancy_step_kind"),
        ),
        sa.CheckConstraint(
            "ended_on IS NULL OR ended_on >= started_on",
            name=op.f("ck_vacancy_step_ends_after_start"),
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancy.id"],
            name=op.f("fk_vacancy_step_vacancy_id_vacancy"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancy_step")),
        sa.UniqueConstraint(
            "vacancy_id", "kind", name=op.f("uq_vacancy_step_vacancy_id")
        ),
    )
    op.create_index(
        op.f("ix_vacancy_step_vacancy_id"), "vacancy_step", ["vacancy_id"], unique=False
    )
    op.create_table(
        "vacancy_text",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("vacancy_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column("based_on_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("established_by_id", sa.UUID(), nullable=True),
        sa.Column("established_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('vacancy_text', 'motivation')", name=op.f("ck_vacancy_text_kind")
        ),
        sa.CheckConstraint(
            "source <> 'model' OR (model_id IS NOT NULL "
            "AND prompt_version IS NOT NULL)",
            name=op.f("ck_vacancy_text_model_has_provenance"),
        ),
        sa.CheckConstraint(
            "source IN ('human', 'model')", name=op.f("ck_vacancy_text_source")
        ),
        sa.CheckConstraint(
            "(established_at IS NULL) = (established_by_id IS NULL)",
            name=op.f("ck_vacancy_text_established_complete"),
        ),
        sa.ForeignKeyConstraint(
            ["based_on_id"],
            ["vacancy_text.id"],
            name=op.f("fk_vacancy_text_based_on_id_vacancy_text"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["person.id"],
            name=op.f("fk_vacancy_text_created_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["established_by_id"],
            ["person.id"],
            name=op.f("fk_vacancy_text_established_by_id_person"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancy.id"],
            name=op.f("fk_vacancy_text_vacancy_id_vacancy"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancy_text")),
    )
    op.create_index(
        "ix_vacancy_text_vacancy_kind",
        "vacancy_text",
        ["vacancy_id", "kind", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_vacancy_text_vacancy_kind", table_name="vacancy_text")
    op.drop_table("vacancy_text")
    op.drop_index(op.f("ix_vacancy_step_vacancy_id"), table_name="vacancy_step")
    op.drop_table("vacancy_step")
    op.drop_index(op.f("ix_vacancy_decision_vacancy_id"), table_name="vacancy_decision")
    op.drop_table("vacancy_decision")
    op.drop_index(op.f("ix_vacancy_status"), table_name="vacancy")
    op.drop_index(op.f("ix_vacancy_requester_id"), table_name="vacancy")
    op.drop_index(op.f("ix_vacancy_budget_line_id"), table_name="vacancy")
    op.drop_table("vacancy")
    op.drop_index(
        "uq_form_template_active_kind",
        table_name="form_template",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_table("form_template")
