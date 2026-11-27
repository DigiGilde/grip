"""Every write to an assignment, its roles and its budget lines is a fact.

All names and amounts are fictional.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from grip.chronicle import guard
from grip.chronicle.ledger import fold
from grip.chronicle.verify import differences
from grip.models.assignment import Allocation, AssignmentRole, BudgetLine
from grip.models.catalogue_role import CatalogueRole
from grip.models.stream_event import StreamEvent
from grip.repositories.chronicle import ChronicleRepository
from grip.services import assignments, budget_intent, catalogue_roles, rates, stale
from grip.services.errors import (
    ClosedYearError,
    DomainValidationError,
    IllegalTransitionError,
)
from grip.tasks.handlers import register_task_handlers
from tests.chronicle.walking import (
    Walk,
    add_rate_card,
    line_body,
    make_cast,
)

INSTANCE = "https://grip.voorbeeld.example"
START, END = date(2026, 1, 1), date(2026, 12, 31)


async def _facts(session, assignment_id: UUID) -> list[str]:
    grams = await ChronicleRepository(session).grams(assignment_id)
    return [gram.fact for gram in grams]


async def _same(session, assignment_id: UUID) -> None:
    await session.flush()
    report = await differences(session, assignment_id)
    assert report.checked, report.reason
    assert report.differences == [], [str(item) for item in report.differences]


async def _rows_of_type(session, assignment_id: UUID) -> list[tuple[str, dict]]:
    """Audit rows and domain events of a case, oldest first."""
    rows = await session.scalars(
        select(StreamEvent)
        .where(
            StreamEvent.case_id == assignment_id,
            StreamEvent.subject_kind != "chronolexogram",
        )
        .order_by(StreamEvent.seq)
    )
    return [(row.type, row.new_value or row.payload or {}) for row in rows]


@pytest.fixture
async def owner(create_person):
    return await create_person("eigenaar@example.org", name="Priya Voorbeeld")


@pytest.fixture
async def other(create_person):
    return await create_person("collega@example.org", name="Wim Voorbeeld")


@pytest.fixture
async def organisation(db_session):
    return await assignments.upsert_organisation(
        db_session,
        name="Voorbeeldorganisatie",
        tooi_uri="https://identifier.overheid.nl/tooi/id/voorbeeld/1",
        instance_uri=f"{INSTANCE}/",
    )


async def _new(db_session, owner, **values):
    values.setdefault("name", "Voorbeeldopdracht")
    return await assignments.create_assignment(db_session, actor=owner, **values)


async def _personnel(db_session, assignment, owner, **values):
    values.setdefault("description", "Voorbeeldregel")
    return await assignments.add_budget_line(
        db_session,
        assignment.id,
        kind="personnel",
        fte=values.pop("fte", Decimal("0.8")),
        rate_category="D",
        actor=owner,
        **values,
    )


# -- the birth of a case -------------------------------------------------------


async def test_creating_writes_one_fact_with_the_owner(db_session, owner):
    assignment = await _new(db_session, owner, notes="Voorbeeldnotitie")
    assert await _facts(db_session, assignment.id) == ["assignment_created"]
    assert assignment.status == "draft"
    await _same(db_session, assignment.id)
    roles = await db_session.scalars(
        select(AssignmentRole).where(AssignmentRole.assignment_id == assignment.id)
    )
    assert [(role.person_id, role.role) for role in roles] == [(owner.id, "owner")]


async def test_creating_without_anyone_writes_no_role(db_session):
    assignment = await assignments.create_assignment(
        db_session, name="Voorbeeldopdracht", actor=None
    )
    assert await _facts(db_session, assignment.id) == ["assignment_created"]
    await _same(db_session, assignment.id)


async def test_a_request_is_one_fact_with_status_and_sharing(
    db_session, owner, organisation
):
    assignment, _ = await assignments.create_assignment_request(
        db_session,
        name="Voorbeeldaanvraag",
        contractor_organisation_id=organisation.id,
        actor=owner,
        description="Voorbeeldomschrijving",
    )
    assert await _facts(db_session, assignment.id) == ["assignment_requested"]
    assert assignment.status == "requested"
    assert assignment.shared_with_instance_uri == INSTANCE
    assert assignment.shared_at is not None
    await _same(db_session, assignment.id)

    await db_session.flush()
    rows = await _rows_of_type(db_session, assignment.id)
    assert [row[0] for row in rows] == [
        "assignment.created",
        "assignment.updated",
        "assignment.status_changed",
        "assignment_request.created",
    ]
    assert rows[0][1]["status"] == "draft"
    assert rows[1][1] == {"status": "requested"}


async def test_a_received_request_is_one_fact_and_says_where_from(
    db_session, organisation
):
    uri = f"{INSTANCE}/id/opdracht/{uuid4()}"
    assignment = await assignments.receive_assignment_request(
        db_session,
        uri=uri,
        name="Voorbeeldaanvraag",
        client_organisation_id=organisation.id,
        description="Voorbeeldomschrijving",
        received={"from": "voorbeeldpeer", "id": "bericht-1"},
    )
    assert await _facts(db_session, assignment.id) == ["assignment_request_received"]
    assert assignment.status == "requested"
    assert assignment.shared_with_instance_uri == INSTANCE
    await _same(db_session, assignment.id)
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[0].fields["received"] == {"from": "voorbeeldpeer", "id": "bericht-1"}

    await db_session.flush()
    rows = await _rows_of_type(db_session, assignment.id)
    assert [row[0] for row in rows] == [
        "assignment.created",
        "assignment.updated",
        "assignment.status_changed",
    ]
    assert rows[0][1]["status"] == "draft"

    # The same request again changes nothing.
    again = await assignments.receive_assignment_request(
        db_session,
        uri=uri,
        name="Voorbeeldaanvraag",
        client_organisation_id=organisation.id,
    )
    assert again.id == assignment.id
    assert await _facts(db_session, assignment.id) == ["assignment_request_received"]


# -- changing a case -----------------------------------------------------------


async def test_a_change_says_only_what_changes(db_session, owner):
    assignment = await _new(db_session, owner, notes="Oud")
    await assignments.update_assignment(
        db_session, assignment.id, actor=owner, name="Nieuw", notes="Oud"
    )
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert [gram.fact for gram in grams] == [
        "assignment_created",
        "assignment_changed",
    ]
    assert grams[1].fields["changes"] == {"name": "Nieuw"}
    assert grams[1].actor_person_id == owner.id
    await _same(db_session, assignment.id)


async def test_a_change_that_changes_nothing_is_no_fact(db_session, owner):
    assignment = await _new(db_session, owner, notes="Oud")
    await assignments.update_assignment(
        db_session, assignment.id, actor=owner, notes="Oud"
    )
    await db_session.flush()
    assert await _facts(db_session, assignment.id) == ["assignment_created"]
    rows = await _rows_of_type(db_session, assignment.id)
    assert [row[0] for row in rows] == ["assignment.created", "assignment.updated"]
    assert rows[1][1] == {"notes": "Oud"}
    await _same(db_session, assignment.id)


async def test_a_new_period_moves_lines_and_allocations_in_one_fact(
    db_session, owner, other
):
    actor = owner
    assignment = await _new(db_session, actor, start_date=START, end_date=END)
    following = await _personnel(db_session, assignment, actor)
    own = await _personnel(
        db_session,
        assignment,
        actor,
        description="Eigen periode",
        period_source="own",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 4, 30),
    )
    await rates.create_rate_card(db_session, 2027, actor=actor)
    allocation = await assignments.add_allocation(
        db_session, following.id, other.id, fte_pct=Decimal("50"), actor=actor
    )
    before = len(await _facts(db_session, assignment.id))

    new_end = date(2027, 6, 30)
    await assignments.update_assignment(
        db_session, assignment.id, actor=actor, end_date=new_end
    )

    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert len(grams) == before + 1
    fact = grams[-1]
    assert fact.fact == "assignment_changed"
    assert fact.fields["changes"] == {"end_date": "2027-06-30"}
    assert fact.fields["moved_lines"] == {
        str(following.id): {"start_date": "2026-01-01", "end_date": "2027-06-30"}
    }
    assert following.end_date == new_end
    assert own.end_date == date(2026, 4, 30)
    await db_session.refresh(allocation)
    assert allocation.end_date == new_end
    await _same(db_session, assignment.id)

    await db_session.flush()
    rows = await _rows_of_type(db_session, assignment.id)
    assert rows[-1][0] == "assignment.updated"
    assert rows[-1][1] == {
        "end_date": "2027-06-30",
        "moved_budget_lines": [str(following.id)],
        "moved_allocations": [str(allocation.id)],
    }


async def test_a_period_taken_away_empties_the_following_lines(db_session, owner):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner)
    assert line.start_date == START

    await assignments.update_assignment(
        db_session, assignment.id, actor=owner, start_date=None, end_date=None
    )
    assert (line.start_date, line.end_date) == (None, None)
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[-1].fields["moved_lines"] == {
        str(line.id): {"start_date": None, "end_date": None}
    }
    await _same(db_session, assignment.id)


async def test_a_refused_move_writes_no_fact(db_session, owner, other):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner)
    await assignments.add_allocation(
        db_session, line.id, other.id, fte_pct=Decimal("50"), actor=owner
    )
    before = await _facts(db_session, assignment.id)
    with pytest.raises(DomainValidationError):
        await assignments.update_assignment(
            db_session, assignment.id, actor=owner, start_date=None, end_date=None
        )
    assert await _facts(db_session, assignment.id) == before
    await _same(db_session, assignment.id)


# -- the status of a case ------------------------------------------------------


async def test_a_step_is_one_fact_with_where_from_and_where_to(
    db_session, owner, organisation
):
    assignment = await _new(
        db_session, owner, contractor_organisation_id=organisation.id
    )
    await assignments.transition(
        db_session, assignment.id, "cancelled", actor=owner, reason="Niet nodig"
    )
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[-1].fact == "assignment_status_changed"
    assert grams[-1].fields == {
        "assignment_id": str(assignment.id),
        "from": "draft",
        "to": "cancelled",
        "reason": "Niet nodig",
    }
    assert assignment.status == "cancelled"
    await _same(db_session, assignment.id)

    await db_session.flush()
    rows = await _rows_of_type(db_session, assignment.id)
    assert [row[0] for row in rows] == [
        "assignment.created",
        "assignment.updated",
        "assignment.status_changed",
    ]
    assert rows[1][1] == {"status": "cancelled", "reason": "Niet nodig"}


async def test_a_verbal_agreement_keeps_its_note_after_the_next_step(
    db_session, owner, organisation
):
    assignment = await _new(
        db_session,
        owner,
        contractor_organisation_id=organisation.id,
        start_date=START,
        end_date=END,
    )
    await assignments.transition(db_session, assignment.id, "quoted", actor=owner)
    await assignments.transition(
        db_session,
        assignment.id,
        "verbally_agreed",
        actor=owner,
        reason="  Voorbeeld zei ja  ",
    )
    await _same(db_session, assignment.id)
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[-1].fields["verbal_agreement_note"] == "Voorbeeld zei ja"

    await assignments.transition(db_session, assignment.id, "accepted", actor=owner)
    await _same(db_session, assignment.id)
    assert assignment.verbal_agreement_note == "Voorbeeld zei ja"
    assert assignment.verbal_agreement_at is not None


async def test_a_refused_step_writes_no_fact(db_session, owner):
    assignment = await _new(db_session, owner)
    with pytest.raises(IllegalTransitionError):
        await assignments.transition(
            db_session, assignment.id, "in_progress", actor=owner
        )
    assert await _facts(db_session, assignment.id) == ["assignment_created"]


# -- sharing -------------------------------------------------------------------


async def test_sharing_is_a_fact_once(db_session, owner):
    assignment = await _new(db_session, owner)
    await assignments.share_with_instance(
        db_session, assignment, f"  {INSTANCE}/ ", actor=owner
    )
    assert assignment.shared_with_instance_uri == INSTANCE
    moment = assignment.shared_at
    await _same(db_session, assignment.id)

    await assignments.share_with_instance(db_session, assignment, f"{INSTANCE}/")
    await assignments.share_with_instance(db_session, assignment, "  ")
    assert assignment.shared_at == moment
    assert await _facts(db_session, assignment.id) == [
        "assignment_created",
        "assignment_shared",
    ]


# -- roles ---------------------------------------------------------------------


async def test_a_new_manager_is_a_fact(db_session, owner, other):
    assignment = await _new(db_session, owner)
    role = await assignments.set_assignment_role(
        db_session, assignment.id, other.id, "manager", actor=owner
    )
    assert role.role == "manager"
    assert await _facts(db_session, assignment.id) == [
        "assignment_created",
        "assignment_role_set",
    ]
    await _same(db_session, assignment.id)


async def test_a_new_owner_demotes_the_old_one_in_one_fact(
    db_session, owner, other, create_person
):
    assignment = await _new(db_session, owner)
    old_role = await db_session.scalar(
        select(AssignmentRole).where(AssignmentRole.assignment_id == assignment.id)
    )
    await assignments.set_assignment_role(
        db_session, assignment.id, other.id, "manager", actor=owner
    )
    # A manager who becomes owner: the unique index on one owner must hold,
    # whichever row sorts first.
    await assignments.set_assignment_role(
        db_session, assignment.id, other.id, "owner", actor=owner
    )
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[-1].fact == "assignment_role_set"
    assert grams[-1].fields["demoted"] == [str(old_role.id)]
    assert old_role.role == "manager"
    await _same(db_session, assignment.id)

    # A brand new person as owner: the old owner steps down in the same fact.
    newcomer = await create_person("nieuw@example.org", name="Nieuwe Voorbeeld")
    await assignments.set_assignment_role(
        db_session, assignment.id, newcomer.id, "owner", actor=owner
    )
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[-1].fields["new"] is True
    assert len(grams[-1].fields["demoted"]) == 1
    await _same(db_session, assignment.id)


async def test_setting_a_role_moves_the_version_also_without_a_fact(
    db_session, owner, other
):
    assignment = await _new(db_session, owner)
    started_from = assignment.version
    await assignments.set_assignment_role(
        db_session, assignment.id, other.id, "manager", actor=owner
    )
    assert assignment.version == started_from + 1
    facts = await _facts(db_session, assignment.id)

    # The same role again: audited and counted as before, nothing to establish.
    await assignments.set_assignment_role(
        db_session, assignment.id, other.id, "manager", actor=owner
    )
    assert assignment.version == started_from + 2
    assert await _facts(db_session, assignment.id) == facts
    await _same(db_session, assignment.id)


async def test_a_refused_role_change_writes_nothing(db_session, owner):
    assignment = await _new(db_session, owner)
    started_from = assignment.version
    with pytest.raises(DomainValidationError):
        await assignments.set_assignment_role(
            db_session, assignment.id, owner.id, "manager", actor=owner
        )
    await db_session.flush()
    assert assignment.version == started_from
    assert await _facts(db_session, assignment.id) == ["assignment_created"]


async def test_a_stale_role_change_is_refused(db_session, owner, other):
    assignment = await _new(db_session, owner)
    started_from = assignment.version
    await assignments.set_assignment_role(
        db_session, assignment.id, other.id, "manager", actor=owner
    )
    with stale.expecting(f'"{assignment.id}:{started_from}"'):
        with pytest.raises(stale.StaleWriteError):
            await assignments.set_assignment_role(
                db_session, assignment.id, other.id, "owner", actor=owner
            )


async def test_removing_a_manager_is_a_fact_before_its_audit_row(
    db_session, owner, other
):
    assignment = await _new(db_session, owner)
    role = await assignments.set_assignment_role(
        db_session, assignment.id, other.id, "manager", actor=owner
    )
    role_id = role.id
    await assignments.remove_assignment_role(
        db_session, assignment.id, other.id, actor=owner
    )
    await db_session.flush()
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[-1].fact == "assignment_role_removed"
    assert grams[-1].fields == {"role_id": str(role_id)}
    await _same(db_session, assignment.id)

    row = await db_session.scalar(
        select(StreamEvent)
        .where(StreamEvent.type == "assignment_role.deleted")
        .where(StreamEvent.subject_id == str(role_id))
    )
    assert row.case_id == assignment.id
    assert row.old_value["role"] == "manager"
    assert row.seq > grams[-1].seq


# -- budget lines --------------------------------------------------------------


async def test_a_line_is_one_fact_with_its_role_resolved(db_session, owner):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(
        db_session,
        assignment,
        owner,
        description="Tweede",
        role="  Nieuwe   voorbeeldrol ",
        fte=Decimal("0.12345"),
    )
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[-1].fact == "budget_line_added"
    fact_line = grams[-1].fields["line"]
    assert fact_line["role"] == "Nieuwe voorbeeldrol"
    assert fact_line["detail"] == "Tweede"
    assert fact_line["fte"] == "0.123"
    assert fact_line["role_id"] == str(line.role_id)
    entry = await db_session.get(CatalogueRole, line.role_id)
    assert entry.needs_review is True
    await _same(db_session, assignment.id)

    # The audit row keeps what it always said: the name as shown, the fte sent.
    await db_session.flush()
    row = await db_session.scalar(
        select(StreamEvent).where(
            StreamEvent.type == "budget_line.created",
            StreamEvent.subject_id == str(line.id),
        )
    )
    assert row.new_value["description"] == "Nieuwe voorbeeldrol: Tweede"
    assert row.new_value["role"] == "Nieuwe voorbeeldrol"
    assert row.new_value["fte"] == "0.12345"


async def test_a_role_in_other_capitals_is_the_entry_of_the_catalogue(
    db_session, owner
):
    entry = CatalogueRole(id=uuid4(), name="Voorbeeldrol", source="manual")
    db_session.add(entry)
    await db_session.flush()
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner, role="VOORBEELDROL")
    assert (line.role, line.role_id) == ("Voorbeeldrol", entry.id)
    await _same(db_session, assignment.id)


async def test_two_new_lines_with_one_new_role_make_one_entry(db_session, owner):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    first = await _personnel(db_session, assignment, owner, role="Eenmalige rol")
    second = await _personnel(db_session, assignment, owner, role="eenmalige ROL")
    assert first.role_id == second.role_id
    await _same(db_session, assignment.id)


async def test_a_line_without_a_name_is_refused_before_any_fact(db_session, owner):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    with pytest.raises(DomainValidationError, match="Kies een rol"):
        await _personnel(db_session, assignment, owner, description="  ", role=" ")
    assert await _facts(db_session, assignment.id) == ["assignment_created"]

    line = await _personnel(db_session, assignment, owner)
    facts = await _facts(db_session, assignment.id)
    with pytest.raises(DomainValidationError, match="Kies een rol"):
        await assignments.update_budget_line(
            db_session, line.id, actor=owner, description=""
        )
    assert await _facts(db_session, assignment.id) == facts
    await _same(db_session, assignment.id)


async def test_changing_a_line_says_only_what_changes(db_session, owner):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner, description="Oud")
    started_from = line.version

    await assignments.update_budget_line(
        db_session, line.id, actor=owner, description="Nieuw", fte=Decimal("0.800")
    )
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[-1].fact == "budget_line_changed"
    assert grams[-1].fields["changes"] == {"detail": "Nieuw"}
    assert line.version == started_from + 1
    await _same(db_session, assignment.id)

    await db_session.flush()
    row = await db_session.scalar(
        select(StreamEvent)
        .where(
            StreamEvent.type == "budget_line.updated",
            StreamEvent.subject_id == str(line.id),
        )
        .order_by(StreamEvent.seq.desc())
    )
    assert row.new_value == {"description": "Nieuw", "fte": "0.8"}


async def test_a_change_that_changes_nothing_on_a_line_is_no_fact(db_session, owner):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner, fte=Decimal("0.8"))
    facts = await _facts(db_session, assignment.id)
    await assignments.update_budget_line(
        db_session, line.id, actor=owner, fte=Decimal("0.800")
    )
    await db_session.flush()
    assert await _facts(db_session, assignment.id) == facts
    await _same(db_session, assignment.id)


async def test_changing_and_clearing_a_role(db_session, owner):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner, role="Eerste rol")
    first = line.role_id

    await assignments.update_budget_line(
        db_session, line.id, actor=owner, role="Tweede rol"
    )
    assert line.role == "Tweede rol"
    assert line.role_id != first
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[-1].fields["changes"] == {
        "role": "Tweede rol",
        "role_id": str(line.role_id),
    }
    await _same(db_session, assignment.id)

    await assignments.update_budget_line(db_session, line.id, actor=owner, role=None)
    assert (line.role, line.role_id) == (None, None)
    await _same(db_session, assignment.id)


async def test_a_period_of_its_own_and_back(db_session, owner, other):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner)
    allocation = await assignments.add_allocation(
        db_session, line.id, other.id, fte_pct=Decimal("50"), actor=owner
    )
    await assignments.update_budget_line(
        db_session,
        line.id,
        actor=owner,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 3, 31),
    )
    assert line.period_source == "own"
    await db_session.refresh(allocation)
    assert allocation.start_date == date(2026, 2, 1)
    await _same(db_session, assignment.id)

    await assignments.update_budget_line(
        db_session, line.id, actor=owner, period_source="assignment"
    )
    assert (line.start_date, line.end_date) == (START, END)
    await _same(db_session, assignment.id)


async def test_removing_a_line_is_a_fact_before_its_audit_row(db_session, owner):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await assignments.add_budget_line(
        db_session,
        assignment.id,
        description="Hosting",
        kind="fixed",
        amount_cents=150000,
        year=2026,
        actor=owner,
    )
    line_id = line.id
    await assignments.delete_budget_line(db_session, line_id, actor=owner)
    await db_session.flush()
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[-1].fact == "budget_line_removed"
    assert await db_session.get(BudgetLine, line_id) is None
    await _same(db_session, assignment.id)

    row = await db_session.scalar(
        select(StreamEvent).where(
            StreamEvent.type == "budget_line.deleted",
            StreamEvent.subject_id == str(line_id),
        )
    )
    assert row.case_id == assignment.id
    assert row.old_value["description"] == "Hosting"
    assert row.seq > grams[-1].seq


# -- the intended person -------------------------------------------------------


async def _reservations(db_session, line_id: UUID) -> list[Allocation]:
    rows = await db_session.scalars(
        select(Allocation).where(
            Allocation.budget_line_id == line_id, Allocation.from_budget.is_(True)
        )
    )
    return list(rows)


async def test_adding_a_line_with_a_person_is_one_fact(db_session, owner, other):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    facts = await _facts(db_session, assignment.id)
    line = await budget_intent.add_line(
        db_session,
        assignment.id,
        actor=owner,
        intended_person_id=other.id,
        description="Voorbeeldregel",
        kind="personnel",
        fte=Decimal("0.5"),
        rate_category="D",
    )
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert [gram.fact for gram in grams] == [*facts, "budget_line_added"]
    assert grams[-1].fields["line"]["intended_person_id"] == str(other.id)
    assert line.intended_person_id == other.id
    assert len(await _reservations(db_session, line.id)) == 1
    await _same(db_session, assignment.id)

    await db_session.flush()
    rows = await _rows_of_type(db_session, assignment.id)
    assert [row[0] for row in rows][-3:] == [
        "budget_line.created",
        "budget_line.updated",
        "allocation.created",
    ]
    assert rows[-2][1] == {"intended_person_id": str(other.id)}


async def test_changing_a_line_and_its_person_is_one_fact(
    db_session, owner, other, create_person
):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await budget_intent.add_line(
        db_session,
        assignment.id,
        actor=owner,
        intended_person_id=other.id,
        description="Voorbeeldregel",
        kind="personnel",
        fte=Decimal("0.5"),
        rate_category="D",
    )
    first = (await _reservations(db_session, line.id))[0]
    started_from = line.version
    facts = await _facts(db_session, assignment.id)
    third = await create_person("derde@example.org", name="Derde Voorbeeld")

    await budget_intent.update_line(
        db_session,
        line.id,
        actor=owner,
        fte=Decimal("0.6"),
        intended_person_id=third.id,
    )
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert [gram.fact for gram in grams] == [*facts, "budget_line_changed"]
    assert grams[-1].fields["changes"] == {
        "fte": "0.6",
        "intended_person_id": str(third.id),
    }
    assert line.version == started_from + 1
    reservations = await _reservations(db_session, line.id)
    assert [item.person_id for item in reservations] == [third.id]
    assert reservations[0].id != first.id
    await _same(db_session, assignment.id)


async def test_a_later_change_of_person_is_a_fact_of_its_own(
    db_session, owner, other, create_person
):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner)
    assert await _reservations(db_session, line.id) == []

    await budget_intent.update_line(
        db_session, line.id, actor=owner, intended_person_id=other.id
    )
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[-1].fact == "budget_line_changed"
    assert grams[-1].fields["changes"] == {"intended_person_id": str(other.id)}
    assert len(await _reservations(db_session, line.id)) == 1
    await _same(db_session, assignment.id)

    # The same person again: nothing to establish.
    facts = await _facts(db_session, assignment.id)
    await budget_intent.update_line(
        db_session, line.id, actor=owner, intended_person_id=other.id
    )
    assert await _facts(db_session, assignment.id) == facts

    # Taken off again: a fact, and the reservation goes.
    await budget_intent.update_line(
        db_session, line.id, actor=owner, intended_person_id=None
    )
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    assert grams[-1].fields["changes"] == {"intended_person_id": None}
    assert await _reservations(db_session, line.id) == []
    await _same(db_session, assignment.id)


async def test_a_person_who_cannot_be_named_is_refused_before_any_fact(
    db_session, owner, create_person
):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner)
    gone = await create_person("weg@example.org", name="Weg Voorbeeld")
    gone.is_active = False
    await db_session.flush()
    facts = await _facts(db_session, assignment.id)
    with pytest.raises(DomainValidationError, match="niet meer actief"):
        await budget_intent.update_line(
            db_session,
            line.id,
            actor=owner,
            fte=Decimal("0.6"),
            intended_person_id=gone.id,
        )
    assert await _facts(db_session, assignment.id) == facts
    assert line.fte == Decimal("0.800")


async def test_a_reservation_that_waited_for_the_period(db_session, owner, other):
    assignment = await _new(db_session, owner)
    line = await budget_intent.add_line(
        db_session,
        assignment.id,
        actor=owner,
        intended_person_id=other.id,
        description="Voorbeeldregel",
        kind="personnel",
        fte=Decimal("0.5"),
        rate_category="D",
    )
    assert await _reservations(db_session, line.id) == []
    await _same(db_session, assignment.id)

    await assignments.update_assignment(
        db_session, assignment.id, actor=owner, start_date=START, end_date=END
    )
    assert len(await _reservations(db_session, line.id)) == 1
    assert (line.start_date, line.end_date) == (START, END)
    await _same(db_session, assignment.id)


# -- merging roles -------------------------------------------------------------


async def test_merging_roles_is_one_fact_per_assignment(db_session, owner):
    first = await _new(db_session, owner, start_date=START, end_date=END)
    second = await _new(db_session, owner, start_date=START, end_date=END)
    untouched = await _new(db_session, owner, start_date=START, end_date=END)
    lines = [
        await _personnel(db_session, first, owner, role="Weg rol"),
        await _personnel(db_session, first, owner, role="Weg rol", position=2),
        await _personnel(db_session, second, owner, role="Weg rol"),
    ]
    other_line = await _personnel(db_session, untouched, owner, role="Blijf rol")
    source, target = lines[0].role_id, other_line.role_id
    versions = [line.version for line in lines]
    facts_of_untouched = await _facts(db_session, untouched.id)

    merged, moved = await catalogue_roles.merge_roles(
        db_session, source, target, actor=owner
    )

    assert merged.id == target
    assert moved == 3
    assert (await _facts(db_session, first.id))[-1] == "budget_lines_role_merged"
    assert (await _facts(db_session, second.id))[-1] == "budget_lines_role_merged"
    assert await _facts(db_session, untouched.id) == facts_of_untouched
    first_grams = await ChronicleRepository(db_session).grams(first.id)
    assert first_grams[-1].fields == {
        "line_ids": [str(lines[0].id), str(lines[1].id)],
        "role_id": str(target),
        "role": "Blijf rol",
    }
    for line, version in zip(lines, versions, strict=True):
        assert (line.role_id, line.role) == (target, "Blijf rol")
        assert line.version == version + 1
    assert await db_session.get(CatalogueRole, source) is None
    for case in (first, second, untouched):
        await _same(db_session, case.id)

    row = await db_session.scalar(
        select(StreamEvent).where(
            StreamEvent.type == "catalogue_role.deleted",
            StreamEvent.subject_id == str(source),
        )
    )
    assert row.new_value["budget_lines_rewritten"] == 3


async def test_merging_a_role_without_lines_is_no_fact(db_session, owner):
    source = CatalogueRole(id=uuid4(), name="Ongebruikt", source="manual")
    target = CatalogueRole(id=uuid4(), name="Doelrol", source="manual")
    db_session.add_all([source, target])
    await db_session.flush()
    source_id = source.id
    _, moved = await catalogue_roles.merge_roles(
        db_session, source_id, target.id, actor=owner
    )
    assert moved == 0
    assert await db_session.get(CatalogueRole, source_id) is None


# -- the whole of it -----------------------------------------------------------


async def test_nothing_goes_around_the_chronicle(
    db_session, owner, other, organisation, create_person
):
    guard.install()
    third = await create_person("derde@example.org", name="Derde Voorbeeld")
    with guard.in_request(db_session) as unit:
        draft = await _new(db_session, owner, notes="Voorbeeldnotitie")
        requested, _ = await assignments.create_assignment_request(
            db_session,
            name="Voorbeeldaanvraag",
            contractor_organisation_id=organisation.id,
            actor=owner,
        )
        received = await assignments.receive_assignment_request(
            db_session,
            uri=f"{INSTANCE}/id/opdracht/{uuid4()}",
            name="Voorbeeldaanvraag",
            client_organisation_id=organisation.id,
        )
        await assignments.update_assignment(
            db_session, draft.id, actor=owner, start_date=START, end_date=END
        )
        await assignments.share_with_instance(db_session, draft, INSTANCE, actor=owner)
        await assignments.set_assignment_role(
            db_session, draft.id, other.id, "manager", actor=owner
        )
        await assignments.set_assignment_role(
            db_session, draft.id, other.id, "owner", actor=owner
        )
        await assignments.set_assignment_role(
            db_session, draft.id, third.id, "manager", actor=other
        )
        await assignments.remove_assignment_role(
            db_session, draft.id, third.id, actor=other
        )
        line = await budget_intent.add_line(
            db_session,
            draft.id,
            actor=other,
            intended_person_id=third.id,
            description="Voorbeeldregel",
            kind="personnel",
            role="Rol om de kroniek",
            fte=Decimal("0.5"),
            rate_category="D",
        )
        await budget_intent.update_line(
            db_session, line.id, actor=other, intended_person_id=other.id
        )
        await budget_intent.update_line(
            db_session,
            line.id,
            actor=other,
            role="Andere rol om de kroniek",
            intended_person_id=None,
        )
        old_role, new_role = line.role_id, None
        kept = await _personnel(db_session, draft, other, role="Blijvende rol")
        new_role = kept.role_id
        await catalogue_roles.merge_roles(db_session, old_role, new_role, actor=owner)
        await assignments.update_assignment(
            db_session, draft.id, actor=other, end_date=date(2026, 6, 30)
        )
        await budget_intent.delete_line(db_session, line.id, actor=other)
        await assignments.transition(db_session, draft.id, "cancelled", actor=other)
        await db_session.flush()
    assert unit.findings == []
    assert unit.cases == {draft.id, requested.id, received.id}
    for case in (draft, requested, received):
        await _same(db_session, case.id)


# -- the fold ------------------------------------------------------------------


async def test_the_fold_at_every_step_holds_what_was_true_then(db_session, owner):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner, fte=Decimal("0.8"))
    await assignments.update_budget_line(
        db_session, line.id, actor=owner, fte=Decimal("0.4")
    )
    grams = await ChronicleRepository(db_session).grams(assignment.id)
    at_add = fold(grams, upto=grams[1].seq).table("budget_line")[str(line.id)]
    at_change = fold(grams, upto=grams[2].seq).table("budget_line")[str(line.id)]
    assert (at_add["fte"], at_change["fte"]) == ("0.8", "0.4")


# -- findings of the review ----------------------------------------------------


async def test_a_conflict_after_a_role_merge_names_who_merged(db_session, owner, other):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner, role="Weg rol")
    await assignments.update_budget_line(
        db_session, line.id, actor=owner, fte=Decimal("0.6")
    )
    keep = await _personnel(db_session, assignment, owner, role="Blijf rol", position=2)
    started_from = line.version

    await catalogue_roles.merge_roles(
        db_session, line.role_id, keep.role_id, actor=other
    )

    by, at = await stale.last_change(db_session, line.id)
    assert by == "Wim Voorbeeld" and at is not None
    with stale.expecting(f'"{line.id}:{started_from}"'):
        with pytest.raises(stale.StaleWriteError) as caught:
            await assignments.update_budget_line(
                db_session, line.id, actor=owner, fte=Decimal("0.7")
            )
    assert caught.value.changed_by == "Wim Voorbeeld"


async def test_a_stale_save_with_an_unusable_person_is_a_conflict(
    db_session, owner, other, create_person
):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner)
    started_from = line.version
    await assignments.update_budget_line(
        db_session, line.id, actor=other, fte=Decimal("0.5")
    )
    gone = await create_person("weg2@example.org", name="Weg Voorbeeld")
    gone.is_active = False
    await db_session.flush()
    facts = await _facts(db_session, assignment.id)

    for person_id in (gone.id, uuid4()):
        with stale.expecting(f'"{line.id}:{started_from}"'):
            with pytest.raises(stale.StaleWriteError):
                await budget_intent.update_line(
                    db_session,
                    line.id,
                    actor=owner,
                    fte=Decimal("0.6"),
                    intended_person_id=person_id,
                )
    assert await _facts(db_session, assignment.id) == facts


async def test_a_nameless_change_meets_the_other_guards_first(db_session, owner, other):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await assignments.add_budget_line(
        db_session,
        assignment.id,
        description="Hosting",
        kind="fixed",
        amount_cents=150000,
        year=2026,
        actor=owner,
    )
    facts = await _facts(db_session, assignment.id)
    with pytest.raises(DomainValidationError, match="buiten de looptijd"):
        await assignments.update_budget_line(
            db_session, line.id, actor=owner, year=2031, description=""
        )
    with pytest.raises(DomainValidationError, match="Kies een rol"):
        await assignments.update_budget_line(
            db_session, line.id, actor=owner, description=" "
        )
    assert await _facts(db_session, assignment.id) == facts


async def test_a_nameless_change_in_a_closed_year_is_a_closed_year(
    db_session, owner, other
):
    await add_rate_card(db_session, 2026, owner)
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(db_session, assignment, owner)
    await rates.set_rate_card_status(db_session, 2026, "closed", actor=owner)
    with pytest.raises(ClosedYearError):
        await assignments.update_budget_line(
            db_session, line.id, actor=owner, role=None, description=""
        )


async def test_a_line_fact_holds_the_name_of_the_line_at_that_moment(
    db_session, owner, other
):
    assignment = await _new(db_session, owner, start_date=START, end_date=END)
    line = await _personnel(
        db_session, assignment, owner, role="Productmanager", description='Zoë "A"'
    )
    await assignments.update_budget_line(
        db_session, line.id, actor=owner, description="  Nieuw  "
    )
    await budget_intent.update_line(
        db_session, line.id, actor=owner, intended_person_id=other.id
    )
    fixed = await assignments.add_budget_line(
        db_session,
        assignment.id,
        description="Hosting",
        kind="fixed",
        amount_cents=150000,
        year=2026,
        actor=owner,
    )
    await assignments.delete_budget_line(db_session, fixed.id, actor=owner)

    grams = await ChronicleRepository(db_session).grams(assignment.id)
    named = [
        (gram.fact, gram.fields["name"])
        for gram in grams
        if gram.fact in ("budget_line_changed", "budget_line_removed")
    ]
    assert named == [
        ("budget_line_changed", "Productmanager:   Nieuw  "),
        ("budget_line_changed", "Productmanager:   Nieuw  "),
        ("budget_line_removed", "Hosting"),
    ]
    await _same(db_session, assignment.id)


@pytest.fixture
async def cast(db_session, create_person):
    return await make_cast(db_session, create_person)


@pytest.fixture
def walk(client, db_session, cast):
    register_task_handlers()
    return Walk(client, db_session, cast)


async def test_starting_an_internal_assignment_is_one_moment(walk):
    await walk.begin(0, kind="internal", client_organisation_id=None)
    await walk.step(
        "regel",
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/budget-lines",
        json=line_body(),
    )
    before = len(await walk.moments(walk.cast.beheerder))

    await walk.step(
        "starten",
        walk.cast.owner,
        "post",
        f"/api/assignments/{walk.assignment_id}/transition",
        json={"target": "in_progress"},
    )

    moments = await walk.moments(walk.cast.beheerder)
    assert [item["title"] for item in moments[before:]] == [
        "Opdracht in uitvoering gezet"
    ]
    assert "Akkoord vastgelegd" not in [item["title"] for item in moments]
    started = walk.seen[-1]
    assert started.assignment["status"] == "in_progress"
    assert started.course is not None
    await walk.check_every_look_back()
    stand = await walk.stand(started.seq)
    assert stand["assignment"]["status"] == "in_progress"
    assert stand["course"]["current_key"] == started.course["current_key"]
    report = await differences(walk.db, UUID(walk.assignment_id))
    assert report.checked and report.differences == []


async def test_an_internal_assignment_still_cannot_start_without_a_date(
    db_session, owner
):
    assignment = await _new(db_session, owner, kind="internal")
    with pytest.raises(DomainValidationError, match="begindatum"):
        await assignments.transition(
            db_session, assignment.id, "in_progress", actor=owner
        )
    assert await _facts(db_session, assignment.id) == ["assignment_created"]
    assert "in_progress" in assignments.allowed_transitions(assignment)
    external = await _new(db_session, owner, kind="external")
    assert "in_progress" not in assignments.allowed_transitions(external)
