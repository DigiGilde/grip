"""Migration 0022: year cards become cards with a validity, up and down."""

# The rows are SQL, one statement per line.
# ruff: noqa: E501

import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from grip.core.config import get_settings

BACKEND = Path(__file__).resolve().parents[2]

_ROWS = """
INSERT INTO rate_card (year, status) VALUES (2025, 'closed'), (2026, 'active'), (2027, 'draft');
INSERT INTO rate_band (year, category, monthly_rate_cents) VALUES (2025, 'D', 1700000), (2026, 'C', 1500000), (2026, 'D', 1800000), (2027, 'D', 1890000);
INSERT INTO scale_band (year, scale, category) VALUES (2026, 14, 'D'), (2026, 12, 'C'), (2027, 14, 'D');
INSERT INTO audit_log (action, entity, entity_id, new_value) VALUES ('create', 'rate_card', '2026', '{"year": 2026}'), ('update', 'rate_band', '2026/D', '{"monthly_rate_cents": 1800000}'), ('update', 'scale_band', '2026/14', '{"category": "D"}'), ('create', 'assignment', '2026', '{}')
"""


async def test_year_cards_become_cards_with_a_validity_and_back():
    url = make_url(get_settings().DATABASE_URL)
    scratch = f"grip_mig_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{scratch}"'))
    env = {
        **os.environ,
        "DEV_NO_AUTH": "1",
        "DATABASE_URL": url.set(database=scratch).render_as_string(hide_password=False),
    }

    def alembic(*args, ok=True):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
        )
        assert (result.returncode == 0) is ok, result.stderr
        return result

    async def rows(sql):
        engine = create_async_engine(url.set(database=scratch))
        async with engine.connect() as conn:
            found = (await conn.execute(text(sql))).all()
        await engine.dispose()
        return [tuple(row) for row in found]

    async def run(sql):
        engine = create_async_engine(url.set(database=scratch))
        async with engine.begin() as conn:
            for statement in sql.split(";"):
                if statement.strip():
                    await conn.execute(text(statement))
        await engine.dispose()

    try:
        alembic("upgrade", "0021_quote_reference")
        await run(_ROWS)

        alembic("upgrade", "0022_rate_card_validity")

        cards = await rows(
            "SELECT name, valid_from, valid_to, status FROM rate_card ORDER BY valid_from"
        )
        assert cards == [
            ("Tarieven 2025", date(2025, 1, 1), date(2025, 12, 31), "closed"),
            ("Tarieven 2026", date(2026, 1, 1), date(2026, 12, 31), "active"),
            ("Tarieven 2027", date(2027, 1, 1), date(2027, 12, 31), "draft"),
        ]
        # Rates and the scale mapping are re-keyed to their card.
        bands = await rows(
            "SELECT card.name, band.category, band.monthly_rate_cents "
            "FROM rate_band band JOIN rate_card card ON card.id = band.rate_card_id "
            "ORDER BY card.valid_from, band.category"
        )
        assert bands == [
            ("Tarieven 2025", "D", 1700000),
            ("Tarieven 2026", "C", 1500000),
            ("Tarieven 2026", "D", 1800000),
            ("Tarieven 2027", "D", 1890000),
        ]
        scales = await rows(
            "SELECT card.name, band.scale, band.category FROM scale_band band "
            "JOIN rate_card card ON card.id = band.rate_card_id "
            "ORDER BY card.valid_from, band.scale"
        )
        assert scales == [
            ("Tarieven 2026", 12, "C"),
            ("Tarieven 2026", 14, "D"),
            ("Tarieven 2027", 14, "D"),
        ]
        # Audit rows that named a card by its year name it by its id; rows of
        # other entities are left alone.
        ((card_id,),) = await rows(
            "SELECT id::text FROM rate_card WHERE name = 'Tarieven 2026'"
        )
        audit = dict(await rows("SELECT entity, entity_id FROM audit_log"))
        assert audit == {
            "rate_card": card_id,
            "rate_band": f"{card_id}/D",
            "scale_band": f"{card_id}/14",
            "assignment": "2026",
        }
        # A card can now start on any day, and two cards that price cannot
        # overlap.
        await run(
            "INSERT INTO rate_card (name, valid_from, status) "
            "VALUES ('Concept halverwege', '2026-07-15', 'draft')"
        )
        overlap = None
        try:
            await run(
                "INSERT INTO rate_card (name, valid_from, status) "
                "VALUES ('Overlap', '2026-07-15', 'active')"
            )
        except Exception as exc:  # noqa: BLE001
            overlap = exc
        assert overlap is not None and "ex_rate_card_no_overlap" in str(overlap)

        # Down: refused while a card does not span one calendar year ...
        refused = alembic("downgrade", "0021_quote_reference", ok=False)
        assert "do not span exactly one" in refused.stderr
        await run("DELETE FROM rate_card WHERE name = 'Concept halverwege'")
        # ... and then back to what it was.
        alembic("downgrade", "0021_quote_reference")
        assert await rows("SELECT year, status FROM rate_card ORDER BY year") == [
            (2025, "closed"),
            (2026, "active"),
            (2027, "draft"),
        ]
        assert await rows(
            "SELECT year, category, monthly_rate_cents FROM rate_band ORDER BY year, category"
        ) == [
            (2025, "D", 1700000),
            (2026, "C", 1500000),
            (2026, "D", 1800000),
            (2027, "D", 1890000),
        ]
        assert dict(await rows("SELECT entity, entity_id FROM audit_log")) == {
            "rate_card": "2026",
            "rate_band": "2026/D",
            "scale_band": "2026/14",
            "assignment": "2026",
        }
        alembic("upgrade", "0022_rate_card_validity")
    finally:
        async with admin.connect() as conn:
            await conn.execute(
                text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
            )
        await admin.dispose()
