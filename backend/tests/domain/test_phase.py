"""The phase of an assignment, the verbal agreement, and what each allows."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from grip.calc import Month
from grip.models.assignment import ASSIGNMENT_STATUSES
from grip.models.audit_log import AuditLog
from grip.services import assignments, events, month_close, phase, staffing
from grip.services.errors import DomainValidationError, IllegalTransitionError
from grip.services.phase import Commitment, Phase

NOTE = "Directeur gaf akkoord in het overleg van 3 maart."


def test_every_status_has_a_phase_a_commitment_and_a_label():
    for status in ASSIGNMENT_STATUSES:
        assert isinstance(phase.phase_of(status), Phase)
        assert isinstance(phase.commitment_of(status), Commitment)
        assert phase.STATUS_LABELS[status]
    assert set(phase.STATUS_LABELS) == set(ASSIGNMENT_STATUSES)
    with pytest.raises(ValueError):
        phase.phase_of("klaar")


def test_phases():
    assert phase.statuses_in_phase(Phase.POTENTIAL) == {
        "draft",
        "requested",
        "quoted",
        "verbally_agreed",
        # A rejected quote does not close the assignment: a new one can follow.
        "rejected",
    }
    assert phase.statuses_in_phase(Phase.ACTIVE) == {"accepted", "in_progress"}
    assert phase.statuses_in_phase(Phase.CLOSED) == {
        "completed",
        "accounted",
        "cancelled",
    }
    assert phase.statuses_in_phase(Phase.POTENTIAL, Phase.ACTIVE) == (
        set(ASSIGNMENT_STATUSES) - phase.statuses_in_phase(Phase.CLOSED)
    )


def test_commitment_for_forecasts():
    assert phase.statuses_with_commitment(Commitment.PIPELINE) == {
        "draft",
        "requested",
        "quoted",
        "rejected",
    }
    assert phase.statuses_with_commitment(Commitment.VERBAL) == {"verbally_agreed"}
    assert phase.statuses_with_commitment(Commitment.COMMITTED) == {
        "accepted",
        "in_progress",
        "completed",
        "accounted",
    }
    assert phase.statuses_with_commitment(Commitment.NONE) == {"cancelled"}


def test_labels_and_counterparty_view():
    assert phase.status_label("draft") == "In voorbereiding"
    assert phase.status_label("verbally_agreed") == "Mondeling akkoord"
    assert phase.counterparty_status("verbally_agreed") == "quoted"
    for status in set(ASSIGNMENT_STATUSES) - {"verbally_agreed"}:
        assert phase.counterparty_status(status) == status


def test_what_a_status_allows():
    assert [s for s in ASSIGNMENT_STATUSES if phase.allows_month_close(s)] == [
        "verbally_agreed",
        "accepted",
        "in_progress",
        "completed",
    ]
    assert [s for s in ASSIGNMENT_STATUSES if phase.allows_billing(s)] == [
        "accepted",
        "in_progress",
        "completed",
        "accounted",
    ]
    assert [s for s in ASSIGNMENT_STATUSES if phase.is_tentative(s)] == [
        "draft",
        "requested",
        "quoted",
        "verbally_agreed",
        "rejected",
    ]


async def test_creation_needs_only_a_name(db_session, beheerder):
    assignment = await assignments.create_assignment(
        db_session, name="Mogelijke opdracht", actor=beheerder
    )

    assert assignment.status == "draft"
    assert phase.assignment_phase(assignment) is Phase.POTENTIAL
    assert assignment.client_organisation_id is None
    assert assignment.start_date is None and assignment.end_date is None
    assert assignment.quoted_amount_cents is None


async def test_external_assignment_needs_a_client_before_it_moves_on(
    db_session, beheerder, client_org
):
    assignment = await assignments.create_assignment(
        db_session, name="Mogelijke opdracht", actor=beheerder
    )
    with pytest.raises(DomainValidationError, match="opdrachtgever"):
        await assignments.transition(
            db_session, assignment.id, "quoted", actor=beheerder
        )
    assert assignment.status == "draft"

    await assignments.update_assignment(
        db_session, assignment.id, actor=beheerder, client_organisation_id=client_org.id
    )
    await assignments.transition(db_session, assignment.id, "quoted", actor=beheerder)
    assert assignment.status == "quoted"


async def test_internal_assignment_needs_no_client(db_session, beheerder):
    assignment = await assignments.create_assignment(
        db_session, name="Eigen ontwikkeling", kind="internal", actor=beheerder
    )
    await assignments.transition(db_session, assignment.id, "accepted", actor=beheerder)
    assert assignment.status == "accepted"


async def test_in_progress_needs_a_start_date(db_session, beheerder, make_assignment):
    assignment = await make_assignment(start_date=None)
    for step in ("quoted", "accepted"):
        await assignments.transition(db_session, assignment.id, step, actor=beheerder)

    with pytest.raises(DomainValidationError, match="begindatum"):
        await assignments.transition(
            db_session, assignment.id, "in_progress", actor=beheerder
        )
    await assignments.update_assignment(
        db_session, assignment.id, actor=beheerder, start_date=date(2026, 1, 1)
    )
    await assignments.transition(
        db_session, assignment.id, "in_progress", actor=beheerder
    )
    assert assignment.status == "in_progress"


async def test_a_rejected_quote_leaves_the_assignment_open_until_someone_ends_it(
    db_session, beheerder, make_assignment
):
    assignment = await make_assignment()
    for step in ("quoted", "rejected"):
        await assignments.transition(db_session, assignment.id, step, actor=beheerder)
    # Still a potential assignment: a new quote can follow.
    assert phase.assignment_phase(assignment) is Phase.POTENTIAL
    assert phase.status_label(assignment.status) == "Offerte afgewezen"
    assert "quoted" in assignments.allowed_transitions(assignment)

    # Ending it is a decision of its own, with a reason.
    with pytest.raises(DomainValidationError, match="waarom"):
        await assignments.transition(
            db_session, assignment.id, "cancelled", actor=beheerder
        )
    await assignments.transition(
        db_session,
        assignment.id,
        "cancelled",
        actor=beheerder,
        reason="De opdrachtgever heeft geen budget.",
    )
    assert phase.assignment_phase(assignment) is Phase.CLOSED


async def test_verbal_agreement_needs_a_note_and_is_audited(
    db_session, beheerder, make_assignment
):
    assignment = await make_assignment()
    await assignments.transition(db_session, assignment.id, "quoted", actor=beheerder)

    for empty in (None, "", "   "):
        with pytest.raises(DomainValidationError, match="mondeling akkoord"):
            await assignments.transition(
                db_session,
                assignment.id,
                "verbally_agreed",
                actor=beheerder,
                reason=empty,
            )
    await assignments.transition(
        db_session, assignment.id, "verbally_agreed", actor=beheerder, reason=NOTE
    )
    await db_session.flush()

    assert assignment.status == "verbally_agreed"
    assert assignment.verbal_agreement_note == NOTE
    assert assignment.verbal_agreement_at is not None
    assert phase.assignment_phase(assignment) is Phase.POTENTIAL
    rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity == "assignment",
                AuditLog.entity_id == str(assignment.id),
            )
        )
    ).scalars()
    agreed = [r for r in rows if (r.new_value or {}).get("status") == "verbally_agreed"]
    assert len(agreed) == 1
    assert agreed[0].old_value == {"status": "quoted"}
    assert agreed[0].new_value["reason"] == NOTE
    assert agreed[0].actor_id == beheerder.id


async def test_verbal_agreement_is_optional_and_only_after_a_quote(
    db_session, beheerder, make_assignment
):
    direct = await make_assignment("Direct akkoord")
    await assignments.transition(db_session, direct.id, "quoted", actor=beheerder)
    await assignments.transition(db_session, direct.id, "accepted", actor=beheerder)
    assert direct.status == "accepted"

    early = await make_assignment("Te vroeg")
    with pytest.raises(IllegalTransitionError):
        await assignments.transition(
            db_session, early.id, "verbally_agreed", actor=beheerder, reason=NOTE
        )

    via = await make_assignment("Via mondeling akkoord")
    await assignments.transition(db_session, via.id, "quoted", actor=beheerder)
    await assignments.transition(
        db_session, via.id, "verbally_agreed", actor=beheerder, reason=NOTE
    )
    assert assignments.allowed_transitions(via) == {
        "accepted",
        "quoted",
        "rejected",
        "cancelled",
    }
    with pytest.raises(IllegalTransitionError):
        await assignments.transition(db_session, via.id, "in_progress", actor=beheerder)
    await assignments.transition(db_session, via.id, "accepted", actor=beheerder)
    assert via.status == "accepted"
    # The note stays, as the trail of how the assignment started.
    assert via.verbal_agreement_note == NOTE


async def test_another_instance_never_sees_the_verbal_agreement(
    db_session, beheerder, make_assignment
):
    seen = []

    async def handler(session, event_type, payload):
        seen.append(payload)

    events.register_handler(events.ASSIGNMENT_STATUS_CHANGED, handler)
    assignment = await make_assignment()
    await assignments.transition(db_session, assignment.id, "quoted", actor=beheerder)
    await assignments.transition(
        db_session, assignment.id, "verbally_agreed", actor=beheerder, reason=NOTE
    )
    await assignments.transition(db_session, assignment.id, "quoted", actor=beheerder)
    await assignments.transition(
        db_session, assignment.id, "verbally_agreed", actor=beheerder, reason=NOTE
    )
    await assignments.transition(db_session, assignment.id, "accepted", actor=beheerder)

    assert [(p["old_status"], p["new_status"]) for p in seen] == [
        ("draft", "quoted"),
        ("quoted", "accepted"),
    ]
    assert all("verbally" not in str(p) and NOTE not in str(p) for p in seen)


@pytest.fixture
async def staffed(
    db_session, rate_cards, beheerder, make_person, make_assignment, add_personnel_line
):
    person = await make_person(14)
    assignment = await make_assignment(start_date=date(2026, 1, 1))
    line = await add_personnel_line(assignment, fte="1")
    allocation = await assignments.add_allocation(
        db_session,
        line.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
        fte_pct=Decimal(80),
        actor=beheerder,
    )
    return assignment, allocation, person


async def test_staffing_on_a_potential_assignment_is_tentative(
    db_session, staffed, beheerder
):
    assignment, allocation, person = staffed

    async def one():
        rows = await staffing.staffed_allocations(db_session, person_ids=[person.id])
        assert [r.allocation_id for r in rows] == [allocation.id]
        return rows[0]

    row = await one()
    assert (row.tentative, row.verbally_agreed, row.phase) == (
        True,
        False,
        Phase.POTENTIAL,
    )
    await assignments.transition(db_session, assignment.id, "quoted", actor=beheerder)
    await assignments.transition(
        db_session, assignment.id, "verbally_agreed", actor=beheerder, reason=NOTE
    )
    row = await one()
    assert (row.tentative, row.verbally_agreed) == (True, True)
    await assignments.transition(db_session, assignment.id, "accepted", actor=beheerder)
    row = await one()
    assert (row.tentative, row.verbally_agreed, row.phase) == (
        False,
        False,
        Phase.ACTIVE,
    )

    # A period filter, and inzet that will not happen is left out.
    assert (
        await staffing.staffed_allocations(
            db_session, assignment_ids=[assignment.id], start=date(2026, 7, 1)
        )
        == []
    )
    await assignments.transition(
        db_session, assignment.id, "cancelled", actor=beheerder
    )
    assert await staffing.staffed_allocations(db_session, person_ids=[person.id]) == []
    assert (
        len(
            await staffing.staffed_allocations(
                db_session, person_ids=[person.id], include_closed=True
            )
        )
        == 1
    )


async def test_verbal_agreement_allows_closing_months_but_not_billing(
    db_session, staffed, beheerder
):
    assignment, allocation, _ = staffed
    jan = Month(2026, 1)

    # Before any agreement there is no month to close.
    with pytest.raises(DomainValidationError, match="In voorbereiding"):
        await month_close.close_month(db_session, assignment.id, jan, actor=beheerder)
    await assignments.transition(db_session, assignment.id, "quoted", actor=beheerder)
    with pytest.raises(DomainValidationError, match="Offerte gemaakt"):
        await month_close.close_month(db_session, assignment.id, jan, actor=beheerder)

    await assignments.transition(
        db_session, assignment.id, "verbally_agreed", actor=beheerder, reason=NOTE
    )
    await month_close.close_month(
        db_session,
        assignment.id,
        jan,
        actor=beheerder,
        established={allocation.id: Decimal(60)},
    )
    with pytest.raises(DomainValidationError, match="mondeling akkoord"):
        await month_close.billing_data(db_session, assignment.id, jan)
    with pytest.raises(DomainValidationError, match="mondeling akkoord"):
        await month_close.create_billing_export(
            db_session, assignment.id, jan, actor=beheerder
        )

    await assignments.transition(db_session, assignment.id, "accepted", actor=beheerder)
    data = await month_close.billing_data(db_session, assignment.id, jan)
    export = await month_close.create_billing_export(
        db_session, assignment.id, jan, actor=beheerder
    )
    assert data.total_cents == export.total_cents == 10_800_00
