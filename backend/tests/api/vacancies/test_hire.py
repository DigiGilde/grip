"""The hire on a vacancy: the moment a person enters grip.

Grip keeps no candidates. It keeps a reference to the vacancy in the
recruitment system and, at the hire, who was hired. All data is fictional.
"""

from __future__ import annotations

from sqlalchemy import select

from grip.access import unclassified_fields
from grip.models.assignment import Allocation
from grip.models.person import Person
from grip.models.person_details import PersonScale
from grip.models.person_standing import ColleagueProposal, PersonStanding
from grip.models.vacancy import Vacancy
from grip.schema import vacancy_hire as schemas

from .test_vacancies_api import BASE, _approve, _create

_NEW = {"name": "Nova Nieuw", "start_date": "2027-03-01"}


async def _approved(client, act_as, manager, beheerder, budget_line, **extra):
    act_as(manager)
    vacancy = await _create(client, budget_line, **extra)
    await _approve(client, act_as, beheerder, vacancy["id"])
    act_as(manager)
    return vacancy


def test_every_field_has_a_data_class():
    for schema in (
        schemas.VacancyHireOut,
        schemas.HireOut,
        schemas.RecruitmentRefOut,
        schemas.ProposedAllocationOut,
    ):
        assert not unclassified_fields(schema), schema.__name__


def test_a_vacancy_has_no_field_for_a_candidate():
    """Selection is the recruitment system's; grip stores nobody before the hire."""
    names = {column.name for column in Vacancy.__table__.columns}

    assert not {n for n in names if "candidate" in n or "kandidaat" in n}


async def test_recruitment_reference_is_stored_and_cleared(
    client, act_as, manager, budget_line
):
    act_as(manager)
    vacancy = await _create(client, budget_line)
    url = f"{BASE}/{vacancy['id']}"

    stored = await client.put(
        f"{url}/recruitment-ref",
        json={"reference": "V-2026-014", "url": "https://werving.example/v/14"},
    )

    assert stored.status_code == 200, stored.text
    assert stored.json()["recruitment_ref"] == {
        "system": "emply",
        "reference": "V-2026-014",
        "url": "https://werving.example/v/14",
    }
    refused = await client.put(
        f"{url}/recruitment-ref", json={"reference": "x", "url": "javascript:alert(1)"}
    )
    assert refused.status_code == 422
    cleared = await client.put(f"{url}/recruitment-ref", json={"reference": ""})
    assert cleared.json()["recruitment_ref"] is None


async def test_hire_fills_the_vacancy_and_creates_the_prospective_colleague(
    client, db_session, act_as, manager, beheerder, budget_line
):
    vacancy = await _approved(client, act_as, manager, beheerder, budget_line)
    url = f"{BASE}/{vacancy['id']}"
    await client.put(f"{url}/recruitment-ref", json={"reference": "V-2026-014"})

    response = await client.post(
        f"{url}/hire",
        json={
            "name": "Nova Nieuw",
            "start_date": "2027-03-01",
            "suborganization": "Digi Gilde",
        },
    )

    assert response.status_code == 201, response.text
    hire = response.json()["hire"]
    assert (hire["person_name"], hire["start_date"], hire["stage"]) == (
        "Nova Nieuw",
        "2027-03-01",
        "prospective",
    )
    # The inzet is proposed, not made: the planner confirms it.
    assert hire["proposed_allocation"] == {
        "budget_line_id": str(budget_line.id),
        "start_date": "2027-03-01",
        "end_date": "2027-12-31",
        "fte_pct": "80",
    }
    assert hire["allocation_id"] is None
    assert (await client.get(url)).json()["status"] == "filled"

    person = await db_session.get(Person, hire["person_id"])
    assert person.email is None
    row = await db_session.get(PersonStanding, person.id)
    assert (row.stage, row.source, row.source_ref) == (
        "prospective",
        "grip",
        "emply:V-2026-014",
    )
    assert (await db_session.get(ColleagueProposal, person.id)).state == "open"


