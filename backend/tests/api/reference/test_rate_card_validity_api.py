"""Rate cards with a validity through the API: start one from any date,
see what activating it does, activate it, and ask which rates hold when."""


async def _cards(client):
    return (await client.get("/api/rates/cards")).json()["items"]


async def test_cards_carry_their_validity(client, world, as_person):
    as_person(world.outsider)
    (card,) = [c for c in await _cards(client) if c["year"] == 2026]
    assert card["name"] == "Tarieven 2026"
    assert (card["valid_from"], card["valid_to"]) == ("2026-01-01", "2026-12-31")
    assert card["spans_calendar_year"] is True and card["id"]
    # A card answers to its id, and still to the year it starts in.
    by_id = await client.get(f"/api/rates/cards/{card['id']}")
    by_year = await client.get("/api/rates/cards/2026")
    assert by_id.status_code == by_year.status_code == 200
    assert by_id.json()["id"] == by_year.json()["id"] == card["id"]
    assert (await client.get("/api/rates/cards/geen-kaart")).status_code == 422


async def test_new_card_from_a_date_preview_and_activate(client, world, as_person):
    as_person(world.beheerder)
    proposal = await client.get(
        "/api/rates/indexation-preview",
        params={"valid_from": "2026-07-15", "increase_pct": "4", "rounding": "ten"},
    )
    assert proposal.status_code == 200, proposal.text
    assert proposal.json()["copy_from_name"] == "Tarieven 2026"

    created = await client.post(
        "/api/rates/cards",
        json={
            "valid_from": "2026-07-15",
            "copy_previous": True,
            "increase_pct": "4",
            "rounding": "ten",
        },
    )
    assert created.status_code == 201, created.text
    card = created.json()
    assert (card["name"], card["status"]) == ("Tarieven vanaf 15 juli 2026", "draft")
    assert (card["valid_from"], card["valid_to"]) == ("2026-07-15", None)
    assert {b["category"]: b["monthly_rate_cents"] for b in card["rate_bands"]}[
        "D"
    ] == 1872000

    preview = await client.get(f"/api/rates/cards/{card['id']}/activation-preview")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["shortened"]["name"] == "Tarieven 2026"
    assert body["shortened"]["new_valid_to"] == "2026-07-14"
    impact = body["impact"]
    assert impact["allocations_changed"] >= 1
    assert impact["open_difference_cents"] > 0
    assert impact["correction_cents"] == 0
    assert impact["assignments"][0]["months"][0]["month"] == "2026-07"
    # Nothing was saved by looking.
    assert (await client.get("/api/rates/cards/2026")).json()[
        "valid_to"
    ] == "2026-12-31"

    renamed = await client.patch(
        f"/api/rates/cards/{card['id']}", json={"name": "Tarieven tweede helft 2026"}
    )
    assert renamed.json()["name"] == "Tarieven tweede helft 2026"
    activated = await client.post(f"/api/rates/cards/{card['id']}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
    assert (await client.get("/api/rates/cards/2026")).json()[
        "valid_to"
    ] == "2026-07-14"
    closed = await client.post("/api/rates/cards/2026/close")
    assert closed.json()["status"] == "closed"


async def test_rates_valid_on_a_date_and_over_a_period(client, world, as_person):
    as_person(world.beheerder)
    created = await client.post(
        "/api/rates/cards",
        json={"valid_from": "2026-07-15", "copy_previous": True, "increase_pct": "4"},
    )
    await client.post(f"/api/rates/cards/{created.json()['id']}/activate")

    # Someone who works with money: the owner of an assignment.
    as_person(world.owner)
    on_a_day = (
        await client.get("/api/rates/valid", params={"start_date": "2026-03-01"})
    ).json()
    assert on_a_day["crosses_cards"] is False and on_a_day["has_gap"] is False
    assert on_a_day["summary"] == "Volgens Tarieven 2026, geldig t/m 14 juli 2026."
    (stretch,) = on_a_day["stretches"]
    assert stretch["card_name"] == "Tarieven 2026"
    assert {b["category"] for b in stretch["rate_bands"]} >= {"D"}

    period = (
        await client.get(
            "/api/rates/valid",
            params={"start_date": "2026-06-01", "end_date": "2026-09-30"},
        )
    ).json()
    assert period["crosses_cards"] is True and period["rates_differ"] is True
    assert [(s["start_date"], s["end_date"]) for s in period["stretches"]] == [
        ("2026-06-01", "2026-07-14"),
        ("2026-07-15", "2026-09-30"),
    ]
    assert (
        "Vanaf 15 juli 2026 geldt Tarieven vanaf 15 juli 2026 met andere tarieven"
        in (period["summary"])
    )


async def test_only_the_beheerder_starts_previews_and_activates(
    client, world, as_person
):
    as_person(world.beheerder)
    created = await client.post(
        "/api/rates/cards", json={"valid_from": "2026-07-15", "copy_previous": True}
    )
    card_id = created.json()["id"]
    for person in (world.planner, world.lezer, world.owner, world.outsider):
        as_person(person)
        assert (
            await client.post("/api/rates/cards", json={"valid_from": "2026-09-01"})
        ).status_code == 403
        assert (
            await client.get(f"/api/rates/cards/{card_id}/activation-preview")
        ).status_code == 403
        assert (
            await client.post(f"/api/rates/cards/{card_id}/activate")
        ).status_code == 403


async def test_scale_with_a_past_date_shows_what_it_touches(client, world, as_person):
    as_person(world.beheerder)
    preview = await client.post(
        f"/api/people/{world.hired.id}/scales/preview",
        json={"valid_from": "2026-03-15", "billing_scale": 16},
    )
    assert preview.status_code == 200, preview.text
    impact = preview.json()
    assert impact["allocations_changed"] >= 1
    assert impact["open_difference_cents"] != 0
    assert impact["assignments"][0]["assignment_name"]
    assert impact["assignments"][0]["months"][0]["month"] == "2026-03"
    # Nothing was saved.
    person = (await client.get(f"/api/people/{world.hired.id}")).json()
    assert all(s["valid_from"] != "2026-03-15" for s in person["scales"])
    for other in (world.planner, world.owner, world.outsider):
        as_person(other)
        refused = await client.post(
            f"/api/people/{world.hired.id}/scales/preview",
            json={"valid_from": "2026-03-15", "billing_scale": 16},
        )
        assert refused.status_code in (403, 404)
