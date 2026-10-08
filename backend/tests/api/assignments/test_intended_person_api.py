"""The intended person of a budget line through the API."""

from decimal import Decimal

from .conftest import by_id


def _line(body, line_id):
    return by_id(body["lines"], "id", str(line_id))


def _new_line(person_id=None, **extra):
    payload = {
        "description": "Developer",
        "kind": "personnel",
        "role": "Developer",
        "fte": "0.5",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
    }
    if person_id is not None:
        payload["intended_person_id"] = str(person_id)
    payload.update(extra)
    return payload


def _base(world) -> str:
    return f"/api/assignments/{world.assignment.id}"


async def test_owner_sees_what_a_person_implies_before_saving(world, as_person):
    response = await as_person(world.owner).post(
        f"{_base(world)}/budget-lines/derive",
        json={
            "intended_person_id": str(world.outsider.id),
            "fte": "0.5",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # The outsider has no billing scale: no category, and a note that says so.
    assert body["rate_category"] is None
    assert any("geen inzetschaal" in note for note in body["notes"])
    assert "rate_summary" in body and body["rate_summary"] is None

    body = (
        await as_person(world.owner).post(
            f"{_base(world)}/budget-lines/derive",
            json={
                "intended_person_id": str(world.colleague.id),
                "fte": "0.5",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        )
    ).json()
    assert body["rate_category"] == "C"
    assert body["billing_scale"] == 12
    assert body["rate_summary"] == (
        "Schaal 12 valt in categorie C: € 15.000 per maand per FTE volgens "
        "'Tarieven 2026'."
    )
    assert body["monthly_rates"] == [{"year": 2026, "monthly_rate_cents": 1500000}]
    assert body["budgeted_cents"] == 6 * 1500000
    assert body["period_proposed"] is False and body["period_source"] == "given"
    # The colleague is on the Productmanager line for 30 percent all year.
    assert body["role"] == "Productmanager" and body["role_source"] == "history"
    assert body["role_source_text"] == "laatst ingezet als Productmanager"
    assert body["role_alternatives"] == []
    assert Decimal(body["free_pct"]) == Decimal(70)
    assert Decimal(body["fte"]) == Decimal("0.7")
    assert body["fte_source_text"] == (
        "vrij in deze periode: 70%; al ingezet op Opdracht Alfa 2026 (30%, onder "
        "voorbehoud). Uitgegaan van een voltijds aanstelling"
    )
    assert body["summary"][0] == "Cas Collega is laatst ingezet als Productmanager."

    # Without a period the one of the assignment is proposed.
    body = (
        await as_person(world.owner).post(
            f"{_base(world)}/budget-lines/derive",
            json={"intended_person_id": str(world.colleague.id)},
        )
    ).json()
    assert (body["start_date"], body["end_date"]) == ("2026-01-01", "2026-12-31")
    assert body["period_proposed"] is True and body["period_source"] == "assignment"
    assert body["period_source_text"] == "periode van de opdracht"
    assert Decimal(body["fte"]) == Decimal("0.7")
    # The proposed size prices the line.
    assert body["budgeted_cents"] == round(12 * 1500000 * 0.7)


async def test_derive_shows_a_planner_no_category_or_amount(world, as_person):
    response = await as_person(world.planner).post(
        f"{_base(world)}/budget-lines/derive",
        json={
            "intended_person_id": str(world.colleague.id),
            "fte": "0.5",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intended_person_id"] == str(world.colleague.id)
    # Role, size and period are staffing: the planner gets the proposals.
    assert body["role"] == "Productmanager"
    assert Decimal(body["fte"]) == Decimal("0.7")
    assert body["period_source"] == "given"
    assert "Opdracht Alfa 2026" in body["fte_source_text"]
    assert body["summary"]
    # What the person bills stays out.
    for hidden in (
        "rate_category",
        "category_notes",
        "monthly_rates",
        "budgeted_cents",
        "rate_summary",
        "billing_scale",
    ):
        assert hidden not in body
    text = response.text
    assert "categorie" not in text and "Schaal" not in text and "15.000" not in text


async def test_who_may_ask_what_a_person_implies(world, as_person):
    payload = {"intended_person_id": str(world.colleague.id)}
    for person in (world.member, world.lezer):
        response = await as_person(person).post(
            f"{_base(world)}/budget-lines/derive", json=payload
        )
        assert response.status_code == 403
    response = await as_person(world.outsider).post(
        f"{_base(world)}/budget-lines/derive", json=payload
    )
    assert response.status_code == 404


async def test_create_derives_reserves_and_shows_the_person_to_staffing_readers(
    world, as_person
):
    response = await as_person(world.owner).post(
        f"{_base(world)}/budget-lines", json=_new_line(world.outsider.id)
    )
    # No billing scale and no category sent: a clear refusal.
    assert response.status_code == 422
    assert "Kies zelf een categorie" in response.text

    response = await as_person(world.owner).post(
        f"{_base(world)}/budget-lines", json=_new_line(world.colleague.id)
    )
    assert response.status_code == 201, response.text
    line = next(
        row for row in response.json()["lines"] if row["description"] == "Developer"
    )
    assert line["rate_category"] == "C"  # derived from the colleague
    assert line["budgeted_cents"] == 6 * 1500000
    assert line["intended_person_id"] == str(world.colleague.id)
    assert line["intended_person_name"] == "Cas Collega"
    assert line["intended_allocation_id"]
    assert line["intended_in_step"] is True
    assert line["intended_tentative"] is True  # the assignment is still potential
    assert line["intended_category"] == "C"
    assert line["intended_category_differs"] is False
    assert line["intended_notes"] == []

    # The reservation shows up as inzet of that person.
    listed = (
        await as_person(world.owner).get(
            "/api/allocations", params={"assignment_id": str(world.assignment.id)}
        )
    ).json()
    assert line["intended_allocation_id"] in response.text and listed

    # A planner sees who, not what that person bills.
    planner_line = _line(
        (await as_person(world.planner).get(f"{_base(world)}/budget")).json(),
        line["id"],
    )
    assert planner_line["intended_person_name"] == "Cas Collega"
    assert planner_line["intended_category_differs"] is False
    for hidden in ("intended_category", "intended_category_notes", "rate_category"):
        assert hidden not in planner_line

    # A reader of totals only does not see who the role is meant for.
    lezer_line = _line(
        (await as_person(world.lezer).get(f"{_base(world)}/budget")).json(), line["id"]
    )
    assert not [key for key in lezer_line if key.startswith("intended")]


async def test_planner_names_a_person_on_an_existing_line(world, as_person, db_session):
    planner = as_person(world.planner)
    # The budget itself is not the planner's to change.
    refused = await planner.patch(
        f"/api/budget-lines/{world.line.id}",
        json={"intended_person_id": str(world.outsider.id), "fte": "0.5"},
    )
    assert refused.status_code == 403
    refused = await planner.patch(
        f"/api/budget-lines/{world.line.id}",
        json={"intended_person_id": str(world.colleague.id), "derive_category": True},
    )
    assert refused.status_code == 403

    response = await planner.patch(
        f"/api/budget-lines/{world.line.id}",
        json={"intended_person_id": str(world.colleague.id)},
    )
    assert response.status_code == 200, response.text
    line = _line(response.json(), world.line.id)
    assert line["intended_person_id"] == str(world.colleague.id)
    # The colleague bills in C on a line that assumes D: the planner gets the
    # signal, not the categories.
    assert line["intended_category_differs"] is True
    assert "intended_category" not in line and "rate_category" not in line
    await db_session.refresh(world.line)
    assert world.line.rate_category == "D"  # unchanged by naming someone

    owner_line = _line(
        (await as_person(world.owner).get(f"{_base(world)}/budget")).json(),
        world.line.id,
    )
    assert owner_line["intended_category"] == "C"
    assert owner_line["intended_category_notes"] == [
        "Deze persoon declareert in categorie C; de regel rekent met categorie D."
    ]

    # Removing the name is staffing too.
    response = await as_person(world.planner).patch(
        f"/api/budget-lines/{world.line.id}", json={"intended_person_id": None}
    )
    assert response.status_code == 200
    assert _line(response.json(), world.line.id).get("intended_person_id") is None


async def test_owner_replaces_the_person_and_takes_the_category_along(
    world, as_person, db_session
):
    owner = as_person(world.owner)
    response = await owner.patch(
        f"/api/budget-lines/{world.line.id}",
        json={"intended_person_id": str(world.colleague.id), "derive_category": True},
    )
    assert response.status_code == 200, response.text
    line = _line(response.json(), world.line.id)
    assert line["rate_category"] == "C"
    assert line["intended_category_differs"] is False
    assert Decimal(line["fte"]) == Decimal("0.8")

    # The period of the line changes: the reservation follows.
    response = await owner.patch(
        f"/api/budget-lines/{world.line.id}", json={"end_date": "2026-09-30"}
    )
    line = _line(response.json(), world.line.id)
    assert line["intended_in_step"] is True


async def test_member_and_outsider_cannot_name_anyone(world, as_person):
    payload = {"intended_person_id": str(world.colleague.id)}
    for person, expected in (
        (world.member, 403),
        (world.lezer, 403),
        (world.outsider, 404),
    ):
        response = await as_person(person).patch(
            f"/api/budget-lines/{world.line.id}", json=payload
        )
        assert response.status_code == expected


async def test_quote_preview_through_the_api_names_no_one(world, as_person):
    owner = as_person(world.owner)
    await owner.patch(
        f"/api/budget-lines/{world.line.id}",
        json={"intended_person_id": str(world.colleague.id)},
    )
    response = await owner.get(f"{_base(world)}/quote-preview")
    assert response.status_code == 200, response.text
    text = response.text
    for needle in (
        str(world.colleague.id),
        "Cas Collega",
        "collega@example.org",
        "intended",
    ):
        assert needle not in text
    assert "Productmanager" in text
