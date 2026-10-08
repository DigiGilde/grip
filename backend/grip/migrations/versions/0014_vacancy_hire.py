"""Vacancy: reference in the recruitment system, and who was hired.

Revision ID: 0014_vacancy_hire
Revises: 0013_person_standing
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_vacancy_hire"
down_revision: str | None = "0013_person_standing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vacancy_recruitment_ref",
        sa.Column("vacancy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "system", sa.String(40), server_default=sa.text("'emply'"), nullable=False
        ),
        sa.Column("reference", sa.String(255), nullable=False),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancy.id"],
            name=op.f("fk_vacancy_recruitment_ref_vacancy_id_vacancy"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("vacancy_id", name=op.f("pk_vacancy_recruitment_ref")),
    )
    op.create_table(
        "vacancy_hire",
        sa.Column("vacancy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("recorded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_vacancy_hire_person_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_id"],
            ["person.id"],
            name=op.f("fk_vacancy_hire_recorded_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancy.id"],
            name=op.f("fk_vacancy_hire_vacancy_id_vacancy"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("vacancy_id", name=op.f("pk_vacancy_hire")),
    )
    op.create_index(
        op.f("ix_vacancy_hire_person_id"), "vacancy_hire", ["person_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_vacancy_hire_person_id"), table_name="vacancy_hire")
    op.drop_table("vacancy_hire")
    op.drop_table("vacancy_recruitment_ref")
