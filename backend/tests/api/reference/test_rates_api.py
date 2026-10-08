"""Rate cards through the API: everyone reads, only the beheerder changes."""

from sqlalchemy import select

from grip.models.audit_log import AuditLog
from grip.repositories.domain import RateRepository


async def test_everyone_reads_rate_cards(client, world, as_person):
    as_person(world.outsider)
    resp = await client.get("/api/rates/cards")
    assert resp.status_code == 200
    body = resp.json()
    assert body["may_manage"] is False
    card = body["items"][0]
    assert card["year"] == 2026 and card["status"] == "active"
    assert {b["category"]: b["monthly_rate_cents"] for b in card["rate_bands"]}[
        "D"
    ] == 1800000
    assert {"scale": 14, "category": "D"} in card["scale_bands"]


async def test_beheerder_may_manage(client, world, as_person):
    as_person(world.beheerder)
    assert (await client.get("/api/rates/cards")).json()["may_manage"] is True


async def test_only_beheerder_changes_rates(client, world, as_person):
    for person in (world.planner, world.lezer, world.owner, world.outsider):
        as_person(person)
        assert (
            await client.post("/api/rates/cards", json={"year": 2027})
        ).status_code == 403
        assert (
            await client.put(
                "/api/rates/cards/2026/bands/D", json={"monthly_rate_cents": 1}
            )
        ).status_code == 403
        assert (
            await client.put("/api/rates/cards/2026/scales/14", json={"category": "A"})
        ).status_code == 403
        assert (
            await client.put("/api/rates/cards/2026/status", json={"status": "closed"})
        ).status_code == 403


async def test_new_year_is_a_draft_copy(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.post("/api/rates/cards", json={"year": 2027, "copy_from": 2026})
    assert resp.status_code == 201
    card = resp.json()
    assert card["status"] == "draft"
    assert len(card["rate_bands"]) == 5
    assert {"scale": 14, "category": "D"} in card["scale_bands"]

    resp = await client.put(
        "/api/rates/cards/2027/bands/D", json={"monthly_rate_cents": 1890000}
    )
    assert resp.status_code == 200
    rates = {b["category"]: b["monthly_rate_cents"] for b in resp.json()["rate_bands"]}
    assert rates["D"] == 1890000 and rates["A"] == 900000

    resp = await client.post("/api/rates/cards", json={"year": 2027})
    assert resp.status_code == 422


async def test_unknown_year_is_not_found(client, world, as_person):
    as_person(world.beheerder)
    assert (await client.get("/api/rates/cards/2031")).status_code == 404


async def test_closed_year_needs_explicit_confirmation(
    client, world, as_person, db_session
):
    as_person(world.beheerder)
    resp = await client.put("/api/rates/cards/2026/status", json={"status": "closed"})
    assert resp.status_code == 200 and resp.json()["status"] == "closed"

    refused = await client.put(
        "/api/rates/cards/2026/bands/D", json={"monthly_rate_cents": 1900000}
    )
    assert refused.status_code == 409
    assert "gesloten" in refused.json()["detail"]
    refused = await client.put(
        "/api/rates/cards/2026/scales/14", json={"category": "E"}
    )
    assert refused.status_code == 409

    confirmed = await client.put(
        "/api/rates/cards/2026/bands/D",
        json={"monthly_rate_cents": 1900000, "confirm_closed_year": True},
    )
    assert confirmed.status_code == 200
    rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity == "rate_band",
                AuditLog.entity_id
                == f"{(await RateRepository(db_session).get_card(2026)).id}/D",
            )
        )
    ).scalars()
    assert any((row.new_value or {}).get("closed_year_override") for row in rows)

    # Reopening is a change in a closed year as well.
    assert (
        await client.put("/api/rates/cards/2026/status", json={"status": "active"})
    ).status_code == 409
    assert (
        await client.put(
            "/api/rates/cards/2026/status",
            json={"status": "active", "confirm_closed_year": True},
        )
    ).status_code == 200


async def test_invalid_input_is_refused(client, world, as_person):
    as_person(world.beheerder)
    assert (
        await client.put(
            "/api/rates/cards/2026/bands/Z", json={"monthly_rate_cents": 1}
        )
    ).status_code == 422
    assert (
        await client.put("/api/rates/cards/2026/scales/99", json={"category": "A"})
    ).status_code == 422
    assert (
        await client.put(
            "/api/rates/cards/2026/bands/D", json={"monthly_rate_cents": -5}
        )
    ).status_code == 422
