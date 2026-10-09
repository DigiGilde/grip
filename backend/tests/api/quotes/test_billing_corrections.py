"""A change after delivery becomes a stored correction on its billing period.

The walk: a quarter is delivered and invoiced, a promotion is recorded late,
the difference is stored with its cause, a task asks whoever delivers to
deliver it, delivering closes it, and the invoice for it is recorded.
"""

import io
from datetime import date

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from grip.core import clock
from grip.models.billing_correction import BillingCorrection
from grip.models.billing_delivery import BillingDelivery
from grip.models.person_details import PersonScale
from grip.services import rates
from grip.services.quote_document import DocumentEngineError
from tests.lifecycle import accept

DETAILS = {
    "organisation": "Voorbeeldministerie",
    "address": "Postbus 1",
    "postcode_city": "1000 AA Voorbeeldstad",
    "reference": "VM-2026-118",
}
TITLE = "Lever de naverrekening over het eerste kwartaal van 2026 aan"


def _base(world) -> str:
    return f"/api/assignments/{world.assignment.id}"


@pytest.fixture(autouse=True)
async def _accepted(world, db_session):
    await accept(db_session, world.assignment.id)


async def _delivered_quarter(client, world) -> None:
    response = await client.put(
        f"{_base(world)}/billing/terms", json={"details": DETAILS}
    )
    assert response.status_code == 200, response.text
    for month in ("2026-01", "2026-02", "2026-03"):
        closed = await client.post(f"{_base(world)}/months/{month}/close", json={})
        assert closed.status_code == 200, closed.text
    try:
        delivered = await client.post(
            f"{_base(world)}/billing/deliveries",
            json={"period_key": "2026-Q1", "via": "self"},
        )
    except DocumentEngineError:
        pytest.skip("the PDF engine's system libraries are not installed here")
    assert delivered.status_code == 201, delivered.text


async def _invoice(client, world, number: str, cents: int):
    return await client.post(
        f"{_base(world)}/billing/periods/2026-Q1/invoice",
        json={
            "invoice_number": number,
            "invoice_date": "2026-04-08",
            "amount_cents": cents,
        },
    )


async def _rows(db_session, world) -> list[BillingCorrection]:
    return list(
        await db_session.scalars(
            select(BillingCorrection)
            .where(BillingCorrection.assignment_id == world.assignment.id)
            .order_by(BillingCorrection.arose_at)
        )
    )


async def _quarter(client, world) -> dict:
    body = (await client.get(f"{_base(world)}/billing")).json()
    return next(p for p in body["periods"] if p["key"] == "2026-Q1")


async def _open_titles(client, world) -> set[str]:
    body = (
        await client.get(f"/api/tasks/cases/assignment/{world.assignment.id}")
    ).json()
    return {
        task["headline"]
        for track in body["tracks"]
        for task in track["tasks"]
        if task["status"] in ("todo", "doing", "waiting")
    }


async def _period_course(client, world) -> dict:
    body = (
        await client.get(f"/api/tasks/cases/assignment/{world.assignment.id}/course")
    ).json()
    return next(part for part in body["parts"] if part["subject_key"] == "2026-Q1")


