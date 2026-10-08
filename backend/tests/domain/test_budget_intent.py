"""The intended person of a budget line: derivation and reservation."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from grip.calc import Month
from grip.models.assignment import Allocation
from grip.models.audit_log import AuditLog
from grip.models.person_standing import PersonStanding
from grip.services import (
    assignments,
    budget_intent,
    month_close,
    pricing,
    rates,
    staffing,
)
from grip.services.errors import DomainValidationError
from grip.services.periods import PeriodChangeBlockedError

YEAR = (date(2026, 1, 1), date(2026, 12, 31))


async def _allocations(db_session, line_id) -> list[Allocation]:
    result = await db_session.execute(
        select(Allocation)
        .where(Allocation.budget_line_id == line_id)
        .order_by(Allocation.created_at, Allocation.id)
    )
    return list(result.scalars())


async def _add(db_session, assignment, actor, person=None, **kwargs):
    values = dict(
        description="Productmanager",
        kind="personnel",
        role="Productmanager",
        fte=Decimal("0.8"),
        start_date=YEAR[0],
        end_date=YEAR[1],
    )
    values.update(kwargs)
    return await budget_intent.add_line(
        db_session,
        assignment.id,
        actor=actor,
        intended_person_id=person.id if person else None,
        **values,
    )


async def _intent(db_session, line):
    return (await budget_intent.line_intents(db_session, [line]))[line.id]


# -- derivation -----------------------------------------------------------------


async def test_person_implies_category_rate_and_budget(
    db_session, rate_cards, make_person, make_assignment
):
    person = await make_person(14)  # scale 14 bills in category D
    assignment = await make_assignment()

    derived = await budget_intent.derive(
        db_session,
        assignment.id,
        person.id,
        start_date=YEAR[0],
        end_date=YEAR[1],
        fte=Decimal("0.8"),
    )

    assert derived.rate_category == "D"
    assert derived.monthly_rate_by_year == {2026: 18_000_00}
    assert derived.budgeted_cents == 172_800_00
    assert derived.period_proposed is False
    assert derived.notes == () and derived.category_notes == ()


async def test_period_comes_from_the_assignment_and_size_from_the_room(
    db_session, rate_cards, make_person, make_assignment
):
    person = await make_person(14)
    assignment = await make_assignment(
        start_date=date(2026, 3, 1), end_date=date(2026, 8, 31)
    )

    derived = await budget_intent.derive(db_session, assignment.id, person.id)

    assert (derived.start_date, derived.end_date) == (
        date(2026, 3, 1),
        date(2026, 8, 31),
    )
    assert derived.period_source == "assignment" and derived.period_proposed is True
    assert derived.period_source_text == "periode van de opdracht"
    # Nothing planned yet: all of the person is free.
    assert derived.free_pct == Decimal(100)
    assert derived.fte == Decimal("1.00")
    assert derived.fte_source_text == (
        "vrij in deze periode: 100%. Uitgegaan van een voltijds aanstelling"
    )
    # With the proposed size the line can be priced.
    assert derived.budgeted_cents == 6 * 18_000_00
    assert derived.notes == ()


async def test_size_is_the_room_left_in_the_busiest_month(
    db_session, rate_cards, beheerder, make_person, make_assignment, accept
):
    person = await make_person(14)
    firm = await make_assignment("Opdracht Vast")
    await accept(firm)
    maybe = await make_assignment("Opdracht Misschien")
    for assignment, pct, end in (
        (firm, 40, date(2026, 12, 31)),
        (maybe, 20, date(2026, 6, 30)),
    ):
        line = await budget_intent.add_line(
            db_session,
            assignment.id,
            actor=beheerder,
            description="Rol",
            kind="personnel",
            role="Developer",
            fte=Decimal(1),
            rate_category="D",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        await assignments.add_allocation(
            db_session,
            line.id,
            person.id,
            start_date=date(2026, 1, 1),
            end_date=end,
            fte_pct=Decimal(pct),
            actor=beheerder,
        )
    target = await make_assignment("Opdracht Nieuw")

    async def only_firm(assignment_id):
        return assignment_id == firm.id

    derived = await budget_intent.derive(
        db_session,
        target.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        may_see_assignment=only_firm,
    )
    # Firm and tentative inzet both count: 40 + 20 in the first half year.
    assert derived.free_pct == Decimal(40)
    assert derived.fte == Decimal("0.40")
    assert derived.fte_source_text == (
        "vrij in deze periode: 40%; al ingezet op Opdracht Vast (40%), andere "
        "opdrachten. Uitgegaan van een voltijds aanstelling"
    )
    assert "Opdracht Misschien" not in " ".join(derived.summary)
    assert {b.assignment_name: (b.pct, b.tentative) for b in derived.busy_on} == {
        "Opdracht Vast": (Decimal(40), False),
        "Opdracht Misschien": (Decimal(20), True),
    }

    # Who may see both gets both names, the tentative one marked.
    everything = await budget_intent.derive(
        db_session,
        target.id,
        person.id,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 12, 31),
    )
    assert everything.fte == Decimal("0.60")
    assert "Opdracht Misschien" not in everything.fte_source_text  # ended in June
    first_half = await budget_intent.derive(
        db_session,
        target.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
    )
    assert "Opdracht Misschien (20%, onder voorbehoud)" in first_half.fte_source_text


async def test_fully_booked_person_gets_no_size_and_a_note(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14)
    busy = await make_assignment("Opdracht Vol")
    line = await budget_intent.add_line(
        db_session,
        busy.id,
        actor=beheerder,
        intended_person_id=person.id,
        description="Rol",
        kind="personnel",
        role="Developer",
        fte=Decimal(1),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    target = await make_assignment("Opdracht Nieuw")

    derived = await budget_intent.derive(
        db_session,
        target.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    assert derived.free_pct == Decimal(0) and derived.fte is None
    assert any("volledig ingezet" in note for note in derived.notes)

    # Editing the line that holds the reservation: its own inzet does not count.
    own = await budget_intent.derive(
        db_session,
        busy.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        exclude_line_id=line.id,
    )
    assert own.free_pct == Decimal(100) and own.fte == Decimal("1.00")
    assert own.busy_on == ()


async def test_without_any_period_the_person_side_proposes_one(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14)
    busy = await make_assignment("Opdracht Vol")
    await budget_intent.add_line(
        db_session,
        busy.id,
        actor=beheerder,
        intended_person_id=person.id,
        description="Rol",
        kind="personnel",
        role="Developer",
        fte=Decimal(1),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
    )
    fresh = await make_assignment("Mogelijke opdracht", start_date=None)

    derived = await budget_intent.derive(
        db_session, fresh.id, person.id, today=date(2026, 5, 10)
    )
    # Booked until the end of June: the first month with room is July.
    assert (derived.start_date, derived.end_date) == (date(2026, 7, 1), None)
    assert derived.period_source == "person" and derived.period_proposed is True
    assert "eerste maand waarin deze persoon ruimte heeft" in derived.period_source_text
    assert derived.fte == Decimal("1.00")
    assert "in de zes maanden vanaf 1 juli 2026" in derived.fte_source_text
    assert derived.rate_category == "D"
    assert any(s.startswith("Vanaf 1 juli 2026:") for s in derived.summary)
    # Never silently "today".
    free_now = await make_person(14)
    now = await budget_intent.derive(
        db_session, fresh.id, free_now.id, today=date(2026, 5, 10)
    )
    assert now.start_date == date(2026, 5, 10)
    assert now.period_source == "person" and now.period_source_text


async def test_role_is_the_one_last_staffed_in_with_alternatives(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14)
    newcomer = await make_person(14)
    assignment = await make_assignment()
    for role, start in (
        ("Developer", date(2026, 1, 1)),
        ("Productmanager", date(2026, 7, 1)),
        ("Developer", date(2026, 3, 1)),
    ):
        line = await budget_intent.add_line(
            db_session,
            assignment.id,
            actor=beheerder,
            description=role,
            kind="personnel",
            role=role,
            fte=Decimal(1),
            rate_category="D",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        await assignments.add_allocation(
            db_session,
            line.id,
            person.id,
            start_date=start,
            end_date=date(2026, 12, 31),
            fte_pct=Decimal(10),
            actor=beheerder,
        )

    derived = await budget_intent.derive(db_session, assignment.id, person.id)
    assert derived.role == "Productmanager"
    assert derived.role_source == "history"
    assert derived.role_source_text == "laatst ingezet als Productmanager"
    assert [c.role for c in derived.role_alternatives] == ["Developer"]
    assert derived.role_id is not None  # a role from the catalogue
    assert derived.summary[0] == f"{person.name} is laatst ingezet als Productmanager."

    none = await budget_intent.derive(db_session, assignment.id, newcomer.id)
    assert (none.role, none.role_source, none.role_alternatives) == (None, None, ())
    assert "geen eerdere rol bekend" in none.summary[0]


async def test_one_recorded_role_wins_over_the_history(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    from grip.models.catalogue_role import CatalogueRole, PersonCatalogueRole

    person = await make_person(14)
    assignment = await make_assignment()
    line = await budget_intent.add_line(
        db_session,
        assignment.id,
        actor=beheerder,
        description="Developer",
        kind="personnel",
        role="Developer",
        fte=Decimal(1),
        rate_category="D",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    await assignments.add_allocation(
        db_session,
        line.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal(10),
        actor=beheerder,
    )
    architect = CatalogueRole(name="Architect", source="wies", wies_public_id="sk-1")
    tester = CatalogueRole(name="Tester")
    db_session.add_all([architect, tester])
    await db_session.flush()
    db_session.add(
        PersonCatalogueRole(person_id=person.id, role_id=architect.id, source="wies")
    )
    await db_session.flush()

    one = await budget_intent.derive(db_session, assignment.id, person.id)
    assert (one.role, one.role_id, one.role_source) == (
        "Architect",
        architect.id,
        "wies",
    )
    assert one.role_source_text == "uit Wies"
    assert [c.role for c in one.role_alternatives] == ["Developer"]
    assert one.summary[0] == f"Rol van {person.name}: Architect (uit Wies)."

    # Several recorded: the history decides, the recorded ones are offered.
    db_session.add(
        PersonCatalogueRole(person_id=person.id, role_id=tester.id, source="manual")
    )
    await db_session.flush()
    several = await budget_intent.derive(db_session, assignment.id, person.id)
    assert (several.role, several.role_source) == ("Developer", "history")
    assert [c.role for c in several.role_alternatives] == ["Architect", "Tester"]


async def test_summary_says_who_how_much_and_what_was_assumed(
    db_session, rate_cards, make_person, make_assignment
):
    person = await make_person(12)
    assignment = await make_assignment(end_date=date(2026, 12, 31))

    derived = await budget_intent.derive(db_session, assignment.id, person.id)

    assert list(derived.summary) == [
        f"Van {person.name} is geen eerdere rol bekend; kies zelf een rol.",
        "Periode: periode van de opdracht.",
        "Vrij in deze periode: 100%. Uitgegaan van een voltijds aanstelling.",
    ]
    # What the person bills is kept apart, for who may see it.
    assert derived.rate_summary == (
        "Schaal 12 valt in categorie C: € 15.000 per maand per FTE volgens "
        "'Tarieven 2026'."
    )
    assert derived.billing_scale == 12
    staffing_text = " ".join(derived.summary) + " ".join(derived.notes)
    assert "categorie" not in staffing_text and "15.000" not in staffing_text
    assert "Schaal" not in staffing_text


async def test_scale_change_inside_the_period_takes_the_start_and_says_so(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(12)  # category C
    await rates.set_person_scale(
        db_session, person.id, date(2026, 7, 1), 14, actor=beheerder
    )
    assignment = await make_assignment()

    derived = await budget_intent.derive(
        db_session, assignment.id, person.id, start_date=YEAR[0], end_date=YEAR[1]
    )

    assert derived.rate_category == "C"
    assert [
        (r.category, str(r.first_month), str(r.last_month))
        for r in derived.category_runs
    ] == [
        ("C", "2026-01", "2026-06"),
        ("D", "2026-07", "2026-12"),
    ]
    (note,) = derived.category_notes
    assert "inzetschaal van deze persoon wijzigt" in note
    assert "categorie C in januari 2026 t/m juni 2026" in note
    assert "categorie D in juli 2026 t/m december 2026" in note
    # Nothing about the rate in the notes a planner may read.
    assert derived.notes == ()


async def test_two_rate_years_that_map_the_scale_differently(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14)
    await rates.set_scale_band(db_session, 2027, 14, "E", actor=beheerder)
    assignment = await make_assignment()

    derived = await budget_intent.derive(
        db_session,
        assignment.id,
        person.id,
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        fte=Decimal(1),
    )

    assert derived.rate_category == "D"
    assert {r.category for r in derived.category_runs} == {"D", "E"}
    assert "tarievenkaarten delen de schaal" in derived.category_notes[0]
    # The proposal prices the line as a line: one category, the rate of each year.
    assert derived.monthly_rate_by_year == {2026: 18_000_00, 2027: 18_900_00}
    assert derived.budgeted_cents == 6 * 18_000_00 + 6 * 18_900_00


async def test_person_without_billing_scale(
    db_session, rate_cards, beheerder, create_person, make_assignment
):
    person = await create_person("zonder.schaal@example.org", name="Zonder Schaal")
    assignment = await make_assignment()

    derived = await budget_intent.derive(
        db_session, assignment.id, person.id, start_date=YEAR[0], end_date=YEAR[1]
    )
    assert derived.rate_category is None
    assert any("geen inzetschaal" in note for note in derived.notes)

    # Without a category of its own the line cannot be saved ...
    with pytest.raises(DomainValidationError, match="Kies zelf een categorie"):
        await _add(db_session, assignment, beheerder, person)
    # ... with one it can, and the person is reserved all the same.
    line = await _add(db_session, assignment, beheerder, person, rate_category="C")
    assert line.intended_person_id == person.id
    assert len(await _allocations(db_session, line.id)) == 1
    intent = await _intent(db_session, line)
    assert any("geen inzetschaal" in note for note in intent.notes)


async def test_scale_that_starts_later_is_flagged(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14, valid_from=date(2026, 4, 1))
    assignment = await make_assignment()

    derived = await budget_intent.derive(
        db_session, assignment.id, person.id, start_date=YEAR[0], end_date=YEAR[1]
    )
    assert derived.rate_category == "D"
    assert any("deel van deze periode geen inzetschaal" in n for n in derived.notes)


async def test_prospective_colleague_before_the_start_date_is_flagged_not_refused(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14)
    db_session.add(
        PersonStanding(
            person_id=person.id,
            stage="prospective",
            start_date=date(2026, 3, 1),
            source="grip",
        )
    )
    await db_session.flush()
    assignment = await make_assignment(end_date=date(2026, 12, 31))

    proposed = await budget_intent.derive(db_session, assignment.id, person.id)
    assert proposed.start_date == date(2026, 3, 1)  # no earlier than the person
    assert proposed.notes == ()

    line = await _add(db_session, assignment, beheerder, person)
    intent = await _intent(db_session, line)
    assert line.start_date == date(2026, 1, 1)
    assert any("begint op 1 maart 2026" in note for note in intent.notes)
    assert intent.allocation_id is not None


async def test_hired_person_is_budgeted_at_the_billing_rate(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14)
    await rates.add_hire(
        db_session,
        person.id,
        supplier="Leverancier",
        cost_monthly_rate_cents=15_000_00,
        valid_from=YEAR[0],
        actor=beheerder,
    )
    assignment = await make_assignment()

    derived = await budget_intent.derive(
        db_session,
        assignment.id,
        person.id,
        start_date=YEAR[0],
        end_date=YEAR[1],
        fte=Decimal(1),
    )
    assert derived.budgeted_cents == 12 * 18_000_00
    assert "15000" not in repr(derived) and "1500000" not in repr(derived)


async def test_inactive_person_and_fixed_line_are_refused(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14)
    assignment = await make_assignment()
    with pytest.raises(DomainValidationError, match="personeelsregel"):
        await budget_intent.add_line(
            db_session,
            assignment.id,
            actor=beheerder,
            intended_person_id=person.id,
            description="Hosting",
            kind="fixed",
            amount_cents=100,
            year=2026,
        )
    person.is_active = False
    await db_session.flush()
    with pytest.raises(DomainValidationError, match="niet meer actief"):
        await _add(db_session, assignment, beheerder, person)


# -- the line and its reservation ---------------------------------------------------


async def test_naming_a_person_derives_the_category_and_reserves_tentatively(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14)
    assignment = await make_assignment()

    line = await _add(db_session, assignment, beheerder, person)

    assert line.rate_category == "D"
    assert line.intended_person_id == person.id
    (reservation,) = await _allocations(db_session, line.id)
    assert reservation.from_budget is True
    assert (reservation.person_id, reservation.start_date, reservation.end_date) == (
        person.id,
        *YEAR,
    )
    assert reservation.fte_pct == Decimal(80)
    intent = await _intent(db_session, line)
    assert intent.allocation_id == reservation.id
    assert (intent.in_step, intent.tentative, intent.category_differs) == (
        True,
        True,
        False,
    )
    assert intent.implied_category == "D" and intent.notes == ()
    # Planning sees the reservation, marked tentative.
    (staffed,) = await staffing.staffed_allocations(db_session, person_ids=[person.id])
    assert staffed.tentative is True
    # The budget is what the person will bill, and inzet uses it up.
    overview = await pricing.assignment_overview(db_session, assignment.id)
    assert overview.budgeted_cents == 172_800_00
    assert overview.available_cents == 0
    # The name is in the audit trail of the line.
    rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity == "budget_line", AuditLog.entity_id == str(line.id)
            )
        )
    ).scalars()
    assert any(
        (r.new_value or {}).get("intended_person_id") == str(person.id) for r in rows
    )


async def test_given_category_is_kept_and_the_difference_is_signalled(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(16)  # category E
    assignment = await make_assignment()

    line = await _add(db_session, assignment, beheerder, person, rate_category="D")
    intent = await _intent(db_session, line)
    signals = await pricing.category_signals(db_session, assignment.id)

    assert line.rate_category == "D"
    assert intent.category_differs is True
    assert intent.implied_category == "E"
    assert intent.category_notes == (
        "Deze persoon declareert in categorie E; de regel rekent met categorie D.",
    )
    assert intent.notes == ()  # nothing about categories for a planner
    assert [(s.line_category, s.person_category) for s in signals] == [("D", "E")]


async def test_line_above_one_fte_reserves_one_person_fully(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14)
    assignment = await make_assignment()
    line = await _add(db_session, assignment, beheerder, person, fte=Decimal(2))
    (reservation,) = await _allocations(db_session, line.id)
    assert reservation.fte_pct == Decimal(100)
    intent = await _intent(db_session, line)
    assert intent.in_step is True
    assert any("groter dan 1 FTE" in note for note in intent.notes)


async def test_reservation_follows_the_line(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14)
    assignment = await make_assignment()
    line = await _add(db_session, assignment, beheerder, person)

    await budget_intent.update_line(
        db_session,
        line.id,
        actor=beheerder,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 10, 31),
        fte=Decimal("0.5"),
    )
    (reservation,) = await _allocations(db_session, line.id)
    assert (reservation.start_date, reservation.end_date, reservation.fte_pct) == (
        date(2026, 3, 1),
        date(2026, 10, 31),
        Decimal(50),
    )
    assert line.rate_category == "D"  # the category only changes when asked


async def test_field_changed_by_hand_on_the_reservation_is_left_alone(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14)
    assignment = await make_assignment()
    line = await _add(db_session, assignment, beheerder, person)
    (reservation,) = await _allocations(db_session, line.id)
    # A planner lowers the percentage on the planning board.
    await assignments.update_allocation(
        db_session, reservation.id, fte_pct=Decimal(40), actor=beheerder
    )

    await budget_intent.update_line(
        db_session,
        line.id,
        actor=beheerder,
        fte=Decimal("0.6"),
        end_date=date(2026, 9, 30),
    )
    assert reservation.fte_pct == Decimal(40)  # by hand: kept
    assert reservation.end_date == date(2026, 9, 30)  # still in step: follows
    intent = await _intent(db_session, line)
    assert intent.in_step is False
    assert any("wijkt af van de regel" in note for note in intent.notes)


async def test_replacing_and_removing_the_person(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    first = await make_person(14)
    second = await make_person(12)  # category C
    assignment = await make_assignment()
    line = await _add(db_session, assignment, beheerder, first)

    await budget_intent.update_line(
        db_session, line.id, actor=beheerder, intended_person_id=second.id
    )
    (reservation,) = await _allocations(db_session, line.id)
    assert reservation.person_id == second.id and reservation.from_budget
    assert line.rate_category == "D"  # not changed silently
    assert (await _intent(db_session, line)).category_differs is True

    await budget_intent.update_line(
        db_session,
        line.id,
        actor=beheerder,
        intended_person_id=second.id,
        derive_category=True,
    )
    assert line.rate_category == "C"
    assert len(await _allocations(db_session, line.id)) == 1

    await budget_intent.update_line(
        db_session, line.id, actor=beheerder, intended_person_id=None
    )
    assert line.intended_person_id is None
    assert await _allocations(db_session, line.id) == []
    assert await budget_intent.line_intents(db_session, [line]) == {}
    with pytest.raises(DomainValidationError, match="Zonder beoogde persoon"):
        await budget_intent.update_line(
            db_session, line.id, actor=beheerder, derive_category=True
        )


async def test_closed_month_keeps_the_established_inzet(
    db_session, rate_cards, beheerder, make_person, make_assignment, accept
):
    first = await make_person(14)
    second = await make_person(14)
    assignment = await make_assignment()
    line = await _add(db_session, assignment, beheerder, first)
    await accept(assignment)
    await month_close.close_month(
        db_session, assignment.id, Month(2026, 1), actor=beheerder
    )
    (reservation,) = await _allocations(db_session, line.id)

    # The reservation follows the line, so the line cannot leave the closed
    # month either: the change is refused as a whole, and says why.
    with pytest.raises(PeriodChangeBlockedError, match="afgesloten maand 2026-01"):
        await budget_intent.update_line(
            db_session, line.id, actor=beheerder, start_date=date(2026, 2, 1)
        )
    assert (line.start_date, reservation.start_date) == (YEAR[0], YEAR[0])
    assert (await _intent(db_session, line)).in_step is True

    # Replacing the person: the established inzet stays as ordinary inzet
    # with a period of its own, and the new person cannot be put into the
    # closed month.
    await budget_intent.update_line(
        db_session, line.id, actor=beheerder, intended_person_id=second.id
    )
    remaining = await _allocations(db_session, line.id)
    assert [(a.person_id, a.from_budget, a.period_source) for a in remaining] == [
        (first.id, False, "own")
    ]
    intent = await _intent(db_session, line)
    assert intent.person_id == second.id and intent.allocation_id is None
    assert any("geen inzet op de regel" in note for note in intent.notes)
    # After the closed month the new person can be reserved.
    await budget_intent.update_line(
        db_session,
        line.id,
        actor=beheerder,
        start_date=date(2026, 2, 1),
        intended_person_id=second.id,
    )
    assert (await _intent(db_session, line)).allocation_id is not None
    assert remaining[0].start_date == YEAR[0]  # untouched


async def test_deleting_the_line_takes_its_reservation_along(
    db_session, rate_cards, beheerder, make_person, make_assignment
):
    person = await make_person(14)
    other = await make_person(14)
    assignment = await make_assignment()
    line = await _add(db_session, assignment, beheerder, person)
    line_id = line.id

    await budget_intent.delete_line(db_session, line_id, actor=beheerder)
    assert await _allocations(db_session, line_id) == []

    # Other inzet on the line still blocks the delete.
    second = await _add(db_session, assignment, beheerder, person)
    await assignments.add_allocation(
        db_session,
        second.id,
        other.id,
        start_date=YEAR[0],
        end_date=YEAR[1],
        fte_pct=Decimal(20),
        actor=beheerder,
    )
    with pytest.raises(DomainValidationError, match="nog inzet"):
        await budget_intent.delete_line(db_session, second.id, actor=beheerder)


async def test_reservation_turns_firm_when_the_assignment_is_accepted(
    db_session, rate_cards, beheerder, make_person, make_assignment, accept
):
    person = await make_person(14)
    assignment = await make_assignment()
    line = await _add(db_session, assignment, beheerder, person)
    assert (await _intent(db_session, line)).tentative is True
    await accept(assignment)
    assert (await _intent(db_session, line)).tentative is False
