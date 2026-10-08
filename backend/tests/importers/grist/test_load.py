"""Loading a plan through the service layer, and reconciling it.

These tests need the database. Every test runs in a transaction that is
rolled back.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.calc import CoverageBasis, PartialMonths
from grip.importers.grist.document import GristDocument
from grip.importers.grist.load import load_plan
from grip.importers.grist.mapping import Mapping, check_mapping
from grip.importers.grist.reconcile import reconcile, render
from grip.importers.grist.refs import GristImportRef
from grip.importers.grist.transform import build_plan
from grip.models.assignment import Allocation, Assignment, AssignmentRole, BudgetLine
from grip.models.audit_log import AuditLog
from grip.models.cost import CostCoverage, CostItem, InvoiceLine
from grip.models.person import Person
from grip.models.person_details import BillabilityTarget, PersonScale
from grip.models.rates import RateBand, ScaleBand
from grip.repositories.domain import RateRepository
from grip.services import events, rates, team
from tests.importers.grist.builder import build_grist
from tests.importers.grist.conftest import fictional_tables
from tests.importers.grist.helpers import confirm_all, confirmed_plan

KEY = "test"


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


async def count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def imported(session: AsyncSession, model: type, entity: str) -> list:
    """The rows of a model that this import made, by Grist row id."""
    refs = (
        await session.execute(
            select(GristImportRef.grist_row_id, GristImportRef.entity_id)
            .where(GristImportRef.document_key == KEY, GristImportRef.entity == entity)
            .order_by(GristImportRef.grist_row_id)
        )
    ).all()
    return [await session.get(model, entity_id) for _, entity_id in refs]


async def add_rate_card_2027(session: AsyncSession) -> None:
    await rates.create_rate_card(session, 2027, actor=None, copy_from=2026)
    await rates.set_rate_card_status(session, 2027, "active", actor=None)


def variant_tables(change) -> list:
    tables = fictional_tables()
    change({table.table_id: table for table in tables})
    return tables


def plan_for(path: Path, mapping: Mapping):
    with GristDocument(path) as doc:
        return confirmed_plan(doc, mapping)


async def test_loads_everything_through_the_services(
    db_session: AsyncSession, document: GristDocument, mapping: Mapping
) -> None:
    plan = confirmed_plan(document, mapping)
    result = await load_plan(db_session, plan, document_key=KEY)

    assert result.errors == []
    assert result.created == {
        "rate_card": 1,
        "rate_band": 5,
        "scale_band": 10,
        "person": 3,
        "person_scale": 3,
        "billability_target": 1,
        "assignment": 3,
        "budget_line": 5,
        "allocation": 4,
        "cost_item": 1,
        "invoice_line": 2,
        "cost_coverage": 2,
    }
    card = await RateRepository(db_session).get_card(2026)
    assert card is not None and card.status == "active"
    assert await count(db_session, RateBand) == 5
    assert await count(db_session, ScaleBand) == 10

    alfa, beta, internal = await imported(db_session, Assignment, "assignment")
    assert (alfa.name, alfa.status, alfa.kind) == (
        "Opdracht Alfa 2026",
        "in_progress",
        "external",
    )
    assert alfa.quoted_amount_cents == 40_000_000
    assert alfa.uri.startswith("http")
    assert beta.status == "quoted"
    assert (internal.kind, internal.status) == ("internal", "in_progress")

    lines = await imported(db_session, BudgetLine, "budget_line")
    assert [line.kind for line in lines] == [
        "personnel",
        "personnel",
        "fixed",
        "personnel",
        "fixed",
    ]
    assert lines[0].fte == Decimal("0.8") and lines[0].rate_category == "D"
    assert lines[2].amount_cents == 6_000_000 and lines[2].year == 2026

    allocations = await imported(db_session, Allocation, "allocation")
    assert [a.fte_pct for a in allocations] == [
        Decimal(80),
        Decimal(100),
        Decimal(50),
        Decimal(50),
    ]
    scales = await imported(db_session, PersonScale, "person_scale")
    assert [s.billing_scale for s in scales] == [14, 12, 10]
    assert await count(db_session, BillabilityTarget) == 1
    assert await count(db_session, CostCoverage) == 2
    assert await count(db_session, InvoiceLine) == 2
    # The loader goes through the services, so the audit log is filled.
    assert await count(db_session, AuditLog) > 30


async def test_a_rerun_changes_nothing(
    db_session: AsyncSession, document: GristDocument, mapping: Mapping
) -> None:
    plan = confirmed_plan(document, mapping)
    await load_plan(db_session, plan, document_key=KEY)
    before = {
        model: await count(db_session, model)
        for model in (
            Person,
            Assignment,
            BudgetLine,
            Allocation,
            CostItem,
            InvoiceLine,
            CostCoverage,
            PersonScale,
            GristImportRef,
            AuditLog,
        )
    }
    again = await load_plan(db_session, plan, document_key=KEY)
    assert again.errors == []
    assert again.created == {}
    assert again.updated == {}
    assert again.vanished == []
    assert sum(again.unchanged.values()) == 39
    # Not one row more, and no audit row either: nothing was touched.
    assert {model: await count(db_session, model) for model in before} == before


async def test_a_newer_download_updates_instead_of_duplicating(
    db_session: AsyncSession, grist_path: Path, tmp_path: Path, mapping: Mapping
) -> None:
    await load_plan(db_session, plan_for(grist_path, mapping), document_key=KEY)

    def change(tables) -> None:
        tables["Inzet"].rows[0]["FTE"] = 0.6
        tables["Opdracht"].rows[0]["Bedrag"] = 410_000
        tables["Team"].rows[2]["Naam"] = "Dana Demo-Voorbeeld"
        tables["Kosten"].rows[0]["Begroot"] = 13_000
        tables["Factuur"].rows[1]["Bedrag"] = 7_000
        del tables["Factuur"].rows[0]
        tables["Factuur"].rows[0]["id"] = 2
        tables["Begroting"].rows.append(
            {"Opdracht": [2], "Omschrijving": "Licenties (stelpost)", "Begroot": 5_000}
        )

    newer = build_grist(tmp_path / "later.grist", variant_tables(change))
    with GristDocument(newer) as doc:
        check = check_mapping(doc, mapping)
        plan = build_plan(
            doc,
            mapping,
            check,
            confirmations=confirm_all(build_plan(doc, mapping, check).confirmations),
        )
    result = await load_plan(db_session, plan, document_key=KEY)

    assert result.errors == []
    assert result.created == {"budget_line": 1}
    assert result.updated == {
        "allocation": 1,
        "assignment": 1,
        "person": 1,
        "cost_item": 1,
        "invoice_line": 1,
    }
    assert await count(db_session, Assignment) == 3
    assert await count(db_session, BudgetLine) == 6
    assert await count(db_session, Allocation) == 4
    assert await count(db_session, Person) == 3
    allocations = await imported(db_session, Allocation, "allocation")
    assert allocations[0].fte_pct == Decimal(60)
    # The invoice row that is gone is reported and left alone.
    assert [(table, row) for table, row, _ in result.vanished] == [("Factuur", 1)]
    assert await count(db_session, InvoiceLine) == 2
    assert any("verwijdert niets" in issue.message for issue in result.issues)


async def test_a_person_who_exists_is_adopted_by_email(
    db_session: AsyncSession, document: GristDocument, mapping: Mapping
) -> None:
    existing = await team.create_person(
        db_session, name="V. Voorbeeld", email="Vera@Voorbeeld.example", actor=None
    )
    result = await load_plan(
        db_session, confirmed_plan(document, mapping), document_key=KEY
    )
    assert result.persons[1] == existing.id
    assert await count(db_session, Person) == 3
    await db_session.refresh(existing)
    assert existing.name == "Vera Voorbeeld"


async def test_the_actor_is_in_the_audit_log(
    db_session: AsyncSession, document: GristDocument, mapping: Mapping
) -> None:
    actor = await team.create_person(
        db_session, name="Importeur", email="import@voorbeeld.example", actor=None
    )
    await load_plan(
        db_session, confirmed_plan(document, mapping), document_key=KEY, actor=actor
    )
    by_actor = await db_session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.actor_id == actor.id)
    )
    assert by_actor and by_actor > 30


async def test_unconfirmed_lines_load_as_text_with_an_amount(
    db_session: AsyncSession, document: GristDocument, mapping: Mapping
) -> None:
    plan = build_plan(document, mapping, check_mapping(document, mapping))
    result = await load_plan(db_session, plan, document_key=KEY)
    assert result.errors == []
    lines = await imported(db_session, BudgetLine, "budget_line")
    assert {line.kind for line in lines} == {"fixed"}
    assert lines[0].description == "Productmanager (0,8 FTE, schaal 14/15)"
    assert lines[0].amount_cents == 17_280_000
    assert await count(db_session, Allocation) == 0
    assert await count(db_session, PersonScale) == 0
    # Without an address a person gets a placeholder that cannot log in.
    persons = await imported(db_session, Person, "person")
    assert all(p.email.endswith("@import.invalid") for p in persons)

    # The reconciliation says why such a line is not what it was in Grist.
    report = await reconcile(db_session, plan, result)
    best = report.best
    assert best is not None
    notes = {row.note for row in best.rows if row.group == "begrotingsregel"}
    assert "regel is niet bevestigd; als vast bedrag geladen" in notes
    assert not report.reconciles


async def test_a_refusal_by_a_service_is_an_issue_and_the_rest_goes_on(
    db_session: AsyncSession, tmp_path: Path, mapping: Mapping
) -> None:
    def change(tables) -> None:
        tables["Kostendekking"].rows[0]["Percentage"] = 0.7

    path = build_grist(tmp_path / "teveel.grist", variant_tables(change))
    result = await load_plan(db_session, plan_for(path, mapping), document_key=KEY)
    assert len(result.errors) == 1
    assert "meer dan 100" in result.errors[0].message
    assert result.errors[0].where.startswith("Kostendekking rij")
    assert await count(db_session, CostCoverage) == 1
    assert await count(db_session, Allocation) == 4


async def test_a_closed_year_is_refused_unless_allowed(
    db_session: AsyncSession, document: GristDocument, mapping: Mapping
) -> None:
    await rates.create_rate_card(db_session, 2026, actor=None)
    await rates.set_rate_card_status(db_session, 2026, "closed", actor=None)
    plan = confirmed_plan(document, mapping)

    refused = await load_plan(db_session, plan, document_key=KEY)
    assert refused.errors
    assert await count(db_session, RateBand) == 0

    allowed = await load_plan(
        db_session, plan, document_key="test-2", allow_closed_year=True
    )
    assert allowed.errors == []
    assert await count(db_session, RateBand) == 5


async def test_two_documents_do_not_share_references(
    db_session: AsyncSession, document: GristDocument, mapping: Mapping
) -> None:
    plan = confirmed_plan(document, mapping)
    await load_plan(db_session, plan, document_key=KEY)
    await load_plan(db_session, plan, document_key="ander-document")
    assert await count(db_session, Assignment) == 6
    # People are the same people: adopted by email, not doubled.
    assert await count(db_session, Person) == 3


async def test_owner_from_grist_becomes_the_owner_role(
    db_session: AsyncSession, tmp_path: Path, mapping_path: Path
) -> None:
    from grip.importers.grist.mapping import load_mapping
    from tests.importers.grist.builder import Col

    def change(tables) -> None:
        tables["Opdracht"].columns.append(Col("Eigenaar", "Ref:Team"))
        tables["Opdracht"].rows[0]["Eigenaar"] = 2

    mapping_path.write_text(
        mapping_path.read_text(encoding="utf-8").replace(
            'owner = ""', 'owner = "Eigenaar"'
        ),
        encoding="utf-8",
    )
    path = build_grist(tmp_path / "eigenaar.grist", variant_tables(change))
    result = await load_plan(
        db_session, plan_for(path, load_mapping(mapping_path)), document_key=KEY
    )
    role = await db_session.scalar(
        select(AssignmentRole).where(
            AssignmentRole.assignment_id == result.assignments[1]
        )
    )
    assert role is not None
    assert (role.person_id, role.role) == (result.persons[2], "owner")


# -- reconciliation -----------------------------------------------------------


async def test_reconciles_to_the_euro_and_answers_the_open_question(
    db_session: AsyncSession, document: GristDocument, mapping: Mapping
) -> None:
    plan = confirmed_plan(document, mapping)
    result = await load_plan(db_session, plan, document_key=KEY)
    await add_rate_card_2027(db_session)
    report = await reconcile(db_session, plan, result)

    assert report.compared == 30
    best = report.best
    assert best is not None
    assert (best.partial_months, best.coverage_basis) == (
        PartialMonths.GRIST_DATEDIF,
        CoverageBasis.FORECAST,
    )
    assert best.differing == []
    assert report.reconciles

    # The current default of grip does not reconcile: the partial period
    # is priced pro rata there.
    default = report.default_variant
    assert default is not None
    assert default.partial_months is PartialMonths.CALENDAR_DAYS
    differing = {(row.group, row.measure) for row in default.differing}
    assert ("inzet", "inzetbedrag") in differing
    assert ("opdracht", "uitputting") in differing

    text = render(report)
    assert "Uitkomst: SLUIT AAN" in text
    assert "niet de standaard van grip" in text
    assert "grist_datedif" in text


async def test_values_per_kind_match_the_worked_examples(
    db_session: AsyncSession, document: GristDocument, mapping: Mapping
) -> None:
    plan = confirmed_plan(document, mapping)
    result = await load_plan(db_session, plan, document_key=KEY)
    await add_rate_card_2027(db_session)
    report = await reconcile(db_session, plan, result)
    best = report.best
    assert best is not None
    values = {(r.group, r.label, r.measure): r.grip_cents for r in best.rows}
    assert values[("opdracht", "Opdracht Alfa 2026 (rij 1)", "begroot")] == 37_780_000
    assert values[("opdracht", "Opdracht Beta 2026 (rij 2)", "uitputting")] == 9_150_000
    assert (
        values[
            (
                "begrotingsregel",
                "Productmanager (0,8 FTE, schaal 14/15) (rij 1)",
                "begroot",
            )
        ]
        == 17_280_000
    )
    assert values[("kostenpost", "Hostingcontract (rij 1)", "prognose")] == 1_500_000
    assert values[("kostenpost", "Hostingcontract (rij 1)", "dekking")] == 1_200_000
    assert values[("KPI", "Vera Voorbeeld (rij 1)", "target")] == 19_440_000
    assert values[("KPI", "Vera Voorbeeld (rij 1)", "realisatie")] == 17_280_000


async def test_a_missing_rate_card_is_reported_never_zero(
    db_session: AsyncSession, document: GristDocument, mapping: Mapping
) -> None:
    plan = confirmed_plan(document, mapping)
    result = await load_plan(db_session, plan, document_key=KEY)
    report = await reconcile(db_session, plan, result)

    assert not report.reconciles
    best = report.best
    assert best is not None
    across = [row for row in best.differing if row.group == "inzet"]
    assert len(across) == 1
    assert across[0].grip_cents is None
    assert "tarievenkaart voor 2027" in across[0].note
    text = render(report)
    assert "Uitkomst: SLUIT NIET AAN" in text
    assert "2027" in text


async def test_coverage_on_the_budgeted_amount_is_recognised(
    db_session: AsyncSession, tmp_path: Path, mapping: Mapping
) -> None:
    def change(tables) -> None:
        # The same document, had it computed coverage on Begroot (12.000).
        tables["Kostendekking"].rows[0]["Bedrag"] = 3_600
        tables["Kostendekking"].rows[1]["Bedrag"] = 6_000
        tables["Kosten"].rows[0]["Dekking"] = 9_600
        tables["Begroting"].rows[4].update(Uitputting=3_600, Beschikbaar=6_400)
        tables["Begroting"].rows[3].update(Uitputting=90_000, Beschikbaar=54_000)
        tables["Opdracht"].rows[0].update(Uitputting=311_400, Beschikbaar=66_400)
        tables["Opdracht"].rows[1].update(Uitputting=90_000, Beschikbaar=54_000)

    path = build_grist(tmp_path / "begroot.grist", variant_tables(change))
    plan = plan_for(path, mapping)
    result = await load_plan(db_session, plan, document_key=KEY)
    await add_rate_card_2027(db_session)
    report = await reconcile(db_session, plan, result)
    best = report.best
    assert best is not None
    assert best.coverage_basis is CoverageBasis.BUDGETED
    assert report.reconciles


async def test_nothing_to_compare_proves_nothing(
    db_session: AsyncSession, document: GristDocument, mapping: Mapping
) -> None:
    plan = confirmed_plan(document, mapping)
    result = await load_plan(db_session, plan, document_key=KEY)
    plan.figures = type(plan.figures)()
    report = await reconcile(db_session, plan, result)
    assert report.compared == 0
    assert not report.reconciles
    assert "NIET AANGETOOND" in render(report)


async def test_a_person_without_scale_shows_in_the_report(
    db_session: AsyncSession, document: GristDocument, mapping: Mapping
) -> None:
    check = check_mapping(document, mapping)
    confirmations = confirm_all(build_plan(document, mapping, check).confirmations)
    scale = confirmations.get("person_scale:2")
    assert scale is not None
    scale.status = "overslaan"
    plan = build_plan(document, mapping, check, confirmations=confirmations)
    result = await load_plan(db_session, plan, document_key=KEY)
    await add_rate_card_2027(db_session)
    report = await reconcile(db_session, plan, result)
    best = report.best
    assert best is not None
    notes = [row.note for row in best.differing if row.group == "inzet"]
    assert any("geen inzetschaal" in note for note in notes)


def test_dates() -> None:
    # Guards the fixture itself: the cross-year allocation really crosses.
    tables = {table.table_id: table for table in fictional_tables()}
    row = tables["Inzet"].rows[2]
    assert (row["Startdatum"], row["Einddatum"]) == (
        date(2026, 7, 1),
        date(2027, 6, 30),
    )
