"""One stream of events; the audit log becomes a view of it.

Revision ID: 0026_event_stream
Revises: 0025_decision_proof
Create Date: 2026-10-08

"""

import hashlib
import json
import secrets
from collections.abc import Sequence
from datetime import UTC

import rfc8785
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_event_stream"
down_revision: str | None = "0025_decision_proof"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Everything below is kept literal: a migration must not change when the
# application code does. This is version 1 of the canonical form of
# ``grip.events.chain``.
_GENESIS = "0" * 64
_VERBS = {"create": "created", "update": "updated", "delete": "deleted"}

_A, _B, _C = "assignment_basic", "assignment_financial", "staffing"
_D, _E, _F = "person_rate", "person_cost", "person_kpi"
_COUNTS = "staffing_counts"

# entity -> (who may know it happened, class of the values).
_CLASSES: dict[str, tuple[str | None, str | None]] = {
    "assignment": (_A, _A),
    "assignment_request": (_A, _A),
    "assignment_role": (_A, _A),
    "task": (_A, _A),
    "budget_line": (_A, _B),
    "budget_usage_requested": (_A, _B),
    "quote": (_A, _B),
    "quote_offer": (_A, _B),
    "quote_invitation": (_A, _B),
    "quote_acceptance": (_A, _B),
    "quote_rejection": (_A, _B),
    "quote_approval": (_A, _B),
    "final_report": (_A, _B),
    "final_report_received": (_A, _B),
    "month_close": (_B, _B),
    "billing_export": (_B, _B),
    "outgoing_invoice": (_B, _B),
    "invoice_line": (_B, _B),
    "invoice_attachment": (_B, _B),
    "cost_item": (_B, _B),
    "cost_coverage": (_B, _B),
    "allocation": (_C, _C),
    "person": (_C, _C),
    "person_standing": (_C, _C),
    "person_role": (_C, _C),
    "person_roles": (_C, _C),
    "colleague_proposal": (_C, _C),
    "person_scale": (_C, _D),
    "hire": (_C, _E),
    "billability_target": (_F, _F),
    "vacancy": (_COUNTS, _C),
    "vacancy_text": (_COUNTS, _C),
    "vacancy_decision": (_COUNTS, _C),
    "vacancy_recruitment_ref": (_COUNTS, _C),
    "vacancy_offer_received": (_COUNTS, _C),
    "vacancy_hire": (_COUNTS, _C),
}
_FIELDS: dict[str, dict[str, str]] = {
    "budget_line": {"intended_person_id": _C},
    "allocation": {
        "billing_scale": _D,
        "scale": _D,
        "rate_category": _D,
        "rate_cents": _D,
        "hourly_rate_cents": _D,
        "amount_cents": _D,
        "cost_rate_cents": _E,
        "cost_cents": _E,
        "margin_cents": _E,
    },
}


def _canonical(value) -> bytes:
    try:
        return rfc8785.dumps(value)
    except Exception:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()


def _digest(salt: str, value) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(salt.encode() + b"\x00" + _canonical(value)).hexdigest()


def _text(value) -> str | None:
    return None if value is None else str(value)


def _hash(event: dict) -> str:
    form = {
        "v": 1,
        "seq": str(event["seq"]),
        "id": str(event["id"]),
        "occurred_at": event["occurred_at"]
        .astimezone(UTC)
        .isoformat(timespec="microseconds"),
        "type": event["type"],
        "action": event["action"],
        "subject": [event["subject_kind"], event["subject_id"]],
        "case": [event["case_kind"], _text(event["case_id"])],
        "person": _text(event["person_id"]),
        "actor": [
            event["actor_kind"],
            _text(event["actor_person_id"]),
            event["actor_ref"],
        ],
        "origin": [event["origin"], event["origin_peer"]],
        "correlation": event["correlation_id"],
        "purpose": event["purpose"],
        "classes": [event["existence_class"], event["field_classes"] or {}],
        "refs": event["refs"],
        "digests": [
            event["old_digest"],
            event["new_digest"],
            event["payload_digest"],
            event["note_digest"],
        ],
        "prev": event["prev_hash"],
    }
    return hashlib.sha256(_canonical(form)).hexdigest()


