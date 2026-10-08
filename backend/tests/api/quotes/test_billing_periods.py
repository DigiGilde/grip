"""Billing per period: settle per month, deliver per period, invoice per delivery."""

import io
from datetime import date

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from grip.models.billing_delivery import BillingDelivery
from grip.models.month_close import BillingExport
from grip.services import billing_deliveries, instance_settings, rates
from grip.services.quote_document import DocumentEngineError
from tests.lifecycle import accept

# 80 percent in category D: 0.8 x 18,000.
MONTH_CENTS = 1_440_000
DETAILS = {
    "organisation": "Voorbeeldministerie",
    "address": "Postbus 1",
    "postcode_city": "1000 AA Voorbeeldstad",
    "reference": "VM-2026-118",
}


def _base(world) -> str:
    return f"/api/assignments/{world.assignment.id}"


@pytest.fixture(autouse=True)
async def _accepted(world, db_session):
    await accept(db_session, world.assignment.id)


async def _close(client, world, *months: str) -> None:
    for month in months:
        response = await client.post(f"{_base(world)}/months/{month}/close", json={})
        assert response.status_code == 200, response.text


async def _overview(client, world) -> dict:
    response = await client.get(f"{_base(world)}/billing")
    assert response.status_code == 200, response.text
    return response.json()


async def _terms(client, world, **body):
    return await client.put(f"{_base(world)}/billing/terms", json=body)


async def _deliver(client, world, period: str, via: str = "self"):
    return await client.post(
        f"{_base(world)}/billing/deliveries", json={"period_key": period, "via": via}
    )


def _period(body: dict, key: str) -> dict:
    return next(p for p in body["periods"] if p["key"] == key)


async def test_the_rhythm_follows_the_instance_until_the_assignment_says(
    act_as, world, db_session
):
    client = act_as(world.manager)
    body = await _overview(client, world)
    assert body["terms"]["rhythm"] == "quarter"
    assert body["terms"]["rhythm_is_default"] is True
    assert [p["key"] for p in body["periods"]][:3] == ["2026-Q1", "2026-Q2", "2026-Q3"]

    await instance_settings.set_values(
        db_session, {"billing.rhythm": "month"}, actor=world.beheerder
    )
    body = await _overview(client, world)
    assert body["terms"]["rhythm"] == "month"
    assert body["periods"][0]["key"] == "2026-01"

    response = await _terms(client, world, rhythm="quarter")
    assert response.status_code == 200, response.text
    assert response.json()["terms"]["rhythm_is_default"] is False
    assert response.json()["periods"][0]["key"] == "2026-Q1"


async def test_the_oldest_month_to_close_is_what_is_asked_first(act_as, world):
    client = act_as(world.manager)
    body = await _overview(client, world)
    step = body["next_step"]
    assert step["kind"] == "close_month"
    assert step["month"] == "2026-01"
    assert step["month_label"] == "januari 2026"
    assert step["amount_cents"] == MONTH_CENTS
    first = _period(body, "2026-Q1")
    assert first["state"] == "to_close"
    assert [m["state"] for m in first["months"]] == ["to_close"] * 3


async def test_a_quarter_with_an_open_month_cannot_be_delivered(act_as, world):
    client = act_as(world.manager)
    await _terms(client, world, details=DETAILS)
    await _close(client, world, "2026-01", "2026-02")
    body = await _overview(client, world)
    assert _period(body, "2026-Q1")["state"] == "to_close"
    assert _period(body, "2026-Q1")["to_deliver_cents"] is None
    assert body["next_step"]["month"] == "2026-03"
    response = await _deliver(client, world, "2026-Q1")
    assert response.status_code == 422
    assert "maart 2026 is nog niet afgesloten" in response.text


