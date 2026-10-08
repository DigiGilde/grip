"""The report of one assignment, for the client and for internal use."""

from uuid import uuid4

from .conftest import (
    ALFA_BUDGET_2026,
    ALFA_BUDGET_2027,
    ALFA_COVERAGE_2026,
    ALFA_FORECAST_2026,
    ALFA_FORECAST_2027,
    ALFA_REALISED_2026,
)

MONEY_KEYS = ("agreed", "totals", "periods", "costs", "quoted_amount_cents")


def _url(world, suffix: str = "") -> str:
    return f"/api/reports/assignments/{world.alfa.id}{suffix}"


async def test_owner_gets_agreed_delivered_and_cost(as_person, world):
    response = await as_person(world.owner).get(
        _url(world), params={"audience": "internal"}
    )
    assert response.status_code == 200
    body = response.json()

    agreed = body["agreed"]
    assert agreed["total_cents"] == ALFA_BUDGET_2026 + ALFA_BUDGET_2027
    assert agreed["form"] == "uploaded_pdf"
    assert agreed["subtotals"] == [
        {"year": 2026, "amount_cents": ALFA_BUDGET_2026},
        {"year": 2027, "amount_cents": ALFA_BUDGET_2027},
    ]
    assert [line["description"] for line in agreed["lines"]] == [
        "Productmanager",
        "Developer",
    ]

    statuses = [change["new_status"] for change in body["status_history"]]
    assert statuses == ["draft", "quoted", "accepted", "in_progress"]
    assert body["months_total"] == 12
    assert body["months_closed"] == 1
    assert [m["month"] for m in body["months"] if m["closed"]] == ["2026-07"]

    periods = {period["year"]: period["totals"] for period in body["periods"]}
    assert periods[2026]["budgeted_cents"] == ALFA_BUDGET_2026
    assert periods[2026]["realised_cents"] == ALFA_REALISED_2026
    assert periods[2026]["forecast_cents"] == ALFA_FORECAST_2026
    assert periods[2026]["coverage_cents"] == ALFA_COVERAGE_2026
    assert periods[2027]["budgeted_cents"] == ALFA_BUDGET_2027
    assert periods[2027]["realised_cents"] == 0
    assert periods[2027]["forecast_cents"] == ALFA_FORECAST_2027
    # The whole period is the sum of its years.
    assert body["totals"]["realised_cents"] == ALFA_REALISED_2026
    assert body["totals"]["forecast_cents"] == ALFA_FORECAST_2026 + ALFA_FORECAST_2027
    assert body["totals"]["budgeted_cents"] == ALFA_BUDGET_2026 + ALFA_BUDGET_2027

    assert [cost["description"] for cost in body["costs"]] == ["Hostingcontract"]
    assert body["costs"][0]["amount_cents"] == ALFA_COVERAGE_2026
    assert {member["person_name"] for member in body["staffing"]} == {
        world.member.name,
        world.colleague.name,
    }


async def test_the_client_version_never_names_staff(as_person, world):
    for person in (world.owner, world.beheerder):
        response = await as_person(person).get(_url(world))
        assert response.status_code == 200
        body = response.json()
        assert body["audience"] == "client"
        assert "staffing" not in body
        assert body["totals"]["realised_cents"] == ALFA_REALISED_2026
        for name in world.staff_names:
            assert name not in response.text


async def test_a_lezer_gets_the_money_and_no_persons(as_person, world):
    response = await as_person(world.lezer).get(
        _url(world), params={"audience": "internal"}
    )
    body = response.json()
    assert body["totals"]["budgeted_cents"] == ALFA_BUDGET_2026 + ALFA_BUDGET_2027
    assert "staffing" not in body
    for name in world.staff_names:
        assert name not in response.text