def _create_table() -> sa.Table:
    return op.create_table(
        "stream_event",
        sa.Column("seq", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=True),
        sa.Column("subject_kind", sa.String(length=100), nullable=False),
        sa.Column("subject_id", sa.String(length=100), nullable=False),
        sa.Column("case_kind", sa.String(length=20), nullable=True),
        sa.Column("case_id", sa.UUID(), nullable=True),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("actor_kind", sa.String(length=20), nullable=False),
        sa.Column("actor_person_id", sa.UUID(), nullable=True),
        sa.Column("actor_ref", sa.String(length=200), nullable=True),
        sa.Column("origin", sa.String(length=10), nullable=False),
        sa.Column("origin_peer", sa.String(length=200), nullable=True),
        sa.Column("correlation_id", sa.String(length=32), nullable=False),
        sa.Column("purpose", sa.String(length=200), nullable=True),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("refs", postgresql.JSONB(), nullable=True),
        sa.Column("existence_class", sa.String(length=40), nullable=True),
        sa.Column("field_classes", postgresql.JSONB(), nullable=False),
        sa.Column("salt", sa.String(length=32), nullable=True),
        sa.Column("old_digest", sa.String(length=64), nullable=True),
        sa.Column("new_digest", sa.String(length=64), nullable=True),
        sa.Column("payload_digest", sa.String(length=64), nullable=True),
        sa.Column("note_digest", sa.String(length=64), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("seq", name=op.f("pk_stream_event")),
        sa.UniqueConstraint("id", name=op.f("uq_stream_event_id")),
    )


def _uuid_text(value) -> str | None:
    text = str(value) if value else ""
    return text if len(text) == 36 and text.count("-") == 4 else None


def _case_lookups(bind) -> dict[str, dict[str, dict[str, str]]]:
    """Per table that is also an entity: row id -> the case and person it names."""
    columns = bind.execute(
        sa.text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND column_name IN "
            "('id', 'assignment_id', 'vacancy_id', 'person_id', 'budget_line_id', "
            "'quote_id')"
        )
    ).all()
    by_table: dict[str, set[str]] = {}
    for table, column in columns:
        by_table.setdefault(table, set()).add(column)
    lookups: dict[str, dict[str, dict[str, str]]] = {}
    for table, names in by_table.items():
        wanted = sorted(names - {"id"})
        if "id" not in names or not wanted or table in ("audit_log", "stream_event"):
            continue
        rows = bind.execute(
            sa.text(f'SELECT id::text, {", ".join(wanted)} FROM "{table}"')  # noqa: S608
        ).all()
        lookups[table] = {
            row[0]: {
                name: str(value)
                for name, value in zip(wanted, row[1:], strict=True)
                if value is not None
            }
            for row in rows
        }
    return lookups


def _resolve(entity, entity_id, values, lookups):
    found: dict[str, str] = {}
    for value in values:
        if isinstance(value, dict):
            for name in ("assignment_id", "vacancy_id", "person_id"):
                if _uuid_text(value.get(name)):
                    found.setdefault(name, str(value[name]))
            for name in ("budget_line_id", "quote_id"):
                if _uuid_text(value.get(name)):
                    found.setdefault(name, str(value[name]))
    for name, value in lookups.get(entity, {}).get(entity_id, {}).items():
        found.setdefault(name, value)
    if entity == "assignment":
        found.setdefault("assignment_id", entity_id)
    elif entity == "vacancy":
        found.setdefault("vacancy_id", entity_id)
    elif entity == "person" or (
        entity.startswith("person") and entity_id in lookups.get("person_ids", {})
    ):
        found.setdefault("person_id", entity_id)
    for name, table in (("budget_line_id", "budget_line"), ("quote_id", "quote")):
        if "assignment_id" not in found and name in found:
            linked = lookups.get(table, {}).get(found[name], {})
            if "assignment_id" in linked:
                found["assignment_id"] = linked["assignment_id"]
    if "vacancy_id" in found and (
        entity.startswith("vacancy") or "assignment_id" not in found
    ):
        case = ("vacancy", _uuid_text(found["vacancy_id"]))
    elif "assignment_id" in found:
        case = ("assignment", _uuid_text(found["assignment_id"]))
    else:
        case = (None, None)
    if case[1] is None:
        case = (None, None)
    return case, _uuid_text(found.get("person_id"))


