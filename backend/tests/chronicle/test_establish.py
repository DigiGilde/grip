"""A fact enters the chronicle and the read models together."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from grip.chronicle import guard, verify
from grip.chronicle.ledger import fold
from grip.chronicle.writer import changes_of, establish, row_of
from grip.events import check
from grip.models.assignment import Assignment, AssignmentRole, BudgetLine
from grip.models.catalogue_role import CatalogueRole
from grip.models.stream_event import StreamEvent
from grip.repositories.chronicle import ChronicleRepository


async def _born(db_session, person=None) -> UUID:
    assignment_id = uuid4()
    await establish(
        db_session,
        "assignment_created",
        assignment_id=assignment_id,
        actor=person,
        fields={
            "assignment": row_of(
                Assignment,
                id=assignment_id,
                uri=f"https://voorbeeld.example/id/opdracht/{assignment_id}",
                name="Voorbeeldopdracht",
                kind="external",
                status="draft",
                context_refs=[],
            ),
            "owner_role": row_of(
                AssignmentRole,
                id=uuid4(),
                assignment_id=assignment_id,
                person_id=person.id,
                role="owner",
            )
            if person
            else None,
        },
    )
    return assignment_id


async def _catalogue_role(db_session, name="Voorbeeldrol") -> CatalogueRole:
    role = CatalogueRole(id=uuid4(), name=name, source="manual")
    db_session.add(role)
    await db_session.flush()
    return role


async def _line(db_session, assignment_id, role, **values) -> UUID:
    line_id = uuid4()
    await establish(
        db_session,
        "budget_line_added",
        assignment_id=assignment_id,
        fields={
            "line": row_of(
                BudgetLine,
                id=line_id,
                assignment_id=assignment_id,
                kind="personnel",
                detail="",
                position=1,
                role=role.name,
                role_id=role.id,
                fte=values.pop("fte", Decimal("0.8")),
                rate_category="B",
                period_source="own",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                **values,
            )
        },
    )
    return line_id


async def test_a_fact_and_its_rows_come_together(db_session, create_person):
    person = await create_person("eigenaar@example.org", name="Priya Voorbeeld")
    assignment_id = await _born(db_session, person)

    row = await db_session.get(Assignment, assignment_id)
    assert row.name == "Voorbeeldopdracht"
    roles = (
        await db_session.scalars(
            select(AssignmentRole).where(AssignmentRole.assignment_id == assignment_id)
        )
    ).all()
    assert [(r.person_id, r.role) for r in roles] == [(person.id, "owner")]

    grams = await ChronicleRepository(db_session).grams(assignment_id)
    assert [g.fact for g in grams] == ["assignment_created"]
    assert grams[0].actor_person_id == person.id
    assert grams[0].recorded_on is not None
    assert grams[0].plan_version


async def test_the_fact_is_filed_under_its_case_and_touches_no_person(db_session):
    assignment_id = await _born(db_session)
    event = await db_session.scalar(
        select(StreamEvent).where(StreamEvent.subject_kind == "chronolexogram")
    )
    assert event.case_kind == "assignment"
    assert event.case_id == assignment_id
    assert event.person_id is None
    assert event.existence_class is None


async def test_the_chain_stays_whole(db_session):
    assignment_id = await _born(db_session)
    role = await _catalogue_role(db_session)
    await _line(db_session, assignment_id, role)
    verdict = await check.verify_stream(db_session)
    assert verdict.intact


async def test_the_fold_is_what_the_rows_say(db_session, create_person):
    person = await create_person("eigenaar@example.org")
    assignment_id = await _born(db_session, person)
    role = await _catalogue_role(db_session)
    line_id = await _line(db_session, assignment_id, role, fte=Decimal("0.12345"))

    report = await verify.differences(db_session, assignment_id)
    assert report.checked
    assert report.differences == []

    # What the column keeps is what the fact says, not what was sent.
    grams = await ChronicleRepository(db_session).grams(assignment_id)
    assert fold(grams).table("budget_line")[str(line_id)]["fte"] == "0.123"


async def test_a_change_counts_once(db_session):
    assignment_id = await _born(db_session)
    role = await _catalogue_role(db_session)
    line_id = await _line(db_session, assignment_id, role)
    line = await db_session.get(BudgetLine, line_id)
    assert line.version == 1

    await establish(
        db_session,
        "budget_line_changed",
        assignment_id=assignment_id,
        fields={"line_id": line_id, "changes": changes_of(BudgetLine, fte="1")},
    )
    assert line.fte == Decimal("1")
    assert line.version == 2


async def test_a_new_role_enters_the_catalogue_with_the_line(db_session):
    assignment_id = await _born(db_session)
    role = CatalogueRole(
        id=uuid4(), name="Nieuwe rol", source="manual", needs_review=True
    )
    db_session.add(role)
    await _line(db_session, assignment_id, role)
    assert (await db_session.get(CatalogueRole, role.id)).name == "Nieuwe rol"


async def test_the_owner_changes_whichever_row_sorts_first(db_session, create_person):
    for promoted_id in (
        UUID("00000000-0000-4000-8000-000000000001"),
        UUID("ffffffff-ffff-4fff-bfff-ffffffffffff"),
    ):
        owner = await create_person(f"{uuid4()}@example.org")
        manager = await create_person(f"{uuid4()}@example.org")
        assignment_id = await _born(db_session, owner)
        owner_row = await db_session.scalar(
            select(AssignmentRole).where(AssignmentRole.assignment_id == assignment_id)
        )
        await establish(
            db_session,
            "assignment_role_set",
            assignment_id=assignment_id,
            fields={
                "role": row_of(
                    AssignmentRole,
                    id=promoted_id,
                    assignment_id=assignment_id,
                    person_id=manager.id,
                    role="manager",
                ),
                "new": True,
                "demoted": [],
            },
        )
        await establish(
            db_session,
            "assignment_role_set",
            assignment_id=assignment_id,
            fields={
                "role": {"id": promoted_id, "role": "owner"},
                "new": False,
                "demoted": [owner_row.id],
            },
        )
        report = await verify.differences(db_session, assignment_id)
        assert report.differences == []
        await db_session.execute(
            text("DELETE FROM assignment_role WHERE id = :id"), {"id": promoted_id}
        )


async def test_damage_shows_and_a_rebuild_puts_it_right(db_session, create_person):
    person = await create_person("eigenaar@example.org")
    assignment_id = await _born(db_session, person)
    role = await _catalogue_role(db_session)
    line_id = await _line(db_session, assignment_id, role)

    await db_session.execute(
        text("UPDATE assignment SET name = 'Beschadigd' WHERE id = :id"),
        {"id": assignment_id},
    )
    await db_session.execute(
        text("UPDATE budget_line SET fte = 9 WHERE id = :id"), {"id": line_id}
    )
    report = await verify.differences(db_session, assignment_id)
    assert {(d.table, d.column) for d in report.differences} == {
        ("assignment", "name"),
        ("budget_line", "fte"),
    }

    changed = await verify.rebuild(db_session, assignment_id)
    assert changed == 2
    report = await verify.differences(db_session, assignment_id)
    assert report.differences == []
    row = await db_session.get(Assignment, assignment_id)
    assert row.name == "Voorbeeldopdracht"
    line = await db_session.get(BudgetLine, line_id)
    assert line.fte == Decimal("0.8")


async def test_a_lost_row_comes_back_and_a_stray_row_goes(db_session, create_person):
    person = await create_person("eigenaar@example.org")
    assignment_id = await _born(db_session, person)
    role = await _catalogue_role(db_session)
    line_id = await _line(db_session, assignment_id, role)
    stray_id = uuid4()

    await db_session.execute(
        text("DELETE FROM budget_line WHERE id = :id"), {"id": line_id}
    )
    db_session.expire_all()
    await db_session.execute(
        text(
            "INSERT INTO budget_line (id, assignment_id, description, kind, "
            "amount_cents, year) VALUES (:id, :a, 'Los', 'fixed', 100, 2026)"
        ),
        {"id": stray_id, "a": assignment_id},
    )
    report = await verify.differences(db_session, assignment_id)
    assert {d.row_id for d in report.differences} == {str(line_id), str(stray_id)}

    await verify.rebuild(db_session, assignment_id)
    report = await verify.differences(db_session, assignment_id)
    assert report.differences == []
    line = await db_session.get(BudgetLine, line_id)
    assert line.role == role.name


async def test_a_renamed_role_is_no_difference(db_session):
    assignment_id = await _born(db_session)
    role = await _catalogue_role(db_session)
    await _line(db_session, assignment_id, role)
    role.name = "Andere naam"
    await db_session.flush()
    report = await verify.differences(db_session, assignment_id)
    assert report.differences == []


async def test_a_person_who_left_empties_what_points_at_them(db_session, create_person):
    person = await create_person("eigenaar@example.org")
    assignment_id = await _born(db_session, person)
    await db_session.delete(person)
    await db_session.flush()
    report = await verify.differences(db_session, assignment_id)
    assert report.differences == []


async def test_a_case_without_a_birth_is_not_compared(db_session):
    assignment = Assignment(
        id=uuid4(), uri="https://voorbeeld.example/x", name="Los", kind="external"
    )
    db_session.add(assignment)
    await db_session.flush()
    report = await verify.differences(db_session, assignment.id)
    assert not report.checked


async def test_an_unknown_fact_is_refused(db_session):
    with pytest.raises(ValueError, match="unknown fact"):
        await establish(db_session, "bestaat_niet", assignment_id=uuid4(), fields={})


async def test_a_change_record_that_names_the_kind_is_no_fact(db_session):
    from grip.events import stream

    assignment_id = await _born(db_session)
    stream.append(
        db_session,
        subject=("chronolexogram", assignment_id),
        action="update",
        assignment_id=assignment_id,
        new={"plain": "x"},
    )
    await db_session.flush()
    grams = await ChronicleRepository(db_session).grams(assignment_id)
    assert [g.fact for g in grams] == ["assignment_created"]


async def test_the_guard_finds_a_write_around_the_chronicle(db_session):
    guard.install()
    assignment_id = await _born(db_session)
    await db_session.flush()
    assert not guard.tainted(db_session)

    row = await db_session.get(Assignment, assignment_id)
    with guard.in_request(db_session) as unit:
        row.name = "Om de kroniek heen"
        await db_session.flush()
    assert unit.findings == ["changed assignment"]


async def test_the_guard_lets_a_fact_through_and_names_its_case(db_session):
    guard.install()
    with guard.in_request(db_session) as unit:
        assignment_id = await _born(db_session)
    assert unit.findings == []
    assert unit.cases == {assignment_id}


async def test_a_hand_edit_outside_a_request_taints_the_session(db_session):
    guard.install()
    assignment_id = await _born(db_session)
    row = await db_session.get(Assignment, assignment_id)
    row.name = "Klaargezet door de test"
    await db_session.flush()
    assert guard.tainted(db_session)
