"""Fixtures for the tests of the event stream.

Tests that need a real commit (handlers after commit, concurrent writers,
the migration of audit rows) run on a database of their own that is made
for the test run and dropped afterwards, because the stream is append-only
and a committed event can never be taken out again.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from grip.core.config import get_settings
from grip.events import stream
from tests.api.assignments.conftest import as_person, world  # noqa: F401

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _no_stream_handlers():
    stream.clear_handlers()
    yield
    stream.clear_handlers()


def alembic(url: str, *args: str) -> None:
    subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": url, "DEV_NO_AUTH": "1"},
        check=True,
        capture_output=True,
    )


async def _admin(url) -> asyncpg.Connection:
    return await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=url.database,
    )


@pytest.fixture(scope="session")
def own_database_url():
    """The URL of a fresh, empty database; dropped after the run."""
    import asyncio

    base = make_url(get_settings().DATABASE_URL)
    name = f"grip_events_{uuid.uuid4().hex[:10]}"

    async def _run(statement: str) -> None:
        connection = await _admin(base)
        try:
            await connection.execute(statement)
        finally:
            await connection.close()

    asyncio.run(_run(f'CREATE DATABASE "{name}"'))
    yield base.set(database=name).render_as_string(hide_password=False)
    asyncio.run(_run(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture(scope="session")
def migrated_database_url(own_database_url):
    """The own database at 0025 with audit rows, then migrated to head.

    Returns the URL and the audit rows that were there before the stream.
    """
    import asyncio

    alembic(own_database_url, "upgrade", "0025_decision_proof")
    url = make_url(own_database_url)
    person_id, assignment_id = uuid.uuid4(), uuid.uuid4()

    async def _seed() -> list[dict]:
        connection = await _admin(url)
        try:
            await connection.execute(
                "INSERT INTO person (id, name, email) VALUES ($1, 'Test Persoon', "
                "'persoon@example.org')",
                person_id,
            )
            rows = [
                ("create", "assignment", str(assignment_id), None, '{"name": "Alfa"}'),
                (
                    "update",
                    "assignment",
                    str(assignment_id),
                    '{"status": "draft"}',
                    '{"status": "active"}',
                ),
                (
                    "update",
                    "person_scale",
                    str(uuid.uuid4()),
                    '{"billing_scale": 11}',
                    f'{{"billing_scale": 12, "person_id": "{person_id}"}}',
                ),
                ("update", "rate_card", "2026", None, '{"status": "active"}'),
            ]
            for index, (action, entity, entity_id, old, new) in enumerate(rows):
                await connection.execute(
                    "INSERT INTO audit_log (occurred_at, actor_id, action, entity, "
                    "entity_id, old_value, new_value) VALUES (now() + $1 * interval "
                    "'1 second', $2, $3, $4, $5, $6::jsonb, $7::jsonb)",
                    index,
                    person_id if index != 3 else None,
                    action,
                    entity,
                    entity_id,
                    old,
                    new,
                )
            found = await connection.fetch(
                "SELECT id, occurred_at, actor_id, action, entity, entity_id, "
                "old_value::text, new_value::text FROM audit_log "
                "ORDER BY occurred_at, id"
            )
            return [dict(row) for row in found]
        finally:
            await connection.close()

    before = asyncio.run(_seed())
    alembic(own_database_url, "upgrade", "head")
    return own_database_url, before, person_id, assignment_id


@pytest.fixture
async def committing(migrated_database_url):
    """A session factory on the own database: commits are real."""
    engine = create_async_engine(migrated_database_url[0], poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
