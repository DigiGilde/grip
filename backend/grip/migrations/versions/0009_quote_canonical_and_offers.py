"""Quote: one canonical form and one hash; offers per quote; no traffic form.

Three changes that belong together (ADR 0020 and 0021):

1. A quote gets its canonical form: the content in contract terms as RFC
   8785 JSON, stored as bytes. The hash of the quote becomes the SHA-256
   over those bytes, and the database ties the two together. The separate
   JSON copy in code names goes away; it is read from the canonical form.
   Existing quotes get their canonical form computed here. Their old hash,
   and the old hash in acceptances and rejections that cite it, is kept in
   an audit row.
2. ``quote_offer`` records each time a quote was put before the client and
   through which channel.
3. ``assignment.traffic_form`` goes away: how a quote reaches the client is
   chosen per offer. What remains is the fact that an assignment is shared
   with another instance, which arises from an exchange.

Revision ID: 0009_quote_canonical
Revises: 0008_grist_import_ref
Create Date: 2026-10-08

"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

import rfc8785
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_quote_canonical"
down_revision: str | None = "0008_grist_import_ref"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The terms of a quote's content as they were when this migration was
# written. Frozen here on purpose: a migration must give the same result
# whenever it runs, whatever the mapping in the application says by then.
_KEYS = {
    "name": "naam",
    "context_refs": "context_uris",
    "lines": "regels",
    "position": "positie",
    "description": "omschrijving",
    "kind": "soort",
    "role": "rol",
    "rate_category": "tariefcategorie",
    "period": "periode",
    "start_date": "begindatum",
    "end_date": "einddatum",
    "monthly_rate": "maandtarief",
    "monthly_rates_per_year": "maandtarieven_per_jaar",
    "year": "jaar",
    "amount": "bedrag",
    "amount_cents": "bedrag_centen",
    "currency": "valuta",
    "subtotals_per_year": "subtotalen_per_jaar",
    "total": "totaal",
    "valid_until": "geldig_tot_en_met",
    "conditions": "voorwaarden",
}
_KINDS = {"personnel": "personeel", "fixed": "vast"}
_KEYS_BACK = {term: name for name, term in _KEYS.items()}
_KINDS_BACK = {term: name for name, term in _KINDS.items()}


def _translate(
    value: Any, keys: dict[str, str], kinds: dict[str, str], kind_key: str
) -> Any:
    if isinstance(value, dict):
        result = {}
        for name, item in value.items():
            if name == kind_key and isinstance(item, str):
                item = kinds.get(item, item)
            result[keys.get(name, name)] = _translate(item, keys, kinds, kind_key)
        return result
    if isinstance(value, list):
        return [_translate(item, keys, kinds, kind_key) for item in value]
    return value


def _audit(connection: sa.Connection, entity: str, entity_id: Any, old: Any, new: Any):
    connection.execute(
        sa.text(
            "INSERT INTO audit_log (action, entity, entity_id, old_value, new_value) "
            "VALUES ('update', :entity, :entity_id, "
            "CAST(:old AS jsonb), CAST(:new AS jsonb))"
        ),
        {
            "entity": entity,
            "entity_id": str(entity_id),
            "old": json.dumps(old),
            "new": json.dumps(new),
        },
    )


def _canonicalise_quotes(connection: sa.Connection) -> None:
    rows = connection.execute(
        sa.text("SELECT id, snapshot, snapshot_hash FROM quote")
    ).all()
    reason = "0009: one canonical form and one hash per quote"
    for quote_id, snapshot, old_hash in rows:
        contract = _translate(snapshot or {}, _KEYS, _KINDS, "kind")
        canonical = rfc8785.dumps(contract)
        new_hash = hashlib.sha256(canonical).hexdigest()
        connection.execute(
            sa.text(
                "UPDATE quote SET canonical = :canonical, snapshot_hash = :hash "
                "WHERE id = :id"
            ),
            {"canonical": canonical, "hash": new_hash, "id": quote_id},
        )
        if new_hash == old_hash:
            continue
        _audit(
            connection,
            "quote",
            quote_id,
            {"snapshot_hash": old_hash},
            {"snapshot_hash": new_hash, "reason": reason},
        )
        # A decision cites the hash of the quote it is about. One that cited
        # the old value follows the quote; one that cited something else is
        # left alone.
        for table, entity in (
            ("quote_acceptance", "quote_acceptance"),
            ("quote_rejection", "quote_rejection"),
        ):
            cited = connection.execute(
                sa.text(
                    f"UPDATE {table} SET quote_hash = :new "  # noqa: S608
                    "WHERE quote_id = :id AND quote_hash = :old RETURNING id"
                ),
                {"new": new_hash, "old": old_hash, "id": quote_id},
            ).all()
            for (row_id,) in cited:
                _audit(
                    connection,
                    entity,
                    row_id,
                    {"quote_hash": old_hash},
                    {"quote_hash": new_hash, "reason": reason},
                )


def _share_assignments(connection: sa.Connection) -> None:
    """What was "federated" becomes "shared with the other party's instance"."""
    from grip.core.config import get_settings

    own = get_settings().INSTANCE_BASE_URI.strip().rstrip("/")
    rows = connection.execute(
        sa.text(
            "SELECT a.id, a.traffic_form, c.instance_uri, k.instance_uri "
            "FROM assignment a "
            "LEFT JOIN organisation c ON c.id = a.client_organisation_id "
            "LEFT JOIN organisation k ON k.id = a.contractor_organisation_id "
            "WHERE a.traffic_form <> 'none'"
        )
    ).all()
    for assignment_id, traffic_form, client_uri, contractor_uri in rows:
        shared = None
        if traffic_form == "federated":
            others = [
                uri.strip().rstrip("/")
                for uri in (client_uri, contractor_uri)
                if uri and uri.strip().rstrip("/") != own
            ]
            shared = others[0] if others else None
            if shared is not None:
                connection.execute(
                    sa.text(
                        "UPDATE assignment SET shared_with_instance_uri = :uri, "
                        "shared_at = created_at WHERE id = :id"
                    ),
                    {"uri": shared, "id": assignment_id},
                )
        _audit(
            connection,
            "assignment",
            assignment_id,
            {"traffic_form": traffic_form},
            {
                "shared_with_instance_uri": shared,
                "reason": "0009: channel is chosen per offer of a quote",
            },
        )


def upgrade() -> None:
    connection = op.get_bind()

    # 1. Canonical form and hash.
    op.add_column("quote", sa.Column("canonical", sa.LargeBinary(), nullable=True))
    _canonicalise_quotes(connection)
    op.alter_column("quote", "canonical", nullable=False)
    op.drop_column("quote", "snapshot")
    op.create_check_constraint(
        op.f("ck_quote_hash_of_canonical"),
        "quote",
        "snapshot_hash = encode(sha256(canonical), 'hex')",
    )

    # 2. Offers.
    op.create_table(
        "quote_offer",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("recipient", sa.String(length=500), nullable=True),
        sa.Column("invitation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("offered_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "channel IN ('client_instance', 'signing_link', 'document')",
            name=op.f("ck_quote_offer_channel_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quote.id"],
            name=op.f("fk_quote_offer_quote_id_quote"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invitation_id"],
            ["quote_invitation.id"],
            name=op.f("fk_quote_offer_invitation_id_quote_invitation"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["offered_by_id"],
            ["person.id"],
            name=op.f("fk_quote_offer_offered_by_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quote_offer")),
    )
    op.create_index(
        "ix_quote_offer_quote", "quote_offer", ["quote_id", "offered_at"], unique=False
    )
    # An invitation that exists was an offer through the signing link.
    connection.execute(
        sa.text(
            "INSERT INTO quote_offer "
            "(quote_id, channel, recipient, invitation_id, offered_at, offered_by_id) "
            "SELECT quote_id, 'signing_link', email, id, created_at, invited_by_id "
            "FROM quote_invitation"
        )
    )

    # 3. No traffic form; the shared-with fact instead.
    op.add_column(
        "assignment",
        sa.Column("shared_with_instance_uri", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "assignment",
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
    )
    _share_assignments(connection)
    op.drop_constraint(
        op.f("ck_assignment_traffic_form_valid"), "assignment", type_="check"
    )
    op.drop_column("assignment", "traffic_form")


def downgrade() -> None:
    """Back to the previous shape. The old hashes are not restored: they are
    in the audit log, and a quote keeps the hash of its canonical form."""
    connection = op.get_bind()

    op.add_column(
        "assignment",
        sa.Column(
            "traffic_form", sa.String(length=10), server_default="none", nullable=False
        ),
    )
    connection.execute(
        sa.text(
            "UPDATE assignment SET traffic_form = 'federated' "
            "WHERE shared_with_instance_uri IS NOT NULL"
        )
    )
    op.create_check_constraint(
        op.f("ck_assignment_traffic_form_valid"),
        "assignment",
        "traffic_form IN ('federated', 'document', 'none')",
    )
    op.drop_column("assignment", "shared_at")
    op.drop_column("assignment", "shared_with_instance_uri")

    op.drop_index("ix_quote_offer_quote", table_name="quote_offer")
    op.drop_table("quote_offer")

    op.drop_constraint(op.f("ck_quote_hash_of_canonical"), "quote", type_="check")
    op.add_column(
        "quote",
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    rows = connection.execute(sa.text("SELECT id, canonical FROM quote")).all()
    for quote_id, canonical in rows:
        snapshot = _translate(
            json.loads(bytes(canonical)), _KEYS_BACK, _KINDS_BACK, "soort"
        )
        connection.execute(
            sa.text(
                "UPDATE quote SET snapshot = CAST(:snapshot AS jsonb) WHERE id = :id"
            ),
            {"snapshot": json.dumps(snapshot), "id": quote_id},
        )
    op.alter_column("quote", "snapshot", nullable=False)
    op.drop_column("quote", "canonical")