async def test_invoiced_then_a_late_promotion_the_task_the_delivery_and_the_invoice(
    act_as, world, db_session
):
    client = act_as(world.manager)
    await _delivered_quarter(client, world)
    first = (
        await db_session.scalars(
            select(BillingDelivery).where(
                BillingDelivery.assignment_id == world.assignment.id
            )
        )
    ).one()
    quarter = await _quarter(client, world)
    assert (
        await _invoice(client, world, "F-2026-014", quarter["delivered_cents"])
    ).status_code == 201
    assert await _rows(db_session, world) == []
    assert TITLE not in await _open_titles(client, world)

    # A promotion decided later, with effect from March.
    await rates.set_person_scale(
        db_session, world.member.id, date(2026, 3, 1), 12, actor=world.beheerder
    )
    await db_session.flush()

    [row] = await _rows(db_session, world)
    assert row.period_key == "2026-Q1"
    assert row.amount_cents == -240_000
    assert row.months == {"2026-03": -240_000}
    assert row.follows_delivery_id == first.id
    assert row.arose_by_id == world.beheerder.id
    assert row.delivered_at is None
    assert [entry["cause"] for entry in row.causes] == [
        "inzetschaal gewijzigd met ingang van 1 maart 2026"
    ]

    # The screens read the stored row.
    quarter = await _quarter(client, world)
    assert quarter["state"] == "ready" and quarter["correction"] is True
    assert quarter["to_deliver_cents"] == -240_000
    assert (
        quarter["correction_cause"]
        == "inzetschaal gewijzigd met ingang van 1 maart 2026"
    )

    # The task for whoever delivers, with the amount and the cause.
    assert TITLE in await _open_titles(client, world)
    part = await _period_course(client, world)
    assert [step["label"] for step in part["steps"]][-1] == "Naverrekening"
    assert part["current_label"] == "Naverrekening"
    told = part["next"]
    assert told["mine"] is True
    assert told["headline"] == TITLE
    assert "-€ 2.400" in told["sentence"]
    assert "inzetschaal gewijzigd" in told["sentence"]
    assert told["action_href"].endswith("/maandafsluiting?periode=2026-Q1")

    # Delivering the difference closes the correction and the task.
    delivered = await client.post(
        f"{_base(world)}/billing/deliveries",
        json={"period_key": "2026-Q1", "via": "self"},
    )
    assert delivered.status_code == 201, delivered.text
    await db_session.refresh(row)
    assert row.delivered_at is not None
    assert row.delivered_delivery_id is not None
    assert row.delivered_delivery_id != first.id

    # The document says what the screen and the task say: per month the
    # difference, why, and the request it comes on top of.
    page = (
        await client.get(f"/api/billing/deliveries/{row.delivered_delivery_id}")
    ).json()
    assert page["corrections"] == [
        {
            "month": "2026-03",
            "month_label": "maart 2026",
            "amount_cents": -240_000,
            "cause": "inzetschaal gewijzigd met ingang van 1 maart 2026",
            "follows_reference": first.reference,
            "follows_delivered_on": clock.local_date(first.delivered_at).isoformat(),
        }
    ]
    document = await client.get(
        f"/api/billing/deliveries/{row.delivered_delivery_id}/document"
    )
    text = " ".join(
        " ".join(sheet.extract_text().split())
        for sheet in PdfReader(io.BytesIO(document.content)).pages
    )
    assert "Naverrekening maart 2026: -€ 2.400,00." in text
    assert "Inzetschaal gewijzigd met ingang van 1 maart 2026." in text
    assert f"Dit bedrag gaat af van factuurverzoek {first.reference} van" in text
    # Why names a date or a rate card, never whose scale it was: this
    # agreement keeps names off the specification.
    assert world.member.name not in text

    quarter = await _quarter(client, world)
    assert quarter["correction"] is False
    assert quarter["state"] == "delivered"
    assert TITLE not in await _open_titles(client, world)
    part = await _period_course(client, world)
    assert "Naverrekening" not in [step["label"] for step in part["steps"]]

    # And the invoice (here a credit) for it.
    credit = await _invoice(client, world, "F-2026-031", -240_000)
    assert credit.status_code == 201, credit.text
    quarter = await _quarter(client, world)
    assert quarter["state"] == "invoiced"
    assert quarter["invoice_numbers"] == ["F-2026-014", "F-2026-031"]


