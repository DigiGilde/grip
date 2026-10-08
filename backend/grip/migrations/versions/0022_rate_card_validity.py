"""Rate cards valid for a period instead of a calendar year.

Every existing card becomes a card valid from 1 January to 31 December of
its year, with the same status; its rates and scale mapping are re-keyed to
the card. Audit rows that named a card by its year now name it by its id.
A delivery of billing data gets a kind: the original, or a correction.

Revision ID: 0022_rate_card_validity
Revises: 0021_quote_reference
Create Date: 2026-10-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_rate_card_validity"
down_revision: str | None = "0021_quote_reference"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BANDS = ("rate_band", "scale_band")
_KEY = {"rate_band": "category", "scale_band": "scale"}


def upgrade() -> None:
    op.add_column(
        "rate_card",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.add_column("rate_card", sa.Column("name", sa.String(length=100)))
    op.add_column("rate_card", sa.Column("valid_from", sa.Date()))
    op.add_column("rate_card", sa.Column("valid_to", sa.Date()))
    op.execute(
        """
        UPDATE rate_card
        SET name = 'Tarieven ' || year,
            valid_from = make_date(year, 1, 1),
            valid_to = make_date(year, 12, 31)
        """
    )
    op.alter_column("rate_card", "name", nullable=False)
    op.alter_column("rate_card", "valid_from", nullable=False)

    for table in _BANDS:
        op.add_column(table, sa.Column("rate_card_id", postgresql.UUID(as_uuid=True)))
        op.execute(
            f"""
            UPDATE {table} AS band SET rate_card_id = card.id
            FROM rate_card AS card WHERE card.year = band.year
            """
        )
        op.alter_column(table, "rate_card_id", nullable=False)
        op.drop_constraint(
            op.f(f"fk_{table}_year_rate_card"), table, type_="foreignkey"
        )
        op.drop_constraint(op.f(f"uq_{table}_year"), table, type_="unique")
        op.drop_index(op.f(f"ix_{table}_year"), table_name=table)

    # Audit rows named a card by its year; they name it by its id from now on.
    op.execute(
        """
        UPDATE audit_log AS log SET entity_id = card.id::text
        FROM rate_card AS card
        WHERE log.entity = 'rate_card' AND log.entity_id = card.year::text
        """
    )
    op.execute(
        """
        UPDATE audit_log AS log
        SET entity_id = card.id::text || '/' || split_part(log.entity_id, '/', 2)
        FROM rate_card AS card
        WHERE log.entity IN ('rate_band', 'scale_band')
          AND split_part(log.entity_id, '/', 1) = card.year::text
        """
    )

    for table in _BANDS:
        op.drop_column(table, "year")
    op.drop_constraint(op.f("ck_rate_card_year_valid"), "rate_card", type_="check")
    op.drop_constraint(op.f("pk_rate_card"), "rate_card", type_="primary")
    op.drop_column("rate_card", "year")
    op.create_primary_key(op.f("pk_rate_card"), "rate_card", ["id"])
    op.create_index(op.f("ix_rate_card_valid_from"), "rate_card", ["valid_from"])
    op.create_check_constraint(
        op.f("ck_rate_card_period_valid"),
        "rate_card",
        "valid_to IS NULL OR valid_to >= valid_from",
    )
    op.create_check_constraint(
        op.f("ck_rate_card_name_not_empty"), "rate_card", "btrim(name) <> ''"
    )
    # Cards that price never overlap; a draft may overlap the card it will
    # follow.
    op.execute(
        """
        ALTER TABLE rate_card ADD CONSTRAINT ex_rate_card_no_overlap
        EXCLUDE USING gist (daterange(valid_from, valid_to, '[]') WITH &&)
        WHERE (status <> 'draft')
        """
    )
    for table in _BANDS:
        op.create_foreign_key(
            op.f(f"fk_{table}_rate_card_id_rate_card"),
            table,
            "rate_card",
            ["rate_card_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_unique_constraint(
            op.f(f"uq_{table}_rate_card_id"), table, ["rate_card_id", _KEY[table]]
        )
        op.create_index(op.f(f"ix_{table}_rate_card_id"), table, ["rate_card_id"])


    # A delivery of billing data is the original of a month or a correction
    # on it (naverrekening).
    op.add_column(
        "billing_export",
        sa.Column(
            "kind", sa.String(length=12), server_default="original", nullable=False
        ),
    )
    op.add_column("billing_export", sa.Column("reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_billing_export_kind_valid"),
        "billing_export",
        "kind IN ('original', 'correction')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_billing_export_kind_valid"), "billing_export", type_="check"
    )
    op.drop_column("billing_export", "reason")
    op.drop_column("billing_export", "kind")
    # The older schema knows one card per calendar year. Anything else cannot
    # be expressed in it.
    odd = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT count(*) FROM rate_card
            WHERE extract(month from valid_from) <> 1
               OR valid_to IS NULL
               OR valid_to <> make_date(extract(year from valid_from)::int, 12, 31)
            """
            )
        )
        .scalar_one()
    )
    doubles = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT count(*) FROM (
                SELECT extract(year from valid_from) FROM rate_card
                GROUP BY 1 HAVING count(*) > 1
            ) AS years
            """
            )
        )
        .scalar_one()
    )
    if odd or doubles:
        raise RuntimeError(
            "Cannot downgrade: there are rate cards that do not span exactly one "
            "calendar year, or two cards in one year."
        )

    op.add_column("rate_card", sa.Column("year", sa.Integer()))
    op.execute("UPDATE rate_card SET year = extract(year from valid_from)::int")
    for table in _BANDS:
        op.add_column(table, sa.Column("year", sa.Integer()))
        op.execute(
            f"""
            UPDATE {table} AS band SET year = card.year
            FROM rate_card AS card WHERE card.id = band.rate_card_id
            """
        )
        op.alter_column(table, "year", nullable=False)
        op.drop_index(op.f(f"ix_{table}_rate_card_id"), table_name=table)
        op.drop_constraint(op.f(f"uq_{table}_rate_card_id"), table, type_="unique")
        op.drop_constraint(
            op.f(f"fk_{table}_rate_card_id_rate_card"), table, type_="foreignkey"
        )
    op.execute(
        """
        UPDATE audit_log AS log SET entity_id = card.year::text
        FROM rate_card AS card
        WHERE log.entity = 'rate_card' AND log.entity_id = card.id::text
        """
    )
    op.execute(
        """
        UPDATE audit_log AS log
        SET entity_id = card.year::text || '/' || split_part(log.entity_id, '/', 2)
        FROM rate_card AS card
        WHERE log.entity IN ('rate_band', 'scale_band')
          AND split_part(log.entity_id, '/', 1) = card.id::text
        """
    )
    op.execute("ALTER TABLE rate_card DROP CONSTRAINT ex_rate_card_no_overlap")
    op.drop_constraint(op.f("ck_rate_card_name_not_empty"), "rate_card", type_="check")
    op.drop_constraint(op.f("ck_rate_card_period_valid"), "rate_card", type_="check")
    op.drop_index(op.f("ix_rate_card_valid_from"), table_name="rate_card")
    op.drop_constraint(op.f("pk_rate_card"), "rate_card", type_="primary")
    op.alter_column("rate_card", "year", nullable=False)
    op.create_primary_key(op.f("pk_rate_card"), "rate_card", ["year"])
    op.create_check_constraint(
        op.f("ck_rate_card_year_valid"), "rate_card", "year BETWEEN 2000 AND 2100"
    )
    for table in _BANDS:
        op.drop_column(table, "rate_card_id")
        op.create_foreign_key(
            op.f(f"fk_{table}_year_rate_card"),
            table,
            "rate_card",
            ["year"],
            ["year"],
            ondelete="CASCADE",
        )
        op.create_unique_constraint(
            op.f(f"uq_{table}_year"), table, ["year", _KEY[table]]
        )
        op.create_index(op.f(f"ix_{table}_year"), table, ["year"])
    op.drop_column("rate_card", "valid_to")
    op.drop_column("rate_card", "valid_from")
    op.drop_column("rate_card", "name")
    op.drop_column("rate_card", "id")
