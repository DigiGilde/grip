"""The period source of budget lines and inzet through the API."""

from .conftest import by_id

PM = {
    "description": "Developer",
    "kind": "personnel",
    "role": "Developer",
    "fte": "0.5",
    "rate_category": "D",
}


def _lines(body, description="Developer"):
    return [line for line in body["lines"] if line["description"] == description]


async def test_fresh_assignment_takes_a_line_without_dates_and_says_what_to_do(
    world, as_person
):
    """The common case: a potential assignment that has no period yet."""
    client = as_person(world.beheerder)
    base = f"/api/assignments/{world.other_assignment.id}"

    response = await client.post(f"{base}/budget-lines", json=PM)
    assert response.status_code == 201, response.text
    body = response.json()
    (line,) = _lines(body)
    assert line["period_source"] == "assignment"
    assert line["start_date"] is None and line["end_date"] is None
    assert body["period_missing"] is True
    assert body["period_message"] == (
        "Nog geen periode: vul de periode van de opdracht in."
    )
    assert body["assignment_start_date"] is None
    # Not priced, and never as zero.
    assert line["budgeted_cents"] is None
    assert body["total_budgeted_cents"] is None
    assert "vul de periode van de opdracht in" in (
        line["pricing_error"] or body["pricing_error"] or ""
    )

    # Every screen that shows the assignment still answers.
    for path in (
        base,
        f"{base}/budget",
        f"{base}/overview",
        f"{base}/staffing",
        f"{base}/financial",
        "/api/assignments",
        "/api/overview?year=2026",
        "/api/allocations/board",
        "/api/reports/steering?year=2026",
    ):
        answer = await client.get(path)
        assert answer.status_code == 200, (
            f"{path}: {answer.status_code} {answer.text[:300]}"
        )
    # A quote cannot be previewed or issued yet, and says why.
    preview = (await client.get(f"{base}/quote-preview")).json()
    assert preview["can_issue"] is False and preview["content"] is None
    assert preview["problem"] == "Nog geen periode: vul de periode van de opdracht in."
    issued = await client.post(f"{base}/quotes", json={})
    assert issued.status_code in (409, 422), issued.text
    assert "periode van de opdracht" in issued.text

    # One action: the period of the assignment prices every following line.
    patched = await client.patch(
        base, json={"start_date": "2026-01-01", "end_date": "2026-12-31"}
    )
    assert patched.status_code == 200, patched.text
    body = (await client.get(f"{base}/budget")).json()
    (line,) = _lines(body)
    assert (line["period_source"], line["start_date"], line["end_date"]) == (
        "assignment",
        "2026-01-01",
        "2026-12-31",
    )
    assert line["budgeted_cents"] == 6 * 1800000
    assert body["period_missing"] is False and body["period_message"] is None
    assert (body["assignment_start_date"], body["assignment_end_date"]) == (
        "2026-01-01",
        "2026-12-31",
    )


async def test_line_source_through_create_and_update(world, as_person):
    client = as_person(world.owner)
    base = f"/api/assignments/{world.assignment.id}"

    own = await client.post(
        f"{base}/budget-lines",
        json={**PM, "start_date": "2026-04-01", "end_date": "2026-09-30"},
    )
    (line,) = _lines(own.json())
    assert line["period_source"] == "own"

    following = await client.patch(
        f"/api/budget-lines/{line['id']}", json={"period_source": "assignment"}
    )
    (line,) = _lines(following.json())
    assert (line["period_source"], line["start_date"], line["end_date"]) == (
        "assignment",
        "2026-01-01",
        "2026-12-31",
    )
    refused = await client.patch(
        f"/api/budget-lines/{line['id']}", json={"period_source": "kwartaal"}
    )
    assert refused.status_code == 422

    # The existing line of the world had the dates of the assignment.
    existing = by_id(following.json()["lines"], "id", str(world.line.id))
    assert existing["start_date"] == "2026-01-01"


async def test_inzet_source_through_create_and_update(world, as_person):
    client = as_person(world.owner)
    created = await client.post(
        "/api/allocations",
        json={
            "budget_line_id": str(world.line.id),
            "person_id": str(world.outsider.id),
            "fte_pct": "20",
        },
    )
    assert created.status_code == 201, created.text
    row = created.json()
    assert (row["period_source"], row["start_date"], row["end_date"]) == (
        "line",
        "2026-01-01",
        "2026-12-31",
    )

    own = await client.patch(
        f"/api/allocations/{row['id']}", json={"end_date": "2026-06-30"}
    )
    assert (own.json()["period_source"], own.json()["end_date"]) == (
        "own",
        "2026-06-30",
    )
    back = await client.patch(
        f"/api/allocations/{row['id']}", json={"period_source": "line"}
    )
    assert (back.json()["period_source"], back.json()["end_date"]) == (
        "line",
        "2026-12-31",
    )

    # The line shortens: the inzet that follows it moves along.
    await client.patch(
        f"/api/budget-lines/{world.line.id}",
        json={"start_date": "2026-01-01", "end_date": "2026-10-31"},
    )
    listed = (
        await client.get(
            "/api/allocations", params={"assignment_id": str(world.assignment.id)}
        )
    ).json()
    moved = by_id(listed["items"], "id", row["id"])
    assert moved["end_date"] == "2026-10-31"


async def test_derive_for_a_following_line(world, as_person):
    client = as_person(world.owner)
    body = (
        await client.post(
            f"/api/assignments/{world.assignment.id}/budget-lines/derive",
            json={
                "intended_person_id": str(world.colleague.id),
                "period_source": "assignment",
                "start_date": "2026-04-01",
                "end_date": "2026-09-30",
            },
        )
    ).json()
    assert (body["start_date"], body["end_date"]) == ("2026-01-01", "2026-12-31")
    assert body["period_source"] == "assignment"

    body = (
        await as_person(world.beheerder).post(
            f"/api/assignments/{world.other_assignment.id}/budget-lines/derive",
            json={
                "intended_person_id": str(world.colleague.id),
                "period_source": "assignment",
            },
        )
    ).json()
    assert body["start_date"] is None and body["period_source"] is None
    assert "Nog geen periode: vul de periode van de opdracht in." in body["notes"]
    assert body["fte"] is None
