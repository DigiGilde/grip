"""Fixtures for the link with Wies. All names, addresses and data are fictional."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import get_settings
from grip.models.assignment import Allocation, Assignment, AssignmentRole, BudgetLine
from grip.models.organisation import Organisation
from grip.models.person import Person

EXPORT_KEY = "sleutel-voor-de-export"
TOOI = "https://identifier.overheid.nl/tooi/id/ministerie/mnre0001"
TODAY = date(2026, 6, 15)


@pytest.fixture
def wies_settings(_test_app):
    """Settings with the link switched on, for this test only."""

    def _apply(**overrides):
        values = {
            "GRIP_EXPORT_KEY": EXPORT_KEY,
            "WIES_BASE_URL": "https://wies.example",
            "WIES_API_KEY": "sleutel-voor-wies",
            "WIES_SUBORGANIZATIONS": "",
            "FRONTEND_URL": "https://grip.example",
        }
        values.update(overrides)
        settings = get_settings().model_copy(update=values)
        _test_app.dependency_overrides[get_settings] = lambda: settings
        return settings

    yield _apply
    _test_app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def make(db_session: AsyncSession):
    """Small builders for the records the export reads."""

    class Make:
        async def person(
            self, email: str, name: str = "Voorbeeld Persoon", **kw
        ) -> Person:
            person = Person(name=name, email=email, **kw)
            db_session.add(person)
            await db_session.flush()
            return person

        async def organisation(self, tooi_uri: str | None = TOOI) -> Organisation:
            org = Organisation(name="Voorbeeldministerie", tooi_uri=tooi_uri)
            db_session.add(org)
            await db_session.flush()
            return org

        async def assignment(
            self,
            name: str = "Opdracht Alfa",
            *,
            status: str = "in_progress",
            owner: Person | None = None,
            client: Organisation | None = None,
            start: date = date(2026, 1, 1),
            end: date = date(2026, 12, 31),
            **kw,
        ) -> Assignment:
            assignment = Assignment(
                uri=f"https://grip.example/id/opdracht/{name}",
                name=name,
                status=status,
                client_organisation_id=client.id if client else None,
                start_date=start,
                end_date=end,
                **kw,
            )
            db_session.add(assignment)
            await db_session.flush()
            if owner is not None:
                db_session.add(
                    AssignmentRole(
                        assignment_id=assignment.id, person_id=owner.id, role="owner"
                    )
                )
                await db_session.flush()
            return assignment

        async def line(
            self,
            assignment: Assignment,
            role: str = "Developer",
            *,
            fte: str = "1",
            start: date = date(2026, 1, 1),
            end: date = date(2026, 12, 31),
            category: str = "D",
        ) -> BudgetLine:
            line = BudgetLine(
                assignment_id=assignment.id,
                description=f"{role} (begroting)",
                kind="personnel",
                role=role,
                fte=Decimal(fte),
                rate_category=category,
                start_date=start,
                end_date=end,
            )
            db_session.add(line)
            await db_session.flush()
            return line

        async def fixed_line(
            self, assignment: Assignment, amount_cents: int = 1234500
        ) -> BudgetLine:
            line = BudgetLine(
                assignment_id=assignment.id,
                description="Hosting",
                kind="fixed",
                amount_cents=amount_cents,
                year=2026,
            )
            db_session.add(line)
            await db_session.flush()
            return line

        async def allocation(
            self,
            line: BudgetLine,
            person: Person,
            *,
            pct: str = "100",
            start: date = date(2026, 1, 1),
            end: date = date(2026, 12, 31),
        ) -> Allocation:
            allocation = Allocation(
                person_id=person.id,
                budget_line_id=line.id,
                start_date=start,
                end_date=end,
                fte_pct=Decimal(pct),
            )
            db_session.add(allocation)
            await db_session.flush()
            return allocation

    return Make()
