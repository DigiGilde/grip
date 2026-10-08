"""Migration 0009 on a database that already holds quotes and assignments.

It must not assume an empty table: an existing quote gets its canonical form
and its new hash, the old hash is kept in the audit log, a decision that
cited the old hash follows the quote, an invitation becomes an offer, and
"federated" becomes "shared with the other party's instance".
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import rfc8785
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from grip.core.config import get_settings
from grip.services import canonical

BACKEND = Path(__file__).resolve().parents[2]
CLIENT_INSTANCE = "https://grip.opdrachtgever.example"

SNAPSHOT = {
    "name": "Opdracht Alfa",
    "context_refs": ["https://corpus.voorbeeldministerie.example/id/node/1"],
    "lines": [
        {
            "position": 1,
            "description": "Productmanager",
            "kind": "personnel",
            "role": "Productmanager",
            "fte": "0.8",
            "rate_category": "D",
            "period": {"start_date": "2026-07-01", "end_date": "2027-06-30"},
            "monthly_rates_per_year": [
                {
                    "year": 2026,
                    "monthly_rate": {"amount_cents": 1800000, "currency": "EUR"},
                },
                {
                    "year": 2027,
                    "monthly_rate": {"amount_cents": 1890000, "currency": "EUR"},
                },
            ],
            "amount": {"amount_cents": 17712000, "currency": "EUR"},
        },
        {
            "position": 2,
            "description": "Hosting",
            "kind": "fixed",
            "year": 2026,
            "amount": {"amount_cents": 1500000, "currency": "EUR"},
        },
    ],
    "subtotals_per_year": [
        {"year": 2026, "amount": {"amount_cents": 10140000, "currency": "EUR"}},
        {"year": 2027, "amount": {"amount_cents": 9072000, "currency": "EUR"}},
    ],
    "total": {"amount_cents": 19212000, "currency": "EUR"},
    "valid_until": "2026-06-30",
    "conditions": "Fictieve voorwaarden.",
}
OLD_HASH = hashlib.sha256(rfc8785.dumps(SNAPSHOT)).hexdigest()


def _alembic(env: dict[str, str], *args: str) -> None:
    result = subprocess.run(  # noqa: S603 - fixed command, own interpreter
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


async def test_existing_rows_get_canonical_form_offers_and_sharing():
    url = make_url(get_settings().DATABASE_URL)
    scratch = f"grip_mig_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{scratch}"'))
    scratch_url = url.set(database=scratch)
    env = {
        **os.environ,
        "DEV_NO_AUTH": "1",
        "DATABASE_URL": scratch_url.render_as_string(hide_password=False),
    }
    engine = create_async_engine(scratch_url)
    try:
        _alembic(env, "upgrade", "0008_grist_import_ref")
        ids = {
            name: str(uuid.uuid4()) for name in ("org", "a1", "a2", "q", "acc", "inv")
        }
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO organisation (id, name, instance_uri) "
                    "VALUES (:id, 'Voorbeeldministerie', :uri)"
                ),
                {"id": ids["org"], "uri": CLIENT_INSTANCE + "/"},
            )
            for key, form in (("a1", "federated"), ("a2", "document")):
                await conn.execute(
                    text(
                        "INSERT INTO assignment (id, uri, name, traffic_form, "
                        "client_organisation_id, context_refs) VALUES "
                        "(:id, :uri, 'Opdracht', :form, :org, '[]'::jsonb)"
                    ),
                    {
                        "id": ids[key],
                        "uri": f"https://x.example/id/opdracht/{ids[key]}",
                        "form": form,
                        "org": ids["org"],
                    },
                )
            await conn.execute(
                text(
                    "INSERT INTO quote (id, uri, assignment_id, snapshot, "
                    "snapshot_hash, total_cents, issued_at) VALUES (:id, :uri, :a, "
                    "CAST(:snapshot AS jsonb), :hash, 19212000, now())"
                ),
                {
                    "id": ids["q"],
                    "uri": f"https://x.example/id/offerte/{ids['q']}",
                    "a": ids["a1"],
                    "snapshot": json.dumps(SNAPSHOT),
                    "hash": OLD_HASH,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO quote_acceptance (id, quote_id, quote_hash, "
                    "signer_name, signer_email, organisation, signed_at, form, "
                    "document_sha256) VALUES (:id, :q, :hash, 'Directeur', "
                    "'d@klant.example', '{}'::jsonb, now(), 'uploaded_pdf', :doc)"
                ),
                {
                    "id": ids["acc"],
                    "q": ids["q"],
                    "hash": OLD_HASH,
                    "doc": "a" * 64,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO quote_invitation (id, quote_id, email) "
                    "VALUES (:id, :q, 'tekenaar@klant.example')"
                ),
                {"id": ids["inv"], "q": ids["q"]},
            )

        _alembic(env, "upgrade", "0009_quote_canonical")

        async with engine.connect() as conn:
            stored, new_hash = (
                await conn.execute(
                    text("SELECT canonical, snapshot_hash FROM quote WHERE id = :id"),
                    {"id": ids["q"]},
                )
            ).one()
            stored = bytes(stored)
            # The canonical form is the contract form, and reads back as the
            # content the quote had, two rate years and all.
            assert new_hash == hashlib.sha256(stored).hexdigest() != OLD_HASH
            contract = json.loads(stored)
            assert contract["regels"][0]["maandtarieven_per_jaar"][1]["jaar"] == 2027
            assert contract["regels"][1]["soort"] == "vast"
            assert canonical.read(stored) == SNAPSHOT
            assert stored == canonical.canonical_form(SNAPSHOT)

            columns = set(
                (
                    await conn.execute(
                        text(
                            "SELECT table_name || '.' || column_name "
                            "FROM information_schema.columns "
                            "WHERE table_name IN ('quote', 'assignment')"
                        )
                    )
                ).scalars()
            )
            assert "quote.snapshot" not in columns
            assert "assignment.traffic_form" not in columns

            cited = await conn.scalar(
                text("SELECT quote_hash FROM quote_acceptance WHERE id = :id"),
                {"id": ids["acc"]},
            )
            assert cited == new_hash
            audit = (
                await conn.execute(
                    text(
                        "SELECT entity, entity_id, old_value, new_value "
                        "FROM audit_log ORDER BY entity"
                    )
                )
            ).all()
            kept = {(row[0], row[1]): (row[2], row[3]) for row in audit}
            assert kept[("quote", ids["q"])][0] == {"snapshot_hash": OLD_HASH}
            assert kept[("quote", ids["q"])][1]["snapshot_hash"] == new_hash
            assert kept[("quote_acceptance", ids["acc"])][0] == {"quote_hash": OLD_HASH}
            assert kept[("assignment", ids["a1"])][0] == {"traffic_form": "federated"}
            assert kept[("assignment", ids["a2"])][0] == {"traffic_form": "document"}

            offers = (
                await conn.execute(
                    text("SELECT channel, recipient, invitation_id FROM quote_offer")
                )
            ).all()
            assert [(o[0], o[1], str(o[2])) for o in offers] == [
                ("signing_link", "tekenaar@klant.example", ids["inv"])
            ]
            shared = dict(
                (
                    await conn.execute(
                        text("SELECT id, shared_with_instance_uri FROM assignment")
                    )
                ).all()
            )
            assert shared[uuid.UUID(ids["a1"])] == CLIENT_INSTANCE
            assert shared[uuid.UUID(ids["a2"])] is None

        # The way back keeps the content readable.
        _alembic(env, "downgrade", "0008_grist_import_ref")
        async with engine.connect() as conn:
            snapshot = await conn.scalar(
                text("SELECT snapshot FROM quote WHERE id = :id"), {"id": ids["q"]}
            )
            assert snapshot == SNAPSHOT
            form = await conn.scalar(
                text("SELECT traffic_form FROM assignment WHERE id = :id"),
                {"id": ids["a1"]},
            )
            assert form == "federated"
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(
                text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
            )
        await admin.dispose()