async def test_delivering_a_quarter_is_one_delivery_with_a_kept_document(
    act_as, world, db_session
):
    client = act_as(world.manager)
    await _terms(client, world, details=DETAILS)
    await _close(client, world, "2026-01", "2026-02", "2026-03")
    body = await _overview(client, world)
    quarter = _period(body, "2026-Q1")
    assert quarter["state"] == "ready"
    assert quarter["to_deliver_cents"] == 3 * MONTH_CENTS
    # Later months are open too, but the oldest open step comes first.
    assert body["next_step"]["kind"] == "deliver"
    assert body["next_step"]["period_key"] == "2026-Q1"
    assert body["next_step"]["period_label"] == "eerste kwartaal 2026"
    assert body["next_step"]["amount_cents"] == 3 * MONTH_CENTS

    try:
        response = await _deliver(client, world, "2026-Q1")
    except DocumentEngineError:
        pytest.skip("the PDF engine's system libraries are not installed here")
    assert response.status_code == 201, response.text
    quarter = _period(response.json(), "2026-Q1")
    assert quarter["state"] == "delivered"
    assert quarter["delivered_cents"] == 3 * MONTH_CENTS
    assert quarter["awaits_invoice"] is True
    [delivery] = quarter["deliveries"]
    assert delivery["total_cents"] == 3 * MONTH_CENTS
    assert delivery["via"] == "self"
    assert delivery["recipient"] is None
    assert delivery["delivered_by_name"] == "Opdracht Manager"
    assert delivery["reference"].endswith("/2026-Q1")
    assert delivery["has_document"] is True

    exports = (
        (
            await db_session.execute(
                select(BillingExport).where(
                    BillingExport.assignment_id == world.assignment.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(exports) == 3
    assert {str(e.delivery_id) for e in exports} == {delivery["id"]}

    document = await client.get(f"/api/billing/deliveries/{delivery['id']}/document")
    assert document.status_code == 200
    assert document.headers["content-type"] == "application/pdf"
    assert document.headers["content-disposition"].startswith("inline;")
    text = "\n".join(
        page.extract_text() for page in PdfReader(io.BytesIO(document.content)).pages
    ).replace("\xa0", " ")
    assert "Factuurverzoek" in text
    assert delivery["reference"] in text
    assert "Voorbeeldministerie" in text
    assert "VM-2026-118" in text
    assert "Productmanager" in text
    assert "43.200,00" in text
    # A quote names roles, and so does what follows from it.
    assert "Teamlid Voorbeeld" not in text

    # The same bytes on every request, whatever changes afterwards.
    await _terms(client, world, details={**DETAILS, "organisation": "Anders"})
    again = await client.get(f"/api/billing/deliveries/{delivery['id']}/document")
    assert again.content == document.content
    assert again.headers["x-document-sha256"] == document.headers["x-document-sha256"]

    # A second delivery of the same period has nothing to hand over.
    response = await _deliver(client, world, "2026-Q1")
    assert response.status_code == 422
    assert "niets meer aan te leveren" in response.text


async def test_without_an_invoice_address_nothing_is_delivered(act_as, world):
    client = act_as(world.manager)
    await _close(client, world, "2026-01", "2026-02", "2026-03")
    body = await _overview(client, world)
    assert set(body["terms"]["missing_details"]) == {
        "organisation",
        "address",
        "postcode_city",
    }
    response = await _deliver(client, world, "2026-Q1")
    assert response.status_code == 422
    assert "factuuradres" in response.text
    assert _period(await _overview(client, world), "2026-Q1")["state"] == "ready"


async def test_the_invoice_is_recorded_against_the_period(act_as, world):
    client = act_as(world.manager)
    await _terms(client, world, details=DETAILS)
    await _close(client, world, "2026-01", "2026-02", "2026-03")
    try:
        assert (await _deliver(client, world, "2026-Q1")).status_code == 201
    except DocumentEngineError:
        pytest.skip("the PDF engine's system libraries are not installed here")
    response = await client.post(
        f"{_base(world)}/billing/periods/2026-Q1/invoice",
        json={
            "invoice_number": "F-2026-014",
            "invoice_date": "2026-04-08",
            "amount_cents": 3 * MONTH_CENTS - 100,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    quarter = _period(body, "2026-Q1")
    assert quarter["state"] == "invoiced"
    assert quarter["invoice_numbers"] == ["F-2026-014"]
    assert quarter["invoiced_cents"] == 3 * MONTH_CENTS - 100
    assert quarter["awaits_invoice"] is False
    assert quarter["deliveries"][0]["invoice_number"] == "F-2026-014"
    assert body["invoiced_cents"] == 3 * MONTH_CENTS - 100

    again = await client.post(
        f"{_base(world)}/billing/periods/2026-Q1/invoice",
        json={
            "invoice_number": "F-2026-015",
            "invoice_date": "2026-04-09",
            "amount_cents": 1,
        },
    )
    assert again.status_code == 422


async def test_a_change_after_delivery_travels_with_the_next_delivery(
    act_as, world, db_session
):
    client = act_as(world.manager)
    await _terms(client, world, details=DETAILS)
    await _close(client, world, "2026-01", "2026-02", "2026-03")
    try:
        assert (await _deliver(client, world, "2026-Q1")).status_code == 201
    except DocumentEngineError:
        pytest.skip("the PDF engine's system libraries are not installed here")
    # Another scale with effect in the past: March costs less than was delivered.
    await rates.set_person_scale(
        db_session, world.member.id, date(2026, 3, 1), 12, actor=world.beheerder
    )
    await db_session.flush()
    body = await _overview(client, world)
    quarter = _period(body, "2026-Q1")
    march = quarter["months"][2]
    # 80 percent of the difference between category C and D.
    assert march["correction_cents"] == -240_000
    assert quarter["state"] == "ready"
    assert quarter["to_deliver_cents"] == march["correction_cents"]

    await _close(client, world, "2026-04", "2026-05", "2026-06")
    body = await _overview(client, world)
    second = _period(body, "2026-Q2")
    response = await _deliver(client, world, "2026-Q2")
    assert response.status_code == 201, response.text
    body = response.json()
    [delivery] = _period(body, "2026-Q2")["deliveries"]
    assert delivery["total_cents"] == second["closed_cents"] + march["correction_cents"]
    assert _period(body, "2026-Q1")["months"][2]["correction_cents"] == 0
    kinds = sorted(
        e.kind
        for e in (
            await db_session.execute(
                select(BillingExport).where(BillingExport.delivery_id == delivery["id"])
            )
        ).scalars()
    )
    assert kinds == ["correction", "original", "original", "original"]


async def test_names_are_on_the_specification_only_when_the_agreement_says(
    act_as, world, db_session
):
    client = act_as(world.manager)
    await _terms(client, world, details=DETAILS, names_on_specification=True)
    await _close(client, world, "2026-01", "2026-02", "2026-03")
    try:
        response = await _deliver(client, world, "2026-Q1")
    except DocumentEngineError:
        pytest.skip("the PDF engine's system libraries are not installed here")
    assert response.status_code == 201, response.text
    delivery = (await db_session.execute(select(BillingDelivery))).scalar_one()
    content = await billing_deliveries.document_content(db_session, delivery)
    assert content["with_names"] is True
    # 80 percent reads as 80, never as a power of ten.
    assert {line["fte_pct"] for line in content["lines"]} == {"80"}
    assert {line["person_name"] for line in content["lines"]} == {"Teamlid Voorbeeld"}
    # Names with rates are for who may see rates: a reader of totals may not.
    as_reader = act_as(world.lezer)
    refused = await as_reader.get(f"/api/billing/deliveries/{delivery.id}/document")
    assert refused.status_code == 403


async def test_who_may_read_and_who_may_deliver(act_as, world):
    manager = act_as(world.manager)
    await _terms(manager, world, details=DETAILS)
    await _close(manager, world, "2026-01", "2026-02", "2026-03")

    reader = act_as(world.lezer)
    body = await _overview(reader, world)
    assert body["may_deliver"] is False
    assert body["may_close"] is False
    assert _period(body, "2026-Q1")["closed_cents"] == 3 * MONTH_CENTS
    assert (await _deliver(reader, world, "2026-Q1")).status_code == 403
    assert (await _terms(reader, world, rhythm="month")).status_code == 403

    planner = act_as(world.planner)
    body = await _overview(planner, world)
    quarter = _period(body, "2026-Q1")
    assert "closed_cents" not in quarter
    assert "amount_cents" not in quarter["months"][0]
    assert "details" not in body["terms"]
    assert "amount_cents" not in body["next_step"]

    outsider = act_as(world.outsider)
    assert (await outsider.get(f"{_base(world)}/billing")).status_code == 404


async def test_the_rhythm_is_fixed_once_a_period_was_delivered(act_as, world):
    client = act_as(world.manager)
    await _terms(client, world, details=DETAILS)
    await _close(client, world, "2026-01", "2026-02", "2026-03")
    try:
        assert (await _deliver(client, world, "2026-Q1")).status_code == 201
    except DocumentEngineError:
        pytest.skip("the PDF engine's system libraries are not installed here")
    response = await _terms(client, world, rhythm="month")
    assert response.status_code == 422
    assert "ligt daarmee vast" in response.text


async def test_mailing_needs_a_recipient_and_a_relay(act_as, world, db_session):
    client = act_as(world.manager)
    await _terms(client, world, details=DETAILS)
    await _close(client, world, "2026-01", "2026-02", "2026-03")
    body = await _overview(client, world)
    assert body["can_mail"] is False
    response = await _deliver(client, world, "2026-Q1", via="mail")
    assert response.status_code == 422
    assert "geen mail" in response.text or "geen adres" in response.text


async def test_ready_periods_over_all_assignments(act_as, world):
    client = act_as(world.manager)
    await _terms(client, world, details=DETAILS)
    await _close(client, world, "2026-01", "2026-02", "2026-03")
    response = await client.get("/api/billing")
    assert response.status_code == 200, response.text
    [entry] = response.json()["assignments"]
    assert entry["assignment_name"] == "Opdracht Alfa"
    assert [p["key"] for p in entry["periods"] if p["state"] == "ready"] == ["2026-Q1"]

    try:
        batch = await client.post(
            "/api/billing/deliveries/batch",
            json={
                "items": [
                    {
                        "assignment_id": str(world.assignment.id),
                        "period_key": "2026-Q1",
                    }
                ],
                "via": "self",
            },
        )
    except DocumentEngineError:
        pytest.skip("the PDF engine's system libraries are not installed here")
    assert batch.status_code == 200, batch.text
    assert len(batch.json()["delivered"]) == 1

    # A reader without rights on the money sees no assignment here.
    planner = act_as(world.planner)
    assert (await planner.get("/api/billing")).json()["assignments"] == []


async def test_the_letter_of_a_quote_states_the_rhythm_of_the_assignment(
    world, db_session
):
    """The sentence in the letter comes from the same fact the system bills by."""
    from grip.services import quote_drafts, quote_sender

    await instance_settings.set_values(
        db_session,
        {
            quote_sender.TEXT_BLOCKS.key: [
                {
                    "key": "voorwaarden",
                    "heading": "Voorwaarden",
                    "body": "De facturatie vindt {factureren} plaats.",
                    "included": True,
                }
            ]
        },
        actor=world.beheerder,
    )
    content = await quote_drafts.start_content(db_session, world.assignment)
    [section] = [s for s in content["sections"] if s["key"] == "voorwaarden"]
    assert section["body"] == "De facturatie vindt per kwartaal plaats."

    await billing_deliveries.set_terms(
        db_session, world.assignment.id, actor=world.manager, rhythm="month"
    )
    content = await quote_drafts.start_content(db_session, world.assignment)
    [section] = [s for s in content["sections"] if s["key"] == "voorwaarden"]
    assert section["body"] == "De facturatie vindt per maand plaats."