async def test_a_planner_gets_the_persons_and_no_money(as_person, world):
    response = await as_person(world.planner).get(
        _url(world), params={"audience": "internal"}
    )
    body = response.json()
    for key in MONEY_KEYS:
        assert key not in body
    assert "cents" not in response.text
    assert all("totals" not in line for line in body["lines"])
    assert {member["person_name"] for member in body["staffing"]} == {
        world.member.name,
        world.colleague.name,
    }
    # What is not money is still there.
    assert body["months_closed"] == 1
    assert body["status_history"]


async def test_a_member_sees_colleagues_by_name_only(as_person, world):
    response = await as_person(world.member).get(
        _url(world), params={"audience": "internal"}
    )
    body = response.json()
    for key in MONEY_KEYS:
        assert key not in body
    staffing = {member["person_name"]: member for member in body["staffing"]}
    assert "fte_pct" in staffing[world.member.name]
    assert "fte_pct" not in staffing[world.colleague.name]
    assert "start_date" not in staffing[world.colleague.name]


async def test_hidden_from_someone_without_a_relation(as_person, world):
    client = as_person(world.outsider)
    assert (await client.get(_url(world))).status_code == 404
    assert (await client.get(_url(world, "/document"))).status_code == 404
    missing = f"/api/reports/assignments/{uuid4()}"
    assert (await as_person(world.beheerder).get(missing)).status_code == 404


async def test_an_unknown_audience_is_refused(as_person, world):
    response = await as_person(world.owner).get(_url(world), params={"audience": "x"})
    assert response.status_code == 422


async def test_the_document_is_a_self_contained_page(as_person, world):
    response = await as_person(world.owner).get(_url(world, "/document"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "private, no-store"
    text = response.text
    assert "Wat is afgesproken" in text
    assert "Wat is geleverd" in text
    assert "Wat het heeft gekost" in text
    assert "versie voor de opdrachtgever" in text
    assert "Wie eraan werkte" not in text
    assert "<script" not in text
    for name in world.staff_names:
        assert name not in text


async def test_the_internal_document_follows_the_reader(as_person, world):
    planner = await as_person(world.planner).get(
        _url(world, "/document"), params={"audience": "internal"}
    )
    assert "Wie eraan werkte" in planner.text
    assert world.member.name in planner.text
    assert "€" not in planner.text
    assert "Wat het heeft gekost" not in planner.text
    assert "Wat is afgesproken" not in planner.text

    lezer = await as_person(world.lezer).get(
        _url(world, "/document"), params={"audience": "internal"}
    )
    assert "€" in lezer.text
    assert "Wie eraan werkte" not in lezer.text
    assert world.member.name not in lezer.text


async def test_the_final_report_shows_what_was_and_was_not_delivered(
    as_person, world, db_session
):
    from grip.services import assignments

    await assignments.transition(
        db_session, world.alfa.id, "completed", actor=world.owner
    )
    await assignments.issue_final_report(
        db_session,
        world.alfa.id,
        {
            "summary": "Fictief eindrapport.",
            "delivered": ["Werkende voorziening"],
            "not_delivered": ["Koppeling met het voorbeeldregister"],
        },
        actor=world.owner,
    )
    response = await as_person(world.owner).get(_url(world))
    final = response.json()["final_report"]
    assert final["summary"] == "Fictief eindrapport."
    assert final["delivered"] == ["Werkende voorziening"]
    assert final["not_delivered"] == ["Koppeling met het voorbeeldregister"]

    document = await as_person(world.owner).get(_url(world, "/document"))
    assert "Koppeling met het voorbeeldregister" in document.text
    assert "Niet geleverd" in document.text


async def test_a_value_from_the_data_is_escaped_in_the_document(
    as_person, world, db_session
):
    from grip.services import assignments

    await assignments.update_assignment(
        db_session, world.alfa.id, actor=world.owner, name="Alfa <script>x</script>"
    )
    document = await as_person(world.owner).get(_url(world, "/document"))
    assert "<script>" not in document.text
    assert "&lt;script&gt;" in document.text
