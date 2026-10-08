"""Persons before an email exists: URI, standing, and the proposal to Wies.

Revision ID: 0013_person_standing
Revises: 0012_function_framework
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from grip.core.config import get_settings

revision: str = "0013_person_standing"
down_revision: str | None = "0012_function_framework"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("person", "email", existing_type=sa.String(320), nullable=True)
    op.add_column("person", sa.Column("uri", sa.String(500), nullable=True))
    op.add_column("person", sa.Column("wies_public_id", sa.String(64), nullable=True))
    op.add_column(
        "person",
        sa.Column(
            "identity_source",
            sa.String(20),
            server_default=sa.text("'grip'"),
            nullable=False,
        ),
    )
    base = get_settings().INSTANCE_BASE_URI.rstrip("/")
    op.execute(
        sa.text(
            "UPDATE person SET uri = :base || '/id/persoon/' || id::text "
            "WHERE uri IS NULL"
        ).bindparams(base=base)
    )
    op.create_unique_constraint(op.f("uq_person_uri"), "person", ["uri"])
    op.create_unique_constraint(
        op.f("uq_person_wies_public_id"), "person", ["wies_public_id"]
    )

    op.create_table(
        "person_standing",
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_ref", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("recorded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("remove_after", sa.Date(), nullable=True),
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
            "stage IN ('prospective', 'colleague', 'left')",
            name=op.f("ck_person_standing_stage_valid"),
        ),
        sa.CheckConstraint(
            "source IN ('grip', 'wies', 'recruitment', 'personnel')",
            name=op.f("ck_person_standing_source_valid"),
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name=op.f("ck_person_standing_dates_ordered"),
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_person_standing_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_id"],
            ["person.id"],
            name=op.f("fk_person_standing_recorded_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("person_id", name=op.f("pk_person_standing")),
    )
    op.create_table(
        "colleague_proposal",
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suborganization", sa.String(255), nullable=True),
        sa.Column(
            "state", sa.String(20), server_default=sa.text("'open'"), nullable=False
        ),
        sa.Column("withdrawn_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
            "state IN ('open', 'confirmed', 'declined', 'withdrawn')",
            name=op.f("ck_colleague_proposal_state_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_colleague_proposal_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("person_id", name=op.f("pk_colleague_proposal")),
    )


def downgrade() -> None:
    op.drop_table("colleague_proposal")
    op.drop_table("person_standing")
    op.drop_constraint(op.f("uq_person_wies_public_id"), "person", type_="unique")
    op.drop_constraint(op.f("uq_person_uri"), "person", type_="unique")
    op.drop_column("person", "identity_source")
    op.drop_column("person", "wies_public_id")
    op.drop_column("person", "uri")
    # A person without an address cannot go back to a mandatory address.
    op.execute(
        "UPDATE person SET email = 'onbekend+' || id::text || '@grip.invalid' "
        "WHERE email IS NULL"
    )
    op.alter_column("person", "email", existing_type=sa.String(320), nullable=False)
