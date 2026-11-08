"""Search: a list of names that betrays nothing, not even by its length.

All names are fictional. Every name holds "Voorbeeld", so one search finds
every kind of thing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.auth import DEV_PERSON_COOKIE
from grip.models.assignment import BudgetLine
from grip.models.person import Person
from grip.models.stream_event import StreamEvent
from grip.models.vacancy import Vacancy, VacancyStatus, VacancyText
from grip.models.vacancy_text_flow import VacancyTextReview, VacancyTextVerdict
from grip.services import assignments, events
from grip.services.vacancies import service as vacancy_service

SEARCH = "/api/search"


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


@dataclass
class World:
    beheerder: Person
    lezer: Person
    owner: Person
    member: Person
    colleague: Person
    outsider: Person
    alfa: object
    beta: object
    concept: Vacancy
    published: Vacancy


@pytest.fixture
def as_person(client: AsyncClient):
    def _as(person: Person) -> AsyncClient:
        client.cookies.set(DEV_PERSON_COOKIE, str(person.id))
        return client

    return _as


async def _line(db: AsyncSession, assignment, actor) -> BudgetLine:
    return await assignments.add_budget_line(
        db,
        assignment.id,
        description="Ontwikkelaar",
        kind="personnel",
        role="Ontwikkelaar",
        fte=Decimal("0.8"),
        rate_category="C",
        start_date=date(2026, 1, 1),
        end_date=date(2030, 12, 31),
        actor=actor,
    )


async def _publish(db: AsyncSession, vacancy: Vacancy, actor: Person) -> None:
    now = datetime.now(UTC)
    vacancy.status = VacancyStatus.open.value
    vacancy.published_at = now
    db.add(
        VacancyText(
            vacancy_id=vacancy.id,
            kind="vacancy_text",
            body="Wij zoeken een ontwikkelaar.",
            source="human",
            established_by_id=actor.id,
            established_at=now,
        )
    )
    await db.flush()


@pytest.fixture
async def world(db_session: AsyncSession, create_person) -> World:
    db = db_session
    beheerder = await create_person(
        "beheer@example.org", name="Voorbeeld Beheerder", functions=["beheerder"]
    )
    lezer = await create_person(
        "lezer@example.org", name="Voorbeeld Lezer", functions=["lezer"]
    )
    owner = await create_person("eigenaar@example.org", name="Voorbeeld Eigenaar")
    member = await create_person("lid@example.org", name="Voorbeeld Lid")
    colleague = await create_person("collega@example.org", name="Voorbeeld Collega")
    outsider = await create_person("buiten@example.org", name="Voorbeeld Buiten")

    org = await assignments.upsert_organisation(db, name="Ministerie van Voorbeeld")
    alfa = await assignments.create_assignment(
        db, name="Voorbeeld Alfa", actor=owner, client_organisation_id=org.id
    )
    beta = await assignments.create_assignment(
        db, name="Voorbeeld Beta", actor=beheerder
    )
    line = await _line(db, alfa, owner)
    for person in (member, colleague):
        await assignments.add_allocation(
            db,
            line.id,
            person.id,
            start_date=date(2026, 1, 1),
            end_date=date(2030, 12, 31),
            fte_pct=Decimal("30"),
            actor=owner,
        )
    concept = await vacancy_service.create_vacancy(
        db,
        actor=owner,
        function_title="Voorbeeld concept",
        fte=Decimal("0.8"),
        declarable=True,
        budget_line_id=line.id,
    )
    published = await vacancy_service.create_vacancy(
        db,
        actor=beheerder,
        function_title="Voorbeeld ontwikkelaar",
        fte=Decimal("1"),
        declarable=False,
    )
    await _publish(db, published, beheerder)
    return World(
        beheerder=beheerder,
        lezer=lezer,
        owner=owner,
        member=member,
        colleague=colleague,
        outsider=outsider,
        alfa=alfa,
        beta=beta,
        concept=concept,
        published=published,
    )


def _ids(found: list[dict]) -> set[str]:
    return {item["id"] for item in found}


def _names(found: list[dict], key: str = "name") -> list[str]:
    return [item[key] for item in found]


async def _search(client: AsyncClient, text: str = "voorbeeld") -> dict:
    response = await client.get(SEARCH, params={"q": text})
    assert response.status_code == 200, response.text
    return response.json()


# --- assignments -------------------------------------------------------------


async def test_a_reader_of_everything_finds_every_assignment(world, as_person):
    body = await _search(as_person(world.beheerder))
    assert _names(body["assignments"]) == ["Voorbeeld Alfa", "Voorbeeld Beta"]
    alfa = body["assignments"][0]
    assert alfa["client_name"] == "Ministerie van Voorbeeld"
    assert alfa["phase"] == "potential"
    assert body["assignments"][1]["client_name"] is None


async def test_the_name_of_the_client_finds_the_assignment(world, as_person):
    body = await _search(as_person(world.beheerder), "ministerie")
    assert _names(body["assignments"]) == ["Voorbeeld Alfa"]


async def test_a_team_member_finds_only_the_assignments_of_the_team(world, as_person):
    for person in (world.owner, world.member, world.colleague):
        body = await _search(as_person(person))
        assert _names(body["assignments"]) == ["Voorbeeld Alfa"], person.name


async def test_someone_without_a_relation_finds_no_assignment(world, as_person):
    body = await _search(as_person(world.outsider))
    assert body["assignments"] == []


async def test_the_answer_holds_no_field_of_a_higher_class(world, as_person):
    body = await _search(as_person(world.beheerder))
    assert set(body) == {"q", "assignments", "vacancies", "people"}
    for item in body["assignments"]:
        assert set(item) == {"id", "name", "client_name", "phase"}
    for item in body["vacancies"]:
        assert set(item) == {"id", "title"}
    for item in body["people"]:
        assert set(item) == {"id", "name"}


# --- vacancies ---------------------------------------------------------------


async def test_a_reader_without_a_relation_finds_only_published_vacancies(
    world, as_person
):
    body = await _search(as_person(world.outsider))
    assert _names(body["vacancies"], "title") == ["Voorbeeld ontwikkelaar"]
    assert "concept" not in str(body).lower()


async def test_a_team_member_finds_the_draft_of_the_own_assignment(world, as_person):
    body = await _search(as_person(world.owner))
    assert _names(body["vacancies"], "title") == [
        "Voorbeeld concept",
        "Voorbeeld ontwikkelaar",
    ]


async def test_a_reader_and_the_beheerder_find_every_vacancy(world, as_person):
    for person in (world.lezer, world.beheerder):
        body = await _search(as_person(person))
        assert _ids(body["vacancies"]) == {
            str(world.concept.id),
            str(world.published.id),
        }, person.name


async def test_a_reviewer_of_a_text_finds_that_vacancy_and_no_other(
    world, as_person, db_session
):
    draft = await vacancy_service.create_vacancy(
        db_session,
        actor=world.beheerder,
        function_title="Voorbeeld beoordeling",
        fte=Decimal("1"),
        declarable=False,
    )
    text = VacancyText(
        vacancy_id=draft.id, kind="vacancy_text", body="Concept.", source="human"
    )
    db_session.add(text)
    await db_session.flush()
    review = VacancyTextReview(
        vacancy_id=draft.id,
        kind="vacancy_text",
        round=1,
        text_id=text.id,
        offered_by_id=world.beheerder.id,
    )
    review.verdicts = [VacancyTextVerdict(reviewer_id=world.outsider.id)]
    db_session.add(review)
    await db_session.flush()

    body = await _search(as_person(world.outsider))
    assert _ids(body["vacancies"]) == {str(draft.id), str(world.published.id)}
    assert str(world.concept.id) not in str(body)


async def test_every_vacancy_found_is_in_the_list_of_vacancies(world, as_person):
    for person in (
        world.beheerder,
        world.lezer,
        world.owner,
        world.member,
        world.outsider,
    ):
        client = as_person(person)
        listed = _ids((await client.get("/api/vacancies")).json())
        assert _ids((await _search(client))["vacancies"]) <= listed, person.name


# --- people ------------------------------------------------------------------


async def test_a_beheerder_finds_every_active_person(world, as_person, create_person):
    await create_person("weg@example.org", name="Voorbeeld Vertrokken", is_active=False)
    body = await _search(as_person(world.beheerder))
    assert _names(body["people"]) == [
        "Voorbeeld Beheerder",
        "Voorbeeld Buiten",
        "Voorbeeld Collega",
        "Voorbeeld Eigenaar",
        "Voorbeeld Lezer",
        "Voorbeeld Lid",
    ]


async def test_a_reader_finds_no_one_but_themselves(world, as_person):
    body = await _search(as_person(world.lezer))
    assert _ids(body["people"]) == {str(world.lezer.id)}


async def test_someone_without_a_relation_finds_only_themselves(world, as_person):
    body = await _search(as_person(world.outsider))
    assert _ids(body["people"]) == {str(world.outsider.id)}


async def test_a_team_member_finds_the_team_and_not_a_stranger(world, as_person):
    body = await _search(as_person(world.member))
    found = _ids(body["people"])
    assert str(world.colleague.id) in found
    assert str(world.member.id) in found
    assert str(world.outsider.id) not in found
    assert str(world.beheerder.id) not in found


async def test_every_person_found_is_in_the_list_of_people(world, as_person):
    for person in (
        world.beheerder,
        world.lezer,
        world.owner,
        world.member,
        world.colleague,
        world.outsider,
    ):
        client = as_person(person)
        listed = _ids((await client.get("/api/people")).json()["items"])
        found = _ids((await _search(client))["people"])
        assert found <= listed, person.name


async def test_a_person_is_found_by_the_same_decision_as_in_the_list(world, as_person):
    # The owner manages an assignment and so reads the roster of everyone;
    # the search follows the list, whatever the rule is.
    client = as_person(world.owner)
    listed = {
        p["id"]: p["name"] for p in (await client.get("/api/people")).json()["items"]
    }
    found = {p["id"]: p["name"] for p in (await _search(client))["people"]}
    assert found == {i: n for i, n in listed.items() if "voorbeeld" in n.lower()}


# --- cutting and counting ----------------------------------------------------


async def test_the_list_is_cut_after_the_decision_not_before(
    world, as_person, db_session, create_person
):
    # Twenty-five things come first in order; the outsider may see none of
    # them, and has one of their own that sorts last.
    for number in range(25):
        await assignments.create_assignment(
            db_session, name=f"Voorbeeld A{number:02d}", actor=world.beheerder
        )
        await vacancy_service.create_vacancy(
            db_session,
            actor=world.beheerder,
            function_title=f"Voorbeeld A{number:02d}",
            fte=Decimal("1"),
            declarable=False,
        )
        await create_person(f"a{number}@example.org", name=f"Voorbeeld A{number:02d}")
    alone = await create_person("alleen@example.org", name="Voorbeeld Zzz Alleen")
    await assignments.create_assignment(
        db_session, name="Voorbeeld Zzz", actor=world.outsider
    )
    own = await vacancy_service.create_vacancy(
        db_session,
        actor=world.beheerder,
        function_title="Voorbeeld Zzz",
        fte=Decimal("1"),
        declarable=False,
    )
    await _publish(db_session, own, world.beheerder)

    outsider = await _search(as_person(world.outsider))
    assert _names(outsider["assignments"]) == ["Voorbeeld Zzz"]
    # Twenty-five drafts are hidden, the published ones are not.
    assert "Voorbeeld Zzz" in _names(outsider["vacancies"], "title")
    assert "Voorbeeld A00" not in _names(outsider["vacancies"], "title")
    # Only the own assignment is a relation; the people stay hidden for
    # someone who has none.
    assert _ids((await _search(as_person(alone)))["people"]) == {str(alone.id)}

    everything = await _search(as_person(world.beheerder))
    for kind in ("assignments", "vacancies", "people"):
        assert len(everything[kind]) == 20, kind


async def test_the_answer_has_no_total(world, as_person):
    body = await _search(as_person(world.outsider))
    assert not {"total", "count", "counts", "more"} & body.keys()


# --- the text ----------------------------------------------------------------


@pytest.mark.parametrize("text", ["a", " a ", "  ", "", "x" * 101])
async def test_a_text_that_is_too_short_or_too_long_is_refused(world, as_person, text):
    response = await as_person(world.beheerder).get(SEARCH, params={"q": text})
    assert response.status_code == 422


async def test_a_search_without_text_is_refused(world, as_person):
    assert (await as_person(world.beheerder).get(SEARCH)).status_code == 422


async def test_two_characters_and_a_hundred_are_enough(world, as_person):
    client = as_person(world.beheerder)
    assert (await client.get(SEARCH, params={"q": "vo"})).status_code == 200
    assert (await client.get(SEARCH, params={"q": "v" * 100})).status_code == 200


async def test_percent_and_underscore_are_plain_characters(
    world, as_person, db_session, create_person
):
    for name in (
        "Voorbeeld_Gamma",
        "VoorbeeldXGamma",
        "Voorbeeld 100%",
        "Voorbeeld 100x",
    ):
        await assignments.create_assignment(
            db_session, name=name, actor=world.beheerder
        )
        await vacancy_service.create_vacancy(
            db_session,
            actor=world.beheerder,
            function_title=name,
            fte=Decimal("1"),
            declarable=False,
        )
        await create_person(f"{name}@example.org".replace(" ", ""), name=name)
    client = as_person(world.beheerder)

    underscore = await _search(client, "d_G")
    assert _names(underscore["assignments"]) == ["Voorbeeld_Gamma"]
    assert _names(underscore["vacancies"], "title") == ["Voorbeeld_Gamma"]
    assert _names(underscore["people"]) == ["Voorbeeld_Gamma"]

    percent = await _search(client, "100%")
    assert _names(percent["assignments"]) == ["Voorbeeld 100%"]
    assert _names(percent["vacancies"], "title") == ["Voorbeeld 100%"]
    assert _names(percent["people"]) == ["Voorbeeld 100%"]

    for pattern in ("%%", "__", "\\\\", "%_"):
        empty = await _search(client, pattern)
        assert empty["assignments"] == empty["vacancies"] == empty["people"] == []


async def test_case_spaces_and_non_ascii_do_not_matter(
    world, as_person, db_session, create_person
):
    await create_person("zoe@example.org", name="Zoë Ünïcode")
    client = as_person(world.beheerder)
    assert _names((await _search(client, "  ZOË  "))["people"]) == ["Zoë Ünïcode"]
    body = await _search(client, " ünï ")
    assert _names(body["people"]) == ["Zoë Ünïcode"]
    assert body["q"] == "ünï"
    assert _names((await _search(client, "VOORBEELD alfa"))["assignments"]) == [
        "Voorbeeld Alfa"
    ]


# --- what is not read --------------------------------------------------------


async def test_searching_writes_no_read_event(world, as_person, db_session):
    client = as_person(world.beheerder)
    before = await db_session.scalar(
        select(func.count())
        .select_from(StreamEvent)
        .where(StreamEvent.type == "data.read")
    )
    await _search(client)
    await db_session.flush()
    after = await db_session.scalar(
        select(func.count())
        .select_from(StreamEvent)
        .where(StreamEvent.type == "data.read")
    )
    assert after == before