def upgrade() -> None:
    table = _create_table()
    op.create_index(
        op.f("ix_stream_event_occurred_at"), "stream_event", ["occurred_at"]
    )
    op.create_index(op.f("ix_stream_event_type"), "stream_event", ["type"])
    op.create_index(
        op.f("ix_stream_event_correlation_id"), "stream_event", ["correlation_id"]
    )
    op.create_index(
        "ix_stream_event_subject", "stream_event", ["subject_kind", "subject_id"]
    )
    op.create_index(
        "ix_stream_event_case", "stream_event", ["case_kind", "case_id", "seq"]
    )
    op.create_index("ix_stream_event_person", "stream_event", ["person_id", "seq"])
    op.create_index("ix_stream_event_actor", "stream_event", ["actor_person_id", "seq"])

    bind = op.get_bind()
    lookups = _case_lookups(bind)
    lookups["person_ids"] = {
        row[0]: {} for row in bind.execute(sa.text("SELECT id::text FROM person"))
    }
    rows = bind.execute(
        sa.text(
            "SELECT id, occurred_at, actor_id, action, entity, entity_id, "
            "old_value, new_value FROM audit_log ORDER BY occurred_at, id"
        )
    ).mappings()
    prev = _GENESIS
    batch: list[dict] = []
    seq = 0
    for row in rows:
        seq += 1
        entity, entity_id = row["entity"], row["entity_id"]
        existence, values_class = _CLASSES.get(entity, (None, None))
        field_classes: dict[str, str | None] = {"*": values_class}
        for value in (row["old_value"], row["new_value"]):
            for key in value or {}:
                if key in _FIELDS.get(entity, {}):
                    field_classes[key] = _FIELDS[entity][key]
        (case_kind, case_id), person_id = _resolve(
            entity, entity_id, (row["new_value"], row["old_value"]), lookups
        )
        salt = secrets.token_hex(16)
        event = {
            "seq": seq,
            "id": row["id"],
            "occurred_at": row["occurred_at"],
            "type": f"{entity}.{_VERBS.get(row['action'], row['action'])}",
            "action": row["action"],
            "subject_kind": entity,
            "subject_id": entity_id,
            "case_kind": case_kind,
            "case_id": case_id,
            "person_id": person_id,
            "actor_kind": "person" if row["actor_id"] else "system",
            "actor_person_id": row["actor_id"],
            "actor_ref": None if row["actor_id"] else "system",
            "origin": "local",
            "origin_peer": None,
            # Audit rows of one transaction shared their time.
            "correlation_id": hashlib.md5(  # noqa: S324
                row["occurred_at"].isoformat().encode()
            ).hexdigest(),
            "purpose": None,
            "old_value": row["old_value"],
            "new_value": row["new_value"],
            "payload": None,
            "note": None,
            "refs": None,
            "existence_class": existence,
            "field_classes": field_classes,
            "salt": salt,
            "old_digest": _digest(salt, row["old_value"]),
            "new_digest": _digest(salt, row["new_value"]),
            "payload_digest": None,
            "note_digest": None,
            "prev_hash": prev,
            "erased_at": None,
        }
        event["hash"] = prev = _hash(event)
        batch.append(event)
        if len(batch) >= 500:
            op.bulk_insert(table, batch)
            batch = []
    if batch:
        op.bulk_insert(table, batch)

    op.drop_table("audit_log")

    # Append-only, enforced by the database: a row is never removed, and
    # the only change allowed is erasing its values.
    op.execute(
        """
        CREATE FUNCTION stream_event_guard() RETURNS trigger AS $$
        DECLARE
            erasable text[] := ARRAY[
                'old_value', 'new_value', 'payload', 'note', 'salt', 'erased_at'
            ];
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'stream_event is append-only: no delete';
            END IF;
            IF NEW.old_value IS NOT NULL OR NEW.new_value IS NOT NULL
                OR NEW.payload IS NOT NULL OR NEW.note IS NOT NULL
                OR NEW.salt IS NOT NULL OR NEW.erased_at IS NULL
                OR (to_jsonb(NEW) - erasable)
                    IS DISTINCT FROM (to_jsonb(OLD) - erasable)
            THEN
                RAISE EXCEPTION
                    'stream_event is append-only: only erasing values is allowed';
            END IF;
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER stream_event_guard BEFORE UPDATE OR DELETE ON stream_event "
        "FOR EACH ROW EXECUTE FUNCTION stream_event_guard()"
    )


def downgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("entity", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["person.id"],
            name=op.f("fk_audit_log_actor_id_person"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_occurred_at"), "audit_log", ["occurred_at"])
    op.create_index(op.f("ix_audit_log_actor_id"), "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_entity", "audit_log", ["entity", "entity_id"])
    # Only plain change records were audit rows. An actor that no longer
    # exists becomes the system, as the foreign key would have made it.
    op.execute(
        "INSERT INTO audit_log (id, occurred_at, actor_id, action, entity, "
        "entity_id, old_value, new_value) "
        "SELECT e.id, e.occurred_at, p.id, e.action, e.subject_kind, e.subject_id, "
        "e.old_value, e.new_value FROM stream_event e "
        "LEFT JOIN person p ON p.id = e.actor_person_id "
        "WHERE e.action IS NOT NULL ORDER BY e.seq"
    )
    op.drop_table("stream_event")
    op.execute("DROP FUNCTION stream_event_guard()")