async def test_hire_can_plan_the_person_at_once(
    client, db_session, act_as, manager, beheerder, budget_line
):
    vacancy = await _approved(client, act_as, manager, beheerder, budget_line)

    response = await client.post(
        f"{BASE}/{vacancy['id']}/hire",
        json={
            "name": "Nova Nieuw",
            "start_date": "2027-03-01",
            "create_allocation": True,
        },
    )

    hire = response.json()["hire"]
    allocation = await db_session.get(Allocation, hire["allocation_id"])
    assert str(allocation.person_id) == hire["person_id"]
    assert hire["proposed_allocation"] is None


async def test_a_new_colleague_starts_at_the_scale_of_the_vacancy(
    client, db_session, act_as, manager, beheerder, budget_line
):
    """Inzet without an inzetschaal cannot be priced, so a hire must not
    leave the new colleague without one: the vacancy's scale holds from the
    start date. Someone grip already knows keeps the scale they have."""
    vacancy = await _approved(client, act_as, manager, beheerder, budget_line)
    scale = (await db_session.get(Vacancy, vacancy["id"])).scale
    assert scale is not None

    response = await client.post(
        f"{BASE}/{vacancy['id']}/hire",
        json={
            "name": "Nova Nieuw",
            "start_date": "2027-03-01",
            "create_allocation": True,
        },
    )
    assert response.status_code == 201, response.text

    person_id = response.json()["hire"]["person_id"]
    scales = (
        (
            await db_session.execute(
                select(PersonScale).where(PersonScale.person_id == person_id)
            )
        )
        .scalars()
        .all()
    )
    assert [(row.valid_from.isoformat(), row.billing_scale) for row in scales] == [
        ("2027-03-01", scale)
    ]


async def test_hire_of_someone_grip_already_knows(
    client, act_as, manager, beheerder, budget_line, colleague
):
    vacancy = await _approved(client, act_as, manager, beheerder, budget_line)

    response = await client.post(
        f"{BASE}/{vacancy['id']}/hire",
        json={"person_id": str(colleague.id), "start_date": "2027-03-01"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["hire"]["stage"] == "colleague"


async def test_hire_needs_the_approval_and_one_person(
    client, act_as, manager, beheerder, budget_line
):
    act_as(manager)
    draft = await _create(client, budget_line)
    early = await client.post(
        f"{BASE}/{draft['id']}/hire",
        json={"name": "Nova Nieuw", "start_date": "2027-03-01"},
    )
    assert early.status_code == 422

    await _approve(client, act_as, beheerder, draft["id"])
    act_as(manager)
    nobody = await client.post(
        f"{BASE}/{draft['id']}/hire", json={"start_date": "2027-03-01"}
    )
    assert nobody.status_code == 422


async def test_hire_that_falls_through_removes_planning_and_proposal(
    client, db_session, act_as, manager, beheerder, budget_line
):
    vacancy = await _approved(client, act_as, manager, beheerder, budget_line)
    url = f"{BASE}/{vacancy['id']}"
    hired = await client.post(
        f"{url}/hire",
        json={
            "name": "Nova Nieuw",
            "start_date": "2027-03-01",
            "create_allocation": True,
        },
    )
    person_id = hired.json()["hire"]["person_id"]

    response = await client.post(
        f"{url}/hire/withdraw", json={"reason": "Ging toch niet door."}
    )

    assert response.status_code == 200, response.text
    assert response.json()["hire"] is None
    left = (
        (
            await db_session.execute(
                select(Allocation).where(Allocation.person_id == person_id)
            )
        )
        .scalars()
        .all()
    )
    assert left == []
    assert (await db_session.get(ColleagueProposal, person_id)).state == "withdrawn"
    assert (await db_session.get(PersonStanding, person_id)).remove_after is not None


async def test_who_may_not_edit_the_vacancy_sees_and_records_nothing(
    client, act_as, manager, beheerder, budget_line, colleague, lezer
):
    vacancy = await _approved(client, act_as, manager, beheerder, budget_line)
    url = f"{BASE}/{vacancy['id']}"
    await client.post(
        f"{url}/hire", json={"name": "Nova Nieuw", "start_date": "2027-03-01"}
    )

    for person in (colleague, lezer):
        act_as(person)
        assert (await client.get(f"{url}/hire")).status_code in (403, 404)
        refused = await client.post(
            f"{url}/hire", json={"name": "Iemand Anders", "start_date": "2027-03-01"}
        )
        assert refused.status_code in (403, 404)
