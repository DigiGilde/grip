"""The read-only check of every read model against its chronicle.

All names are fictional.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from grip.chronicle.check import check
from grip.chronicle.verify import differences
from grip.core.config import Settings, get_settings
from grip.dev.seed import SeedRefusedError, ensure_local_instance
from grip.models.assignment import Assignment
from grip.services import assignments

BACKEND = Path(__file__).resolve().parents[2]
# What an instance configured for real work looks like.
REAL_INSTANCE = {
    "DEV_NO_AUTH": "0",
    "PUBLIC_HOST": "grip.voorbeeld.example",
    "OIDC_ISSUER": "https://sso.voorbeeld.example",
    "SESSION_SECRET_KEY": "voorbeeld-sleutel-voor-deze-test",
}


async def test_the_check_counts_what_differs_and_prints_it(
    db_session, create_person, capsys
):
    owner = await create_person("eigenaar@example.org", name="Priya Voorbeeld")
    whole = await assignments.create_assignment(
        db_session, name="Heel traject", actor=owner
    )
    damaged = await assignments.create_assignment(
        db_session, name="Beschädigd  traject é", actor=owner
    )
    await db_session.flush()

    assert await check(db_session) == 0
    assert (
        "2 opdrachten: 2 zonder verschillen, 0 met verschillen, 0 overgeslagen, "
        "0 niet te controleren." in capsys.readouterr().out
    )

    await db_session.execute(
        text("UPDATE assignment SET notes = 'Met de hand' WHERE id = :id"),
        {"id": damaged.id},
    )
    assert await check(db_session) == 1
    printed = capsys.readouterr().out
    assert f"Beschädigd  traject é ({damaged.id}):" in printed
    assert "notes: de kroniek zegt None, de tabel 'Met de hand'" in printed
    assert str(whole.id) not in printed
    assert (
        "2 opdrachten: 1 zonder verschillen, 1 met verschillen, 0 overgeslagen, "
        "0 niet te controleren." in printed
    )


async def test_the_check_names_what_it_skipped_and_counts_it_as_no_difference(
    db_session, capsys
):
    db_session.add(Assignment(uri="https://voorbeeld.example/id/1", name="Zonder feit"))
    await db_session.flush()

    assert await check(db_session) == 0
    printed = capsys.readouterr().out
    assert (
        "1 opdrachten: 0 zonder verschillen, 0 met verschillen, 1 overgeslagen, "
        "0 niet te controleren." in printed
    )
    assert "overgeslagen, geen kroniek: 1" in printed


async def test_a_row_gone_from_the_table_is_told_in_dutch(
    db_session, create_person, capsys
):
    owner = await create_person("eigenaar@example.org", name="Priya Voorbeeld")
    case = await assignments.create_assignment(
        db_session, name="Traject zonder eigenaar", actor=owner
    )
    await db_session.flush()
    await db_session.execute(
        text("DELETE FROM assignment_role WHERE assignment_id = :id"), {"id": case.id}
    )

    assert await check(db_session) == 1
    assert "de kroniek zegt een rij, de tabel geen rij" in capsys.readouterr().out


async def test_the_check_goes_on_past_a_case_it_cannot_read(
    db_session, create_person, capsys
):
    owner = await create_person("eigenaar@example.org", name="Priya Voorbeeld")
    whole = await assignments.create_assignment(
        db_session, name="Heel traject", actor=owner
    )
    broken = await assignments.create_assignment(
        db_session, name="Traject op de rand", actor=owner
    )
    await db_session.flush()
    # What a moment at the very start of the calendar reads back as: no zone.
    await db_session.execute(
        text("UPDATE assignment SET shared_at = '-infinity' WHERE id = :id"),
        {"id": broken.id},
    )

    assert await check(db_session) == 1
    printed = capsys.readouterr().out
    assert f"Traject op de rand ({broken.id}): niet te controleren (ValueError)." in (
        printed
    )
    assert str(whole.id) not in printed
    assert (
        "2 opdrachten: 1 zonder verschillen, 0 met verschillen, 0 overgeslagen, "
        "1 niet te controleren." in printed
    )


async def test_a_failed_query_ends_the_check_of_one_case_only(
    db_session, create_person, capsys, monkeypatch
):
    owner = await create_person("eigenaar@example.org", name="Priya Voorbeeld")
    first = await assignments.create_assignment(
        db_session, name="Eerste traject", actor=owner
    )
    second = await assignments.create_assignment(
        db_session, name="Tweede traject", actor=owner
    )
    await db_session.flush()

    async def the_database_refuses_one(session, assignment_id):
        if assignment_id == first.id:
            await session.execute(text("SELECT 1 / 0"))
        return await differences(session, assignment_id)

    monkeypatch.setattr("grip.chronicle.check.differences", the_database_refuses_one)

    assert await check(db_session) == 1
    printed = capsys.readouterr().out
    assert f"Eerste traject ({first.id}): niet te controleren" in printed
    assert str(second.id) not in printed
    assert "1 zonder verschillen, 0 met verschillen, 0 overgeslagen, 1 niet" in printed


def test_the_check_runs_on_an_instance_that_holds_no_example_data():
    with pytest.raises(SeedRefusedError):
        ensure_local_instance(Settings(_env_file=None, **REAL_INSTANCE))

    run = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "grip.chronicle.check"],
        cwd=BACKEND,
        env={
            **os.environ,
            **REAL_INSTANCE,
            "DATABASE_URL": get_settings().DATABASE_URL,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    # Whatever is committed on this database: the check itself went through.
    assert "opdrachten:" in run.stdout, run.stderr
