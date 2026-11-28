"""Two requests at one moment: rows and chronicle may not part.

The two sessions share the connection of the test, so the second reads what the
first flushed without a commit. They show the stale read, not the wait on the
lock.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from grip.chronicle import verify
from grip.chronicle.writer import changes_of, establish, row_of
from grip.events import context, stream
from grip.integrations.wies.client import WiesSkill
from grip.models.assignment import Assignment, AssignmentRole
from grip.repositories.chronicle import ChronicleRepository
from grip.services import assignments, budget_intent, catalogue_roles, costs
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.vacancies import service as vacancies
from tests.chronicle.test_establish import _born

LOCK = "pg_advisory_xact_lock"


def _while_it_waits(monkeypatch, happens) -> None:
    """Something else is recorded while the next one to ask waits on the stream."""
    real_hold = stream.hold_head

    async def wait(session):
        monkeypatch.setattr(stream, "hold_head", real_hold)
        await happens()
        await real_hold(session)

    monkeypatch.setattr(stream, "hold_head", wait)


@pytest.fixture
async def other_request(db_session):
    session = AsyncSession(bind=db_session.bind, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()


async def _manager(db_session, assignment_id: UUID, person) -> UUID:
    role_id = uuid4()
    await establish(
        db_session,
        "assignment_role_set",
        assignment_id=assignment_id,
        fields={
            "role": row_of(
                AssignmentRole,
                id=role_id,
                assignment_id=assignment_id,
                person_id=person.id,
                role="manager",
            ),
            "demoted": [],
            "new": True,
        },
    )
    return role_id


async def test_a_value_equal_to_a_stale_read_still_reaches_the_row(
    db_session, other_request, create_person
):
    manager = await create_person("manager@example.org")
    assignment_id = await _born(db_session)
    role_id = await _manager(db_session, assignment_id, manager)

    assert (await other_request.get(AssignmentRole, role_id)).role == "manager"

    await establish(
        db_session,
        "assignment_role_set",
        assignment_id=assignment_id,
        fields={"role": {"id": role_id, "role": "owner"}, "demoted": []},
    )
    await establish(
        other_request,
        "assignment_role_set",
        assignment_id=assignment_id,
        fields={"role": {"id": role_id, "role": "manager"}, "demoted": []},
    )
    await other_request.flush()

    report = await verify.differences(db_session, assignment_id)
    assert report.checked
    assert report.differences == []


async def test_a_versioned_row_that_moved_refuses_the_fact(db_session, other_request):
    assignment_id = await _born(db_session)
    stale = await other_request.get(Assignment, assignment_id)
    assert stale.notes is None

    await establish(
        db_session,
        "assignment_changed",
        assignment_id=assignment_id,
        fields={
            "assignment_id": assignment_id,
            "changes": changes_of(Assignment, notes="Eerst"),
        },
    )

    with pytest.raises(StaleDataError):
        await establish(
            other_request,
            "assignment_changed",
            assignment_id=assignment_id,
            fields={
                "assignment_id": assignment_id,
                "changes": changes_of(Assignment, notes=None),
            },
        )


async def test_an_empty_patch_decides_nothing_about_a_row_that_moved(
    db_session, other_request
):
    assignment_id = await _born(db_session)
    await other_request.get(Assignment, assignment_id)

    await establish(
        db_session,
        "assignment_changed",
        assignment_id=assignment_id,
        fields={
            "assignment_id": assignment_id,
            "changes": changes_of(Assignment, notes="Eerst"),
        },
    )
    await establish(
        other_request,
        "assignment_changed",
        assignment_id=assignment_id,
        fields={"assignment_id": assignment_id, "changes": {}},
    )
    await other_request.flush()

    assert (await verify.differences(db_session, assignment_id)).differences == []


async def test_a_row_that_moved_answers_with_a_conflict(
    client, create_person, monkeypatch
):
    await create_person("beheerder@example.org", functions=["beheerder"])
    created = await client.post("/api/assignments", json={"name": "Voorbeeldtraject"})
    assert created.status_code == 201, created.text

    async def moved(*_args, **_kwargs):
        raise StaleDataError("the row moved")

    monkeypatch.setattr(assignments, "update_assignment", moved)
    response = await client.patch(
        f"/api/assignments/{created.json()['id']}", json={"notes": "Iets"}
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "StaleDataError"
    assert "niets overschreven" in response.json()["detail"]


async def _manager_by_request(client, create_person) -> tuple[str, UUID]:
    await create_person("beheerder@example.org", functions=["beheerder"])
    manager = await create_person("manager@example.org")
    created = await client.post("/api/assignments", json={"name": "Voorbeeldtraject"})
    assert created.status_code == 201, created.text
    case = created.json()["id"]
    made = await client.put(
        f"/api/assignments/{case}/roles/{manager.id}", json={"role": "manager"}
    )
    assert made.status_code == 200, made.text
    return case, manager.id


async def test_the_same_manager_removed_twice_answers_with_a_conflict(
    client, db_session, other_request, create_person, monkeypatch
):
    case, manager = await _manager_by_request(client, create_person)

    async def the_first_removal():
        await assignments.remove_assignment_role(
            other_request, UUID(case), manager, actor=None
        )
        await other_request.flush()

    _while_it_waits(monkeypatch, the_first_removal)
    response = await client.delete(f"/api/assignments/{case}/roles/{manager}")

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "StaleDataError"
    assert "niets overschreven" in response.json()["detail"]
    grams = await ChronicleRepository(db_session).grams(UUID(case))
    assert [gram.fact for gram in grams].count("assignment_role_removed") == 1
    assert (await verify.differences(db_session, UUID(case))).differences == []


@contextmanager
def _statements(session: AsyncSession) -> Iterator[list[str]]:
    seen: list[str] = []

    def note(_connection, _cursor, statement, *_rest) -> None:
        seen.append(statement)

    connection = session.bind.sync_connection
    event.listen(connection, "before_cursor_execute", note)
    try:
        yield seen
    finally:
        event.remove(connection, "before_cursor_execute", note)


def _first(seen: list[str], fragment: str) -> int:
    return next(i for i, statement in enumerate(seen) if fragment in statement)


async def test_a_rename_takes_the_lock_on_the_stream_before_the_lines(db_session):
    role = await catalogue_roles.create_role(db_session, name="Developer", actor=None)
    await db_session.flush()

    with _statements(db_session) as seen:
        await catalogue_roles.update_role(
            db_session, role.id, {"name": "Ontwikkelaar"}, actor=None
        )

    assert _first(seen, LOCK) < _first(seen, "UPDATE catalogue_role")


async def test_a_description_given_before_the_name_waits_for_the_lock_too(db_session):
    role = await catalogue_roles.create_role(db_session, name="Developer", actor=None)
    await db_session.flush()

    with _statements(db_session) as seen:
        await catalogue_roles.update_role(
            db_session,
            role.id,
            {"description": "Bouwt de dienst", "name": "Ontwikkelaar"},
            actor=None,
        )

    assert _first(seen, LOCK) < _first(seen, "UPDATE catalogue_role")


async def test_a_rename_from_wies_takes_the_lock_on_the_stream_before_the_lines(
    db_session,
):
    skill = str(uuid4())
    await catalogue_roles.apply_wies_skills(db_session, [WiesSkill(skill, "Developer")])

    with _statements(db_session) as seen:
        counts = await catalogue_roles.apply_wies_skills(
            db_session, [WiesSkill(skill, "Ontwikkelaar")]
        )

    assert counts.renamed == 1
    assert _first(seen, LOCK) < _first(seen, "UPDATE catalogue_role")


async def test_a_merge_takes_the_lock_on_the_stream_before_the_roles(db_session):
    source = await catalogue_roles.create_role(db_session, name="Developer", actor=None)
    target = await catalogue_roles.create_role(
        db_session, name="Ontwikkelaar", actor=None
    )
    await db_session.flush()

    with _statements(db_session) as seen:
        await catalogue_roles.merge_roles(db_session, source.id, target.id, actor=None)

    assert _first(seen, LOCK) < _first(seen, "DELETE FROM catalogue_role")


async def test_a_coverage_takes_the_lock_on_the_stream_before_its_line(
    db_session, staffed
):
    item = await costs.create_cost_item(
        db_session, description="Licentie", actor=None, budgeted_cents=1000
    )
    await db_session.flush()

    with _statements(db_session) as seen:
        await costs.set_coverage(
            db_session, item.id, staffed.line.id, Decimal("50"), actor=None
        )

    assert _first(seen, LOCK) < _first(seen, "INSERT INTO cost_coverage")


async def test_a_vacancy_takes_the_lock_on_the_stream_before_its_line(
    db_session, staffed
):
    with _statements(db_session) as seen:
        await vacancies.create_vacancy_from_budget_line(
            db_session, actor=None, budget_line_id=staffed.line.id
        )

    assert _first(seen, LOCK) < _first(seen, "INSERT INTO vacancy")


async def test_a_name_taken_while_a_rename_waits_is_told_as_taken(
    db_session, other_request, monkeypatch
):
    one = await catalogue_roles.create_role(db_session, name="Developer", actor=None)
    two = await catalogue_roles.create_role(db_session, name="Tester", actor=None)
    await db_session.flush()

    async def the_first_rename():
        await catalogue_roles.update_role(
            other_request, one.id, {"name": "Voorbeeld"}, actor=None
        )

    _while_it_waits(monkeypatch, the_first_rename)
    with pytest.raises(DomainValidationError, match="Er is al een rol"):
        await catalogue_roles.update_role(
            db_session, two.id, {"name": "voorbeeld"}, actor=None
        )


@pytest.fixture
async def staffed(db_session, create_person):
    """A line that follows its assignment, with inzet that follows the line."""
    person = await create_person("medewerker@example.org")
    case = await assignments.create_assignment(
        db_session,
        name="Voorbeeldtraject",
        actor=None,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    line = await assignments.add_budget_line(
        db_session,
        case.id,
        description="",
        kind="personnel",
        role="Productmanager",
        fte=Decimal("0.5"),
        rate_category="D",
        actor=None,
    )
    allocation = await assignments.add_allocation(
        db_session, line.id, person.id, fte_pct=Decimal("50"), actor=None
    )
    await db_session.flush()
    return SimpleNamespace(person=person, case=case, line=line, allocation=allocation)


async def test_new_inzet_takes_the_lock_on_the_stream_before_its_line(
    db_session, staffed
):
    with _statements(db_session) as seen:
        await assignments.add_allocation(
            db_session,
            staffed.line.id,
            staffed.person.id,
            fte_pct=Decimal("20"),
            actor=None,
        )

    assert _first(seen, LOCK) < _first(seen, "INSERT INTO allocation")


async def test_a_change_of_inzet_takes_the_lock_on_the_stream_before_its_row(
    db_session, staffed
):
    with _statements(db_session) as seen:
        await assignments.update_allocation(
            db_session, staffed.allocation.id, actor=None, fte_pct=Decimal("40")
        )

    assert _first(seen, LOCK) < _first(seen, "UPDATE allocation")


async def test_a_moved_line_takes_the_lock_on_the_stream_before_its_inzet(
    db_session, staffed
):
    with _statements(db_session) as seen:
        await assignments.update_budget_line(
            db_session,
            staffed.line.id,
            actor=None,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 11, 30),
        )

    assert _first(seen, LOCK) < _first(seen, "UPDATE allocation")


async def test_a_moved_assignment_takes_the_lock_on_the_stream_before_the_inzet(
    db_session, staffed
):
    with _statements(db_session) as seen:
        await assignments.update_assignment(
            db_session,
            staffed.case.id,
            actor=None,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 11, 30),
        )

    assert _first(seen, LOCK) < _first(seen, "UPDATE allocation")


async def test_a_reservation_that_stays_takes_the_lock_on_the_stream_before_its_row(
    db_session, staffed, monkeypatch
):
    async def work_was_established(*_args, **_kwargs):
        raise DomainValidationError("Deze inzet komt voor in een maandafsluiting.")

    monkeypatch.setattr(assignments, "delete_allocation", work_was_established)
    with _statements(db_session) as seen:
        await budget_intent._release(
            db_session, staffed.allocation, actor=None, allow_closed_year=False
        )

    assert _first(seen, LOCK) < _first(seen, "UPDATE allocation")


async def test_new_inzet_on_a_line_that_went_while_it_waited_is_not_found(
    db_session, other_request, staffed, monkeypatch
):
    line = await assignments.add_budget_line(
        db_session,
        staffed.case.id,
        description="",
        kind="personnel",
        role="Ontwikkelaar",
        fte=Decimal("0.5"),
        rate_category="D",
        actor=None,
    )
    await db_session.flush()

    async def the_line_goes():
        await assignments.delete_budget_line(other_request, line.id, actor=None)
        await other_request.flush()

    _while_it_waits(monkeypatch, the_line_goes)
    with pytest.raises(NotFoundError):
        await assignments.add_allocation(
            db_session, line.id, staffed.person.id, fte_pct=Decimal("20"), actor=None
        )


async def test_new_inzet_follows_a_line_that_moved_while_it_waited(
    db_session, other_request, staffed, monkeypatch
):
    async def the_line_moves():
        await assignments.delete_allocation(
            other_request, staffed.allocation.id, actor=None
        )
        await assignments.update_budget_line(
            other_request,
            staffed.line.id,
            actor=None,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 11, 30),
        )
        await other_request.flush()

    _while_it_waits(monkeypatch, the_line_moves)
    allocation = await assignments.add_allocation(
        db_session,
        staffed.line.id,
        staffed.person.id,
        fte_pct=Decimal("20"),
        actor=None,
    )

    assert (allocation.start_date, allocation.end_date) == (
        date(2026, 2, 1),
        date(2026, 11, 30),
    )


async def test_a_trace_over_two_requests_does_not_stretch_an_act(db_session):
    first = datetime(2026, 3, 2, 10, tzinfo=UTC)
    second = datetime(2026, 3, 2, 11, tzinfo=UTC)
    with context.scope(correlation_id="een-trace-van-buiten"):
        with stream.recording_at(first):
            assignment_id = await _born(db_session)
        with stream.recording_at(second):
            stream.append(
                db_session,
                subject=("instance_setting", "instance"),
                action="update",
                new={"quote_approval.mode": "always"},
            )
            await db_session.flush()
    repository = ChronicleRepository(db_session)
    gram = (await repository.grams(assignment_id))[0]

    assert gram.occurred_at == first
    assert (
        await repository.act_end(gram.seq, gram.correlation_id, gram.occurred_at, None)
        == gram.seq
    )


async def test_what_a_transaction_records_is_dated_as_one(db_session):
    moment = datetime(2026, 3, 2, 10, tzinfo=UTC)
    with stream.recording_at(moment):
        fact = stream.append(
            db_session, subject=("instance_setting", "instance"), action="update"
        )
        change = stream.append(
            db_session, subject=("instance_setting", "instance"), action="update"
        )
        await db_session.flush()
    assert fact.occurred_at == change.occurred_at == moment


async def test_owner_and_manager_swapped_by_hand_come_back(db_session, create_person):
    owner = await create_person("eigenaar@example.org")
    manager = await create_person("manager@example.org")
    assignment_id = await _born(db_session, owner)
    await _manager(db_session, assignment_id, manager)
    await db_session.execute(
        text(
            "UPDATE assignment_role SET role = 'manager' "
            "WHERE assignment_id = :id AND person_id = :owner"
        ),
        {"id": assignment_id, "owner": owner.id},
    )
    await db_session.execute(
        text(
            "UPDATE assignment_role SET role = 'owner' "
            "WHERE assignment_id = :id AND person_id = :manager"
        ),
        {"id": assignment_id, "manager": manager.id},
    )
    assert len((await verify.differences(db_session, assignment_id)).differences) == 2

    assert await verify.rebuild(db_session, assignment_id) == 2

    assert (await verify.differences(db_session, assignment_id)).differences == []


async def test_a_column_younger_than_the_fact_is_no_difference(db_session, monkeypatch):
    assignment_id = await _born(db_session)
    await db_session.execute(
        text("UPDATE assignment SET notes = 'Gevuld bij een migratie' WHERE id = :id"),
        {"id": assignment_id},
    )
    real_grams = ChronicleRepository.grams

    async def older_facts(self, wanted, upto=None):
        grams = await real_grams(self, wanted, upto)
        fields = dict(grams[0].fields)
        fields["assignment"] = {
            key: value for key, value in fields["assignment"].items() if key != "notes"
        }
        return [replace(grams[0], fields=fields), *grams[1:]]

    monkeypatch.setattr(ChronicleRepository, "grams", older_facts)

    report = await verify.differences(db_session, assignment_id)
    assert report.checked
    assert report.differences == []
