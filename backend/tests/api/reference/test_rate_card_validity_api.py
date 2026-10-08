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


async def test_the_preview_names_the_period_left_without_a_settled_card(
    client, world, as_person
):
    """Settling a later card while an earlier one is a draft leaves a gap."""
    as_person(world.beheerder)
    current = (await client.get("/api/rates/cards/2026")).json()
    ended = await client.patch(
        f"/api/rates/cards/{current['id']}", json={"valid_to": "2026-12-31"}
    )
    assert ended.status_code == 200, ended.text

    async def draft(start: str, end: str | None) -> dict:
        made = await client.post(
            "/api/rates/cards",
            json={"valid_from": start, "valid_to": end, "copy_from_id": current["id"]},
        )
        assert made.status_code == 201, made.text
        return made.json()

    middle = await draft("2027-01-01", "2027-12-31")
    later = await draft("2028-01-01", None)

    preview = await client.get(f"/api/rates/cards/{later['id']}/activation-preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["gaps"] == [
        {
            "start_date": "2027-01-01",
            "end_date": "2027-12-31",
            "drafts": [middle["name"]],
        }
    ]
    # The card that follows on directly leaves none.
    adjoining = await client.get(f"/api/rates/cards/{middle['id']}/activation-preview")
    assert adjoining.json()["gaps"] == []

    # With the middle one settled the later one leaves no gap either.
    settled = await client.post(f"/api/rates/cards/{middle['id']}/activate")
    assert settled.status_code == 200, settled.text
    again = await client.get(f"/api/rates/cards/{later['id']}/activation-preview")
    assert again.json()["gaps"] == []


async def test_a_gap_without_a_draft_is_named_too(client, world, as_person):
    as_person(world.beheerder)
    current = (await client.get("/api/rates/cards/2026")).json()
    await client.patch(
        f"/api/rates/cards/{current['id']}", json={"valid_to": "2026-12-31"}
    )
    made = await client.post(
        "/api/rates/cards",
        json={"valid_from": "2027-03-01", "copy_from_id": current["id"]},
    )
    assert made.status_code == 201, made.text
    preview = await client.get(
        f"/api/rates/cards/{made.json()['id']}/activation-preview"
    )
    assert preview.json()["gaps"] == [
        {"start_date": "2027-01-01", "end_date": "2027-02-28", "drafts": []}
    ]