async def test_delivered_and_not_yet_invoiced_is_a_difference_too(
    act_as, world, db_session
):
    """The first request stands as it was delivered; the change is a
    difference on top of it, also while no invoice was recorded yet."""
    client = act_as(world.manager)
    await _delivered_quarter(client, world)
    before = (await _quarter(client, world))["delivered_cents"]
    await rates.set_person_scale(
        db_session, world.member.id, date(2026, 3, 1), 12, actor=world.beheerder
    )
    await db_session.flush()
    [row] = await _rows(db_session, world)
    assert row.amount_cents == -240_000
    quarter = await _quarter(client, world)
    assert quarter["correction"] is True
    assert quarter["delivered_cents"] == before
    assert TITLE in await _open_titles(client, world)

    delivered = await client.post(
        f"{_base(world)}/billing/deliveries",
        json={"period_key": "2026-Q1", "via": "self"},
    )
    assert delivered.status_code == 201, delivered.text
    quarter = await _quarter(client, world)
    assert quarter["delivered_cents"] == before - 240_000
    assert len(quarter["deliveries"]) == 2
    assert TITLE not in await _open_titles(client, world)


async def test_a_change_that_is_undone_before_delivery_leaves_nothing(
    act_as, world, db_session
):
    client = act_as(world.manager)
    await _delivered_quarter(client, world)
    old = (
        await db_session.scalars(
            select(PersonScale.billing_scale)
            .where(PersonScale.person_id == world.member.id)
            .order_by(PersonScale.valid_from.desc())
        )
    ).first()
    await rates.set_person_scale(
        db_session, world.member.id, date(2026, 3, 1), 12, actor=world.beheerder
    )
    await db_session.flush()
    assert len(await _rows(db_session, world)) == 1
    assert TITLE in await _open_titles(client, world)

    await rates.set_person_scale(
        db_session, world.member.id, date(2026, 3, 1), old, actor=world.beheerder
    )
    await db_session.flush()
    assert await _rows(db_session, world) == []
    quarter = await _quarter(client, world)
    assert quarter["correction"] is False and quarter["state"] == "delivered"
    assert TITLE not in await _open_titles(client, world)


async def test_two_changes_before_delivery_are_one_correction_with_both_causes(
    act_as, world, db_session
):
    client = act_as(world.manager)
    await _delivered_quarter(client, world)
    await rates.set_person_scale(
        db_session, world.member.id, date(2026, 3, 1), 12, actor=world.beheerder
    )
    await db_session.flush()
    await rates.set_person_scale(
        db_session, world.member.id, date(2026, 2, 1), 12, actor=world.beheerder
    )
    await db_session.flush()

    [row] = await _rows(db_session, world)
    assert row.months == {"2026-02": -240_000, "2026-03": -240_000}
    assert row.amount_cents == -480_000
    assert [entry["cause"] for entry in row.causes] == [
        "inzetschaal gewijzigd met ingang van 1 maart 2026",
        "inzetschaal gewijzigd met ingang van 1 februari 2026",
    ]
    quarter = await _quarter(client, world)
    assert quarter["to_deliver_cents"] == -480_000
    assert (
        "1 maart 2026; inzetschaal gewijzigd met ingang van 1 februari 2026"
        in quarter["correction_cause"]
    )
    # Still one task.
    body = (
        await client.get(f"/api/tasks/cases/assignment/{world.assignment.id}")
    ).json()
    assert [
        task["headline"]
        for track in body["tracks"]
        for task in track["tasks"]
        if task["headline"] == TITLE
    ] == [TITLE]


async def test_a_rate_changed_on_a_settled_card_is_a_difference_too(
    act_as, world, db_session
):
    """A rate that changes on the card that priced a delivered period leaves
    a correction, like a card that takes effect does."""
    client = act_as(world.manager)
    await _delivered_quarter(client, world)
    assert await _rows(db_session, world) == []
    card = await rates.get_card(db_session, 2026)
    for band in list(card.rate_bands):
        await rates.set_rate_band(
            db_session,
            2026,
            band.category,
            band.monthly_rate_cents + 100_00,
            actor=world.beheerder,
        )
    await db_session.flush()
    [row] = await _rows(db_session, world)
    assert row.amount_cents > 0
    assert "Tarieven 2026" in str(row.causes)
    assert (await _quarter(client, world))["correction"] is True
