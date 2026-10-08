"""Functiegebouw Rijk: families, groups with scales, and the link from a vacancy.

Creates the tables and loads the reference file that ships with grip. A later
change of that file is loaded with the recipe or the beheer action, which
upsert; this migration only fills the empty tables.

Revision ID: 0012_function_framework
Revises: 0011_organisation_registry
Create Date: 2026-10-08

"""

import json
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_function_framework"
down_revision: str | None = "0011_organisation_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REFERENCE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "function_framework"
    / "functiegebouw-rijk.json"
)

_VALIDITY = "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    family = op.create_table(
        "function_family",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source", sa.String(10), server_default="manual", nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_function_family")),
        sa.UniqueConstraint("key", name=op.f("uq_function_family_key")),
        sa.CheckConstraint(
            "source IN ('reference', 'manual')",
            name=op.f("ck_function_family_source_valid"),
        ),
        sa.CheckConstraint(_VALIDITY, name=op.f("ck_function_family_validity_order")),
    )
    group = op.create_table(
        "function_group",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("scales", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source", sa.String(10), server_default="manual", nullable=False),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_function_group")),
        sa.UniqueConstraint("source_id", name=op.f("uq_function_group_source_id")),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["function_family.id"],
            name=op.f("fk_function_group_family_id_function_family"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["edited_by_id"],
            ["person.id"],
            name=op.f("fk_function_group_edited_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "source IN ('reference', 'manual')",
            name=op.f("ck_function_group_source_valid"),
        ),
        sa.CheckConstraint(
            "cardinality(scales) >= 1", name=op.f("ck_function_group_has_scales")
        ),
        sa.CheckConstraint(
            "1 <= ALL(scales) AND 19 >= ALL(scales)",
            name=op.f("ck_function_group_scales_in_range"),
        ),
        sa.CheckConstraint(_VALIDITY, name=op.f("ck_function_group_validity_order")),
    )
    op.create_index(
        op.f("ix_function_group_family_id"), "function_group", ["family_id"]
    )

    op.add_column(
        "vacancy",
        sa.Column("function_group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "vacancy", sa.Column("scale_deviation_reason", sa.Text(), nullable=True)
    )
    op.add_column(
        "vacancy",
        sa.Column("addressee_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_vacancy_function_group_id"), "vacancy", ["function_group_id"]
    )
    op.create_foreign_key(
        op.f("fk_vacancy_function_group_id_function_group"),
        "vacancy",
        "function_group",
        ["function_group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_vacancy_addressee_id_person"),
        "vacancy",
        "person",
        ["addressee_id"],
        ["id"],
        ondelete="SET NULL",
    )

    reference = json.loads(_REFERENCE.read_text(encoding="utf-8"))
    families = []
    groups = []
    for family_position, entry in enumerate(reference["families"], start=1):
        family_id = uuid.uuid4()
        families.append(
            {
                "id": family_id,
                "key": entry["key"],
                "name": entry["name"],
                "position": family_position,
                "source": "reference",
                "source_url": entry.get("source_url"),
            }
        )
        for group_position, item in enumerate(entry["groups"], start=1):
            groups.append(
                {
                    "id": uuid.uuid4(),
                    "family_id": family_id,
                    "name": item["name"],
                    "scales": sorted(item["scales"]),
                    "position": group_position,
                    "source": "reference",
                    "source_id": item["source_id"],
                    "source_url": item.get("source_url"),
                }
            )
    op.bulk_insert(family, families)
    op.bulk_insert(group, groups)


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_vacancy_addressee_id_person"), "vacancy", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_vacancy_function_group_id_function_group"),
        "vacancy",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_vacancy_function_group_id"), table_name="vacancy")
    op.drop_column("vacancy", "addressee_id")
    op.drop_column("vacancy", "scale_deviation_reason")
    op.drop_column("vacancy", "function_group_id")
    op.drop_index(op.f("ix_function_group_family_id"), table_name="function_group")
    op.drop_table("function_group")
    op.drop_table("function_family")
