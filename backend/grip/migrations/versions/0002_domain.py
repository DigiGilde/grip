"""Domain: rates, people details, assignments, quotes, monthly close, costs.

Revision ID: 0002_domain
Revises: 0001_initial
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_domain"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cost_item",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column(
            "budgeted_cents", sa.BigInteger(), server_default="0", nullable=False
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
            "budgeted_cents >= 0", name=op.f("ck_cost_item_budgeted_not_negative")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cost_item")),
    )
    op.create_table(
        "organisation",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("tooi_uri", sa.String(length=500), nullable=True),
        sa.Column("unit_key", sa.String(length=100), nullable=True),
        sa.Column("instance_uri", sa.String(length=500), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisation")),
        sa.UniqueConstraint("instance_uri", name=op.f("uq_organisation_instance_uri")),
    )
    op.create_index(
        "uq_organisation_tooi_uri_unit_key",
        "organisation",
        ["tooi_uri", "unit_key"],
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("tooi_uri IS NOT NULL"),
    )
    op.create_table(
        "rate_card",
        sa.Column("year", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column(
            "status", sa.String(length=10), server_default="draft", nullable=False
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
            "status IN ('draft', 'active', 'closed')",
            name=op.f("ck_rate_card_status_valid"),
        ),
        sa.CheckConstraint(
            "year BETWEEN 2000 AND 2100", name=op.f("ck_rate_card_year_valid")
        ),
        sa.PrimaryKeyConstraint("year", name=op.f("pk_rate_card")),
    )
    op.create_table(
        "assignment",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("uri", sa.String(length=500), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "kind", sa.String(length=10), server_default="external", nullable=False
        ),
        sa.Column(
            "traffic_form", sa.String(length=10), server_default="none", nullable=False
        ),
        sa.Column(
            "status", sa.String(length=20), server_default="draft", nullable=False
        ),
        sa.Column("client_organisation_id", sa.UUID(), nullable=True),
        sa.Column("contractor_organisation_id", sa.UUID(), nullable=True),
        sa.Column("parent_assignment_uri", sa.String(length=500), nullable=True),
        sa.Column(
            "context_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("client_contact", sa.String(length=255), nullable=True),
        sa.Column("quote_date", sa.Date(), nullable=True),
        sa.Column("quoted_amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "kind IN ('external', 'internal')", name=op.f("ck_assignment_kind_valid")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'requested', 'quoted', 'accepted', 'in_progress', "
            "'completed', 'accounted', 'rejected', 'cancelled')",
            name=op.f("ck_assignment_status_valid"),
        ),
        sa.CheckConstraint(
            "traffic_form IN ('federated', 'document', 'none')",
            name=op.f("ck_assignment_traffic_form_valid"),
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name=op.f("ck_assignment_period_valid"),
        ),
        sa.CheckConstraint(
            "quoted_amount_cents IS NULL OR quoted_amount_cents >= 0",
            name=op.f("ck_assignment_quoted_amount_not_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["client_organisation_id"],
            ["organisation.id"],
            name=op.f("fk_assignment_client_organisation_id_organisation"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contractor_organisation_id"],
            ["organisation.id"],
            name=op.f("fk_assignment_contractor_organisation_id_organisation"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment")),
        sa.UniqueConstraint("uri", name=op.f("uq_assignment_uri")),
    )
    op.create_index(
        op.f("ix_assignment_client_organisation_id"),
        "assignment",
        ["client_organisation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assignment_contractor_organisation_id"),
        "assignment",
        ["contractor_organisation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assignment_parent_assignment_uri"),
        "assignment",
        ["parent_assignment_uri"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assignment_status"), "assignment", ["status"], unique=False
    )
    op.create_table(
        "billability_target",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("target_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.CheckConstraint(
            "target_pct BETWEEN 0 AND 100", name=op.f("ck_billability_target_pct_valid")
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_billability_target_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_billability_target")),
        sa.UniqueConstraint(
            "person_id", "year", name=op.f("uq_billability_target_person_id")
        ),
    )
    op.create_index(
        op.f("ix_billability_target_person_id"),
        "billability_target",
        ["person_id"],
        unique=False,
    )
    op.create_table(
        "hire",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("supplier", sa.String(length=255), nullable=False),
        sa.Column("cost_monthly_rate_cents", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("contract_reference", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "cost_monthly_rate_cents >= 0", name=op.f("ck_hire_rate_not_negative")
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name=op.f("ck_hire_period_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_hire_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hire")),
    )
    op.create_index(op.f("ix_hire_person_id"), "hire", ["person_id"], unique=False)
    op.create_table(
        "invoice_line",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("cost_item_id", sa.UUID(), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("period", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('actual', 'estimate')", name=op.f("ck_invoice_line_kind_valid")
        ),
        sa.ForeignKeyConstraint(
            ["cost_item_id"],
            ["cost_item.id"],
            name=op.f("fk_invoice_line_cost_item_id_cost_item"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_line")),
    )
    op.create_index(
        op.f("ix_invoice_line_cost_item_id"),
        "invoice_line",
        ["cost_item_id"],
        unique=False,
    )
    op.create_table(
        "person_scale",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("billing_scale", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "billing_scale BETWEEN 1 AND 30", name=op.f("ck_person_scale_scale_valid")
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name=op.f("ck_person_scale_period_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_person_scale_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person_scale")),
        sa.UniqueConstraint(
            "person_id", "valid_from", name=op.f("uq_person_scale_person_id")
        ),
    )
    op.create_index(
        op.f("ix_person_scale_person_id"), "person_scale", ["person_id"], unique=False
    )
    op.create_table(
        "rate_band",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=1), nullable=False),
        sa.Column("monthly_rate_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "category IN ('A', 'B', 'C', 'D', 'E')",
            name=op.f("ck_rate_band_category_valid"),
        ),
        sa.CheckConstraint(
            "monthly_rate_cents >= 0", name=op.f("ck_rate_band_rate_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["year"],
            ["rate_card.year"],
            name=op.f("fk_rate_band_year_rate_card"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rate_band")),
        sa.UniqueConstraint("year", "category", name=op.f("uq_rate_band_year")),
    )
    op.create_index(op.f("ix_rate_band_year"), "rate_band", ["year"], unique=False)
    op.create_table(
        "scale_band",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("scale", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=1), nullable=False),
        sa.CheckConstraint(
            "category IN ('A', 'B', 'C', 'D', 'E')",
            name=op.f("ck_scale_band_category_valid"),
        ),
        sa.CheckConstraint(
            "scale BETWEEN 1 AND 30", name=op.f("ck_scale_band_scale_valid")
        ),
        sa.ForeignKeyConstraint(
            ["year"],
            ["rate_card.year"],
            name=op.f("fk_scale_band_year_rate_card"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scale_band")),
        sa.UniqueConstraint("year", "scale", name=op.f("uq_scale_band_year")),
    )
    op.create_index(op.f("ix_scale_band_year"), "scale_band", ["year"], unique=False)
    op.create_table(
        "assignment_role",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'manager')", name=op.f("ck_assignment_role_role_valid")
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignment.id"],
            name=op.f("fk_assignment_role_assignment_id_assignment"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_assignment_role_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_role")),
        sa.UniqueConstraint(
            "assignment_id", "person_id", name=op.f("uq_assignment_role_assignment_id")
        ),
    )
    op.create_index(
        op.f("ix_assignment_role_assignment_id"),
        "assignment_role",
        ["assignment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assignment_role_person_id"),
        "assignment_role",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "uq_assignment_role_one_owner",
        "assignment_role",
        ["assignment_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )
    op.create_table(
        "budget_line",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("position", sa.Integer(), server_default="1", nullable=False),
        sa.Column("role", sa.String(length=255), nullable=True),
        sa.Column("fte", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("rate_category", sa.String(length=1), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
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
            "kind <> 'fixed' OR (amount_cents IS NOT NULL AND year IS NOT NULL "
            "AND fte IS NULL AND rate_category IS NULL)",
            name=op.f("ck_budget_line_fixed_fields"),
        ),
        sa.CheckConstraint(
            "kind <> 'personnel' OR (fte IS NOT NULL AND rate_category IS NOT NULL "
            "AND start_date IS NOT NULL AND end_date IS NOT NULL "
            "AND amount_cents IS NULL AND year IS NULL)",
            name=op.f("ck_budget_line_personnel_fields"),
        ),
        sa.CheckConstraint(
            "kind IN ('personnel', 'fixed')", name=op.f("ck_budget_line_kind_valid")
        ),
        sa.CheckConstraint(
            "rate_category IS NULL OR rate_category IN ('A', 'B', 'C', 'D', 'E')",
            name=op.f("ck_budget_line_category_valid"),
        ),
        sa.CheckConstraint(
            "amount_cents IS NULL OR amount_cents >= 0",
            name=op.f("ck_budget_line_amount_not_negative"),
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name=op.f("ck_budget_line_period_valid"),
        ),
        sa.CheckConstraint(
            "fte IS NULL OR fte > 0", name=op.f("ck_budget_line_fte_positive")
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignment.id"],
            name=op.f("fk_budget_line_assignment_id_assignment"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budget_line")),
    )
    op.create_index(
        op.f("ix_budget_line_assignment_id"),
        "budget_line",
        ["assignment_id"],
        unique=False,
    )
    op.create_table(
        "month_close",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("closed_by_id", sa.UUID(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reopened_by_id", sa.UUID(), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopen_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "extract(day from month) = 1",
            name=op.f("ck_month_close_month_is_first_day"),
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignment.id"],
            name=op.f("fk_month_close_assignment_id_assignment"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["closed_by_id"],
            ["person.id"],
            name=op.f("fk_month_close_closed_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reopened_by_id"],
            ["person.id"],
            name=op.f("fk_month_close_reopened_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_month_close")),
    )
    op.create_index(
        op.f("ix_month_close_assignment_id"),
        "month_close",
        ["assignment_id"],
        unique=False,
    )
    op.create_index(
        "uq_month_close_in_force",
        "month_close",
        ["assignment_id", "month"],
        unique=True,
        postgresql_where=sa.text("reopened_at IS NULL"),
    )
    op.create_table(
        "quote",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("uri", sa.String(length=500), nullable=False),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=True),
        sa.Column(
            "status", sa.String(length=12), server_default="issued", nullable=False
        ),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_by_id", sa.UUID(), nullable=True),
        sa.Column("document_sha256", sa.String(length=64), nullable=True),
        sa.Column("document_ref", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "snapshot_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_quote_hash_format")
        ),
        sa.CheckConstraint(
            "status IN ('issued', 'accepted', 'rejected', 'superseded')",
            name=op.f("ck_quote_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignment.id"],
            name=op.f("fk_quote_assignment_id_assignment"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["issued_by_id"],
            ["person.id"],
            name=op.f("fk_quote_issued_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quote")),
        sa.UniqueConstraint("uri", name=op.f("uq_quote_uri")),
    )
    op.create_index(
        op.f("ix_quote_assignment_id"), "quote", ["assignment_id"], unique=False
    )
    op.create_table(
        "allocation",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("budget_line_id", sa.UUID(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("fte_pct", sa.Numeric(precision=6, scale=3), nullable=False),
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
            "end_date >= start_date", name=op.f("ck_allocation_period_valid")
        ),
        sa.CheckConstraint(
            "fte_pct > 0 AND fte_pct <= 100", name=op.f("ck_allocation_pct_valid")
        ),
        sa.ForeignKeyConstraint(
            ["budget_line_id"],
            ["budget_line.id"],
            name=op.f("fk_allocation_budget_line_id_budget_line"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_allocation_person_id_person"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_allocation")),
    )
    op.create_index(
        op.f("ix_allocation_budget_line_id"),
        "allocation",
        ["budget_line_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_allocation_person_id"), "allocation", ["person_id"], unique=False
    )
    op.create_table(
        "billing_export",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("month_close_id", sa.UUID(), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("exported_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "extract(day from month) = 1",
            name=op.f("ck_billing_export_month_is_first_day"),
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignment.id"],
            name=op.f("fk_billing_export_assignment_id_assignment"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["exported_by_id"],
            ["person.id"],
            name=op.f("fk_billing_export_exported_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["month_close_id"],
            ["month_close.id"],
            name=op.f("fk_billing_export_month_close_id_month_close"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_billing_export")),
    )
    op.create_index(
        op.f("ix_billing_export_assignment_id"),
        "billing_export",
        ["assignment_id"],
        unique=False,
    )
    op.create_table(
        "cost_coverage",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("cost_item_id", sa.UUID(), nullable=False),
        sa.Column("budget_line_id", sa.UUID(), nullable=False),
        sa.Column("pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "pct > 0 AND pct <= 100", name=op.f("ck_cost_coverage_pct_valid")
        ),
        sa.ForeignKeyConstraint(
            ["budget_line_id"],
            ["budget_line.id"],
            name=op.f("fk_cost_coverage_budget_line_id_budget_line"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cost_item_id"],
            ["cost_item.id"],
            name=op.f("fk_cost_coverage_cost_item_id_cost_item"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cost_coverage")),
        sa.UniqueConstraint(
            "cost_item_id", "budget_line_id", name=op.f("uq_cost_coverage_cost_item_id")
        ),
    )
    op.create_index(
        op.f("ix_cost_coverage_budget_line_id"),
        "cost_coverage",
        ["budget_line_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cost_coverage_cost_item_id"),
        "cost_coverage",
        ["cost_item_id"],
        unique=False,
    )
    op.create_table(
        "quote_acceptance",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("quote_id", sa.UUID(), nullable=False),
        sa.Column("quote_hash", sa.String(length=64), nullable=False),
        sa.Column("signer_name", sa.String(length=255), nullable=False),
        sa.Column("signer_email", sa.String(length=320), nullable=False),
        sa.Column("signer_function", sa.String(length=255), nullable=True),
        sa.Column("signer_person_id", sa.UUID(), nullable=True),
        sa.Column(
            "organisation", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("form", sa.String(length=20), nullable=False),
        sa.Column("jws", sa.Text(), nullable=True),
        sa.Column("document_sha256", sa.String(length=64), nullable=True),
        sa.Column("document_ref", sa.String(length=500), nullable=True),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "form <> 'own_instance' OR jws IS NOT NULL",
            name=op.f("ck_quote_acceptance_own_instance_has_jws"),
        ),
        sa.CheckConstraint(
            "form <> 'uploaded_pdf' OR document_sha256 IS NOT NULL",
            name=op.f("ck_quote_acceptance_uploaded_pdf_has_document"),
        ),
        sa.CheckConstraint(
            "form IN ('own_instance', 'signing_link', 'uploaded_pdf')",
            name=op.f("ck_quote_acceptance_form_valid"),
        ),
        sa.CheckConstraint(
            "quote_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_quote_acceptance_hash_format"),
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quote.id"],
            name=op.f("fk_quote_acceptance_quote_id_quote"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_id"],
            ["person.id"],
            name=op.f("fk_quote_acceptance_recorded_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["signer_person_id"],
            ["person.id"],
            name=op.f("fk_quote_acceptance_signer_person_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quote_acceptance")),
        sa.UniqueConstraint("quote_id", name=op.f("uq_quote_acceptance_quote_id")),
    )
    op.create_table(
        "quote_invitation",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("quote_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("invited_by_id", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_id"],
            ["person.id"],
            name=op.f("fk_quote_invitation_invited_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_quote_invitation_person_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quote.id"],
            name=op.f("fk_quote_invitation_quote_id_quote"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quote_invitation")),
    )
    op.create_index(
        op.f("ix_quote_invitation_person_id"),
        "quote_invitation",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quote_invitation_quote_id"),
        "quote_invitation",
        ["quote_id"],
        unique=False,
    )
    op.create_index(
        "uq_quote_invitation_quote_email",
        "quote_invitation",
        ["quote_id", sa.literal_column("lower(email)")],
        unique=True,
    )
    op.create_table(
        "quote_rejection",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("quote_id", sa.UUID(), nullable=False),
        sa.Column("quote_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "organisation", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quote.id"],
            name=op.f("fk_quote_rejection_quote_id_quote"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_id"],
            ["person.id"],
            name=op.f("fk_quote_rejection_recorded_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quote_rejection")),
        sa.UniqueConstraint("quote_id", name=op.f("uq_quote_rejection_quote_id")),
    )
    op.create_table(
        "billing_export_line",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("billing_export_id", sa.UUID(), nullable=False),
        sa.Column("budget_line_id", sa.UUID(), nullable=False),
        sa.Column("allocation_id", sa.UUID(), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("fte_pct", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("category", sa.String(length=1), nullable=False),
        sa.Column("monthly_rate_cents", sa.BigInteger(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["allocation_id"],
            ["allocation.id"],
            name=op.f("fk_billing_export_line_allocation_id_allocation"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["billing_export_id"],
            ["billing_export.id"],
            name=op.f("fk_billing_export_line_billing_export_id_billing_export"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["budget_line_id"],
            ["budget_line.id"],
            name=op.f("fk_billing_export_line_budget_line_id_budget_line"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_billing_export_line_person_id_person"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_billing_export_line")),
    )
    op.create_index(
        op.f("ix_billing_export_line_billing_export_id"),
        "billing_export_line",
        ["billing_export_id"],
        unique=False,
    )
    op.create_table(
        "month_close_line",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("month_close_id", sa.UUID(), nullable=False),
        sa.Column("allocation_id", sa.UUID(), nullable=False),
        sa.Column("planned_fte_pct", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column(
            "established_fte_pct", sa.Numeric(precision=6, scale=3), nullable=False
        ),
        sa.CheckConstraint(
            "established_fte_pct >= 0 AND established_fte_pct <= 100",
            name=op.f("ck_month_close_line_pct_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["allocation_id"],
            ["allocation.id"],
            name=op.f("fk_month_close_line_allocation_id_allocation"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["month_close_id"],
            ["month_close.id"],
            name=op.f("fk_month_close_line_month_close_id_month_close"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_month_close_line")),
        sa.UniqueConstraint(
            "month_close_id",
            "allocation_id",
            name=op.f("uq_month_close_line_month_close_id"),
        ),
    )
    op.create_index(
        op.f("ix_month_close_line_allocation_id"),
        "month_close_line",
        ["allocation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_month_close_line_month_close_id"),
        "month_close_line",
        ["month_close_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_month_close_line_month_close_id"), table_name="month_close_line"
    )
    op.drop_index(
        op.f("ix_month_close_line_allocation_id"), table_name="month_close_line"
    )
    op.drop_table("month_close_line")
    op.drop_index(
        op.f("ix_billing_export_line_billing_export_id"),
        table_name="billing_export_line",
    )
    op.drop_table("billing_export_line")
    op.drop_table("quote_rejection")
    op.drop_index("uq_quote_invitation_quote_email", table_name="quote_invitation")
    op.drop_index(op.f("ix_quote_invitation_quote_id"), table_name="quote_invitation")
    op.drop_index(op.f("ix_quote_invitation_person_id"), table_name="quote_invitation")
    op.drop_table("quote_invitation")
    op.drop_table("quote_acceptance")
    op.drop_index(op.f("ix_cost_coverage_cost_item_id"), table_name="cost_coverage")
    op.drop_index(op.f("ix_cost_coverage_budget_line_id"), table_name="cost_coverage")
    op.drop_table("cost_coverage")
    op.drop_index(op.f("ix_billing_export_assignment_id"), table_name="billing_export")
    op.drop_table("billing_export")
    op.drop_index(op.f("ix_allocation_person_id"), table_name="allocation")
    op.drop_index(op.f("ix_allocation_budget_line_id"), table_name="allocation")
    op.drop_table("allocation")
    op.drop_index(op.f("ix_quote_assignment_id"), table_name="quote")
    op.drop_table("quote")
    op.drop_index(
        "uq_month_close_in_force",
        table_name="month_close",
        postgresql_where=sa.text("reopened_at IS NULL"),
    )
    op.drop_index(op.f("ix_month_close_assignment_id"), table_name="month_close")
    op.drop_table("month_close")
    op.drop_index(op.f("ix_budget_line_assignment_id"), table_name="budget_line")
    op.drop_table("budget_line")
    op.drop_index(
        "uq_assignment_role_one_owner",
        table_name="assignment_role",
        postgresql_where=sa.text("role = 'owner'"),
    )
    op.drop_index(op.f("ix_assignment_role_person_id"), table_name="assignment_role")
    op.drop_index(
        op.f("ix_assignment_role_assignment_id"), table_name="assignment_role"
    )
    op.drop_table("assignment_role")
    op.drop_index(op.f("ix_scale_band_year"), table_name="scale_band")
    op.drop_table("scale_band")
    op.drop_index(op.f("ix_rate_band_year"), table_name="rate_band")
    op.drop_table("rate_band")
    op.drop_index(op.f("ix_person_scale_person_id"), table_name="person_scale")
    op.drop_table("person_scale")
    op.drop_index(op.f("ix_invoice_line_cost_item_id"), table_name="invoice_line")
    op.drop_table("invoice_line")
    op.drop_index(op.f("ix_hire_person_id"), table_name="hire")
    op.drop_table("hire")
    op.drop_index(
        op.f("ix_billability_target_person_id"), table_name="billability_target"
    )
    op.drop_table("billability_target")
    op.drop_index(op.f("ix_assignment_status"), table_name="assignment")
    op.drop_index(op.f("ix_assignment_parent_assignment_uri"), table_name="assignment")
    op.drop_index(
        op.f("ix_assignment_contractor_organisation_id"), table_name="assignment"
    )
    op.drop_index(op.f("ix_assignment_client_organisation_id"), table_name="assignment")
    op.drop_table("assignment")
    op.drop_table("rate_card")
    op.drop_index(
        "uq_organisation_tooi_uri_unit_key",
        table_name="organisation",
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("tooi_uri IS NOT NULL"),
    )
    op.drop_table("organisation")
    op.drop_table("cost_item")
