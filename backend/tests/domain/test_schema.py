"""The migration chain and the constraints in the database."""

import os
import subprocess
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from grip.core.config import get_settings
from grip.models.assignment import Allocation, Assignment, AssignmentRole, BudgetLine
from grip.models.cost import CostCoverage, CostItem
from grip.models.organisation import Organisation
from grip.models.rates import RateBand, RateCard

BACKEND = Path(__file__).resolve().parents[2]


async def test_migrations_apply_on_an_empty_database_without_drift():
    """Create a scratch database, upgrade to 0002_domain, check for drift."""
    url = make_url(get_settings().DATABASE_URL)
    scratch = f"grip_mig_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{scratch}"'))
    try:
        env = {
            **os.environ,
            "DEV_NO_AUTH": "1",
            "DATABASE_URL": url.set(database=scratch).render_as_string(
                hide_password=False
            ),
        }
        for args in (["upgrade", "0002_domain"], ["current"]):
            result = subprocess.run(
                [sys.executable, "-m", "alembic", *args],
                cwd=BACKEND,
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr
        assert "0002_domain" in result.stdout
        scratch_engine = create_async_engine(url.set(database=scratch))
        async with scratch_engine.connect() as conn:
            tables = set(
                (
                    await conn.execute(
                        text(
                            "SELECT tablename FROM pg_tables "
                            "WHERE schemaname = 'public'"
                        )
                    )
                ).scalars()
            )
        await scratch_engine.dispose()
        assert {
            "rate_card",
            "rate_band",
            "scale_band",
            "person_scale",
            "billability_target",
            "organisation",
            "assignment",
            "assignment_role",
            "budget_line",
            "allocation",
            "quote",
            "quote_invitation",
            "quote_acceptance",
            "quote_rejection",
            "month_close",
            "month_close_line",
            "cost_item",
            "invoice_line",
            "cost_coverage",
            "hire",
            "billing_export",
            "billing_export_line",
        } <= tables
        # Downgrade must work too.
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0001_initial"],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
    finally:
        async with admin.connect() as conn:
            await conn.execute(
                text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
            )
        await admin.dispose()


async def _refused(db_session, obj) -> None:
    savepoint = await db_session.begin_nested()
    db_session.add(obj)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await savepoint.rollback()


async def test_structural_rules_are_constraints(db_session, create_person):
    person = await create_person("constraint@example.org")
    db_session.add(RateCard(year=2031, status="active"))
    db_session.add(RateBand(year=2031, category="D", monthly_rate_cents=1))
    assignment = Assignment(uri="https://grip.example/id/opdracht/c1", name="C")
    db_session.add(assignment)
    await db_session.flush()
    line = BudgetLine(
        assignment_id=assignment.id,
        description="Rol",
        kind="personnel",
        fte=Decimal("1"),
        rate_category="D",
        start_date=date(2031, 1, 1),
        end_date=date(2031, 12, 31),
    )
    item = CostItem(description="Hosting")
    db_session.add_all([line, item])
    db_session.add(
        AssignmentRole(assignment_id=assignment.id, person_id=person.id, role="owner")
    )
    await db_session.flush()
    other = await create_person("constraint2@example.org")

    # Uniqueness per year and category.
    await _refused(db_session, RateBand(year=2031, category="D", monthly_rate_cents=2))
    await _refused(db_session, RateBand(year=2031, category="F", monthly_rate_cents=2))
    # One owner per assignment.
    await _refused(
        db_session,
        AssignmentRole(assignment_id=assignment.id, person_id=other.id, role="owner"),
    )
    # A personnel line needs its fields; a fixed line needs amount and year.
    await _refused(
        db_session,
        BudgetLine(assignment_id=assignment.id, description="X", kind="personnel"),
    )
    await _refused(
        db_session,
        BudgetLine(assignment_id=assignment.id, description="X", kind="fixed"),
    )
    # Date order and percentage range.
    await _refused(
        db_session,
        Allocation(
            person_id=person.id,
            budget_line_id=line.id,
            start_date=date(2031, 3, 1),
            end_date=date(2031, 2, 1),
            fte_pct=Decimal(50),
        ),
    )
    await _refused(
        db_session,
        Allocation(
            person_id=person.id,
            budget_line_id=line.id,
            start_date=date(2031, 1, 1),
            end_date=date(2031, 2, 1),
            fte_pct=Decimal(120),
        ),
    )
    await _refused(
        db_session,
        CostCoverage(cost_item_id=item.id, budget_line_id=line.id, pct=Decimal(0)),
    )
    # Unknown status.
    await _refused(
        db_session,
        Assignment(uri="https://grip.example/id/opdracht/c2", name="D", status="klaar"),
    )


async def test_units_of_one_organisation_share_a_tooi_uri(db_session):
    tooi = "https://identifier.overheid.nl/tooi/id/oorg/oorg00000"
    db_session.add_all(
        [
            Organisation(name="Dienst", tooi_uri=tooi),
            Organisation(name="Onderdeel", tooi_uri=tooi, unit_key="onderdeel"),
            Organisation(name="Zonder registratie"),
            Organisation(name="Ook zonder registratie"),
        ]
    )
    await db_session.flush()

    await _refused(db_session, Organisation(name="Dienst dubbel", tooi_uri=tooi))
    await _refused(
        db_session,
        Organisation(name="Onderdeel dubbel", tooi_uri=tooi, unit_key="onderdeel"),
    )
