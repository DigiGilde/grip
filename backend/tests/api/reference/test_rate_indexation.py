"""A new rate card as an indexed copy: the arithmetic, the bounds, the audit row."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from grip.models.audit_log import AuditLog
from grip.services import rate_indexation
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.rate_indexation import indexed_rate_cents

# -- arithmetic (no database) --------------------------------------------------


@pytest.mark.parametrize(
    ("old", "pct", "rounding", "new"),
    [
        # 18,000 plus 5 percent lands on a whole euro.
        (1800000, "5", "euro", 1890000),
        # 10,333 plus 5 percent is 10,849.65: up to 10,850.
        (1033300, "5", "euro", 1085000),
        # 10,331 plus 5 percent is 10,847.55: up to 10,848.
        (1033100, "5", "euro", 1084800),
        # 10,330 plus 5 percent is 10,846.50: a half rounds up.
        (1033000, "5", "euro", 1084700),
        # 10,329 plus 5 percent is 10,845.45: down to 10,845.
        (1032900, "5", "euro", 1084500),
        (1033300, "5", "ten", 1085000),
        (1032900, "5", "ten", 1085000),
        (1033300, "5", "fifty", 1085000),
        # 18,000 plus 2.5 percent is 18,450: stays on tens and fifties.
        (1800000, "2.5", "fifty", 1845000),
        # 12,000 plus 3.3 percent is 12,396: 12,400 on tens and on fifties.
        (1200000, "3.3", "ten", 1240000),
        (1200000, "3.3", "fifty", 1240000),
        # 12,000 plus 3.1 percent is 12,372: 12,350 on fifties.
        (1200000, "3.1", "fifty", 1235000),
        (1800000, "0", "euro", 1800000),
        (1800000, "25", "euro", 2250000),
        (0, "5", "euro", 0),
    ],
)
def test_indexed_rate(old, pct, rounding, new):
    assert indexed_rate_cents(old, Decimal(pct), rounding) == new


def test_no_float_drift_on_an_awkward_percentage():
    # 1.1 percent of 1,000,001 cents: exact decimals, then one rounding.
    assert indexed_rate_cents(100000100, Decimal("1.1"), "euro") == 101100100


@pytest.mark.parametrize("pct", ["-0.01", "-5", "25.01", "100", "5.123", "NaN"])
def test_percentage_out_of_bounds_is_refused(pct):
    with pytest.raises(DomainValidationError):
        indexed_rate_cents(1800000, Decimal(pct), "euro")


def test_unknown_rounding_is_refused():
    with pytest.raises(DomainValidationError):
        indexed_rate_cents(1800000, Decimal(5), "hundred")


# -- service ---------------------------------------------------------------------


async def test_preview_creates_nothing(db_session, world):
    rates = await rate_indexation.preview_indexed_rates(
        db_session, 2026, Decimal(5), "euro"
    )
    by_category = {r.category: r for r in rates}
    assert by_category["D"].old_monthly_rate_cents == 1800000
    assert by_category["D"].new_monthly_rate_cents == 1890000
    assert by_category["D"].difference_cents == 90000
    assert len(rates) == 5
    from grip.repositories.domain import RateRepository

    assert await RateRepository(db_session).get_card(2027) is None


async def test_create_indexes_rates_and_copies_scales_unchanged(db_session, world):
    card = await rate_indexation.create_indexed_rate_card(
        db_session,
        2027,
        copy_from=2026,
        increase_pct=Decimal("5"),
        rounding="euro",
        actor=world.beheerder,
    )
    assert card.status == "draft"
    assert {b.category: b.monthly_rate_cents for b in card.rate_bands} == {
        "A": 945000,
        "B": 1260000,
        "C": 1575000,
        "D": 1890000,
        "E": 2205000,
    }
    assert {b.scale: b.category for b in card.scale_bands} == {
        8: "A",
        9: "A",
        10: "B",
        11: "B",
        12: "C",
        13: "C",
        14: "D",
        15: "D",
    }


async def test_audit_row_names_year_percentage_and_rounding(db_session, world):
    await rate_indexation.create_indexed_rate_card(
        db_session,
        2027,
        copy_from=2026,
        increase_pct=Decimal("2.50"),
        rounding="fifty",
        actor=world.beheerder,
    )
    rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity == "rate_card", AuditLog.entity_id == "2027"
            )
        )
    ).scalars()
    row = next(iter(rows))
    assert row.actor_id == world.beheerder.id
    assert row.new_value["copied_from"] == 2026
    assert row.new_value["increase_pct"] == "2.5"
    assert row.new_value["rounding"] == "fifty"
    assert row.new_value["rounding_step_cents"] == 5000
    assert row.new_value["monthly_rate_cents"]["D"] == {"old": 1800000, "new": 1845000}


async def test_existing_year_and_unknown_source_are_refused(db_session, world):
    with pytest.raises(DomainValidationError):
        await rate_indexation.create_indexed_rate_card(
            db_session,
            2026,
            copy_from=2026,
            increase_pct=Decimal(5),
            actor=world.beheerder,
        )
    with pytest.raises(NotFoundError):
        await rate_indexation.create_indexed_rate_card(
            db_session,
            2027,
            copy_from=2019,
            increase_pct=Decimal(5),
            actor=world.beheerder,
        )


# -- API ---------------------------------------------------------------------------


async def test_list_carries_the_default_increase(client, world, as_person):
    as_person(world.outsider)
    body = (await client.get("/api/rates/cards")).json()
    assert Decimal(body["default_increase_pct"]) == Decimal(5)


async def test_preview_through_the_api(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.get(
        "/api/rates/indexation-preview",
        params={"copy_from": 2026, "increase_pct": "5", "rounding": "euro"},
    )
    assert resp.status_code == 200
    body = resp.json()
    d = next(r for r in body["rates"] if r["category"] == "D")
    assert d == {
        "category": "D",
        "old_monthly_rate_cents": 1800000,
        "new_monthly_rate_cents": 1890000,
        "difference_cents": 90000,
    }
    assert (await client.get("/api/rates/cards/2027")).status_code == 404


async def test_preview_is_for_whoever_manages_rates(client, world, as_person):
    as_person(world.planner)
    resp = await client.get(
        "/api/rates/indexation-preview", params={"copy_from": 2026, "increase_pct": "5"}
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("pct", ["-1", "25.5", "5.125", "veel"])
async def test_api_refuses_a_percentage_out_of_bounds(client, world, as_person, pct):
    as_person(world.beheerder)
    resp = await client.get(
        "/api/rates/indexation-preview", params={"copy_from": 2026, "increase_pct": pct}
    )
    assert resp.status_code == 422
    resp = await client.post(
        "/api/rates/cards", json={"year": 2027, "copy_from": 2026, "increase_pct": pct}
    )
    assert resp.status_code == 422


async def test_unknown_rounding_and_source_through_the_api(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.get(
        "/api/rates/indexation-preview",
        params={"copy_from": 2026, "increase_pct": "5", "rounding": "hundred"},
    )
    assert resp.status_code == 422
    resp = await client.get(
        "/api/rates/indexation-preview", params={"copy_from": 2019, "increase_pct": "5"}
    )
    assert resp.status_code == 404


async def test_create_with_increase_through_the_api(
    client, world, as_person, db_session
):
    as_person(world.beheerder)
    resp = await client.post(
        "/api/rates/cards",
        json={"year": 2027, "copy_from": 2026, "increase_pct": "5", "rounding": "ten"},
    )
    assert resp.status_code == 201
    card = resp.json()
    assert card["status"] == "draft"
    rates = {b["category"]: b["monthly_rate_cents"] for b in card["rate_bands"]}
    assert rates["D"] == 1890000 and rates["A"] == 945000
    assert {"scale": 14, "category": "D"} in card["scale_bands"]

    # The rates of the draft stay editable per category.
    resp = await client.put(
        "/api/rates/cards/2027/bands/D", json={"monthly_rate_cents": 1900000}
    )
    assert resp.status_code == 200

    row = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity == "rate_card",
                AuditLog.entity_id == "2027",
                AuditLog.action == "create",
            )
        )
    ).scalar_one()
    assert row.new_value["increase_pct"] == "5"
    assert row.new_value["rounding"] == "ten"
    assert row.new_value["copied_from"] == 2026


async def test_copy_without_increase_keeps_the_rates(client, world, as_person):
    as_person(world.beheerder)
    resp = await client.post("/api/rates/cards", json={"year": 2027, "copy_from": 2026})
    assert resp.status_code == 201
    rates = {b["category"]: b["monthly_rate_cents"] for b in resp.json()["rate_bands"]}
    assert rates["D"] == 1800000
