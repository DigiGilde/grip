"""Delivered and invoiced: three facts, and no figure that says more than grip knows."""

from datetime import date
from uuid import uuid4

import pytest

from grip.core.audit import UPDATE
from grip.models.audit_log import AuditLog
from grip.services import events, outgoing_invoices
from tests.lifecycle import accept

# 80 percent in category D: 0.8 x 18,000.
MONTH_CENTS = 1_440_000


def _base(world) -> str:
    return f"/api/assignments/{world.assignment.id}"


@pytest.fixture(autouse=True)
async def _accepted(world, db_session):
    """Billing data needs a formally accepted assignment."""
    await accept(db_session, world.assignment.id)


async def _close(client, world, month: str) -> None:
    response = await client.post(f"{_base(world)}/months/{month}/close", json={})
    assert response.status_code == 200, response.text


async def _deliver(client, world, month: str) -> str:
    response = await client.post(f"{_base(world)}/months/{month}/billing-exports")
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _status(client, world, **params) -> dict:
    response = await client.get(f"{_base(world)}/billing-status", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _record(
    client, world, export_ids, *, number="F-2026-001", amount=MONTH_CENTS
):
    return await client.post(
        f"{_base(world)}/outgoing-invoices",
        json={
            "export_ids": export_ids,
            "invoice_number": number,
            "invoice_date": "2026-04-03",
            "amount_cents": amount,
        },
    )


async def test_a_closed_month_is_first_only_to_deliver(act_as, world):
    client = act_as(world.manager)
    await _close(client, world, "2026-01")
    body = await _status(client, world)
    assert body["billable"] is True
    assert body["deliverable_cents"] == MONTH_CENTS
    assert body["delivered_cents"] == 0
    assert body["to_deliver_cents"] == MONTH_CENTS
    assert body["invoiced_cents"] == 0
    assert body["to_invoice_cents"] == 0
    assert [(m["month"], m["state"]) for m in body["months"]] == [
        ("2026-01", "not_delivered")
    ]
    assert body["invoices"] == []


async def test_an_export_is_a_delivery_and_not_an_invoice(act_as, world):
    """The defect this fixes: an export used to count as invoiced."""
    client = act_as(world.manager)
    await _close(client, world, "2026-01")
    export_id = await _deliver(client, world, "2026-01")
    body = await _status(client, world)
    assert body["delivered_cents"] == MONTH_CENTS
    assert body["to_deliver_cents"] == 0
    assert body["invoiced_cents"] == 0
    assert body["to_invoice_cents"] == MONTH_CENTS
    month = body["months"][0]
    assert month["state"] == "delivered"
    assert month["export_id"] == export_id
    assert month["delivered_by_name"] == "Opdracht Manager"
    assert month["invoice_number"] is None
    assert month["invoiced_cents"] is None


async def test_recording_an_invoice_makes_it_invoiced(act_as, world, db_session):
    seen = []

    async def handler(_session, event_type, payload):
        seen.append((event_type, payload))

    events.register_handler(events.INVOICE_RECORDED, handler)
    client = act_as(world.manager)
    await _close(client, world, "2026-01")
    export_id = await _deliver(client, world, "2026-01")
    response = await _record(client, world, [export_id])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["invoiced_cents"] == MONTH_CENTS
    assert body["to_invoice_cents"] == 0
    month = body["months"][0]
    assert month["state"] == "invoiced"
    assert month["invoice_number"] == "F-2026-001"
    assert month["invoice_date"] == "2026-04-03"
    invoice = body["invoices"][0]
    assert invoice["amount_cents"] == MONTH_CENTS
    assert invoice["delivered_cents"] == MONTH_CENTS
    assert invoice["difference_cents"] == 0
    assert invoice["months"] == ["2026-01"]
    assert invoice["source"] == "manual"
    assert invoice["recorded_by_name"] == "Opdracht Manager"

    assert [event_type for event_type, _ in seen] == ["invoice.recorded"]
    payload = seen[0][1]
    assert payload["invoice_number"] == "F-2026-001"
    assert payload["amount_cents"] == MONTH_CENTS
    assert payload["months"] == ["2026-01"]
    assert payload["assignment_id"] == str(world.assignment.id)


async def test_one_invoice_for_several_months_and_a_difference(act_as, world):
    client = act_as(world.manager)
    exports = []
    for month in ("2026-01", "2026-02", "2026-03"):
        await _close(client, world, month)
        exports.append(await _deliver(client, world, month))

    proposal = await client.get(
        f"{_base(world)}/outgoing-invoices/proposal",
        params=[("export_id", exports[0]), ("export_id", exports[1])],
    )
    assert proposal.json() == {
        "months": ["2026-01", "2026-02"],
        "delivered_cents": 2 * MONTH_CENTS,
    }

    # The invoice says 100 euros less than was delivered: recorded, and shown.
    response = await _record(
        client, world, exports[:2], amount=2 * MONTH_CENTS - 10_000
    )
    assert response.status_code == 201, response.text
    body = response.json()
    invoice = body["invoices"][0]
    assert invoice["months"] == ["2026-01", "2026-02"]
    assert invoice["difference_cents"] == -10_000
    assert body["delivered_cents"] == 3 * MONTH_CENTS
    assert body["invoiced_cents"] == 2 * MONTH_CENTS - 10_000
    assert body["to_invoice_cents"] == MONTH_CENTS + 10_000
    states = {m["month"]: m for m in body["months"]}
    assert states["2026-01"]["state"] == "invoiced"
    assert states["2026-02"]["state"] == "invoiced"
    assert states["2026-03"]["state"] == "delivered"
    # The amount is spread over the months and adds up to the invoice.
    assert (
        states["2026-01"]["invoiced_cents"] + states["2026-02"]["invoiced_cents"]
        == 2 * MONTH_CENTS - 10_000
    )


async def test_figures_per_year_follow_the_month(act_as, world, db_session):
    position = await outgoing_invoices.billing_position(
        db_session, world.assignment.id, year=2027
    )
    assert position.delivered_cents == 0
    assert position.months == ()
    client = act_as(world.manager)
    await _close(client, world, "2026-01")
    export_id = await _deliver(client, world, "2026-01")
    await _record(client, world, [export_id])
    assert (await _status(client, world, year=2026))["invoiced_cents"] == MONTH_CENTS
    other_year = await _status(client, world, year=2027)
    assert other_year["invoiced_cents"] == 0
    assert other_year["delivered_cents"] == 0
    assert other_year["months"] == []
    positions = await outgoing_invoices.billing_positions(
        db_session, [world.assignment.id], year=2026
    )
    assert positions[world.assignment.id].to_invoice_cents == 0


async def test_what_cannot_be_recorded(act_as, world):
    client = act_as(world.manager)
    await _close(client, world, "2026-01")
    export_id = await _deliver(client, world, "2026-01")

    # A month that was not delivered has nothing to invoice.
    assert (await _record(client, world, [])).status_code == 422
    assert (await _record(client, world, [str(world.line.id)])).status_code == 422
    # Not before it was sent.
    future = await client.post(
        f"{_base(world)}/outgoing-invoices",
        json={
            "export_ids": [export_id],
            "invoice_number": "F-1",
            "invoice_date": "2099-01-01",
            "amount_cents": MONTH_CENTS,
        },
    )
    assert future.status_code == 422
    assert "toekomst" in future.json()["detail"]
    assert (await _record(client, world, [export_id], number="   ")).status_code == 422

    assert (await _record(client, world, [export_id])).status_code == 201
    # A delivery is on one invoice, and a number is used once.
    again = await _record(client, world, [export_id], number="F-2026-002")
    assert again.status_code == 422
    assert "al een factuur" in again.json()["detail"]
    await _close(client, world, "2026-02")
    second = await _deliver(client, world, "2026-02")
    same_number = await _record(client, world, [second], number="f-2026-001")
    assert same_number.status_code == 422
    assert "al vastgelegd" in same_number.json()["detail"]


async def test_who_may_record_and_who_may_read(act_as, world):
    client = act_as(world.manager)
    await _close(client, world, "2026-01")
    export_id = await _deliver(client, world, "2026-01")
    await _close(client, world, "2026-02")
    second = await _deliver(client, world, "2026-02")

    for person in (world.lezer, world.planner, world.member):
        response = await _record(act_as(person), world, [export_id])
        assert response.status_code == 403, person.email
    assert (
        await _record(act_as(world.outsider), world, [export_id])
    ).status_code == 404

    # The beheerder may, besides whoever manages the assignment.
    assert (
        await _record(act_as(world.beheerder), world, [export_id])
    ).status_code == 201
    assert (
        await _record(act_as(world.manager), world, [second], number="F-2026-002")
    ).status_code == 201

    # Reading follows class B: the lezer sees it, without the right to record.
    body = await _status(act_as(world.lezer), world)
    assert body["invoiced_cents"] == 2 * MONTH_CENTS
    assert body["may_record_invoice"] is False
    assert len(body["invoices"]) == 2
    # The planner and a member see no amounts, no months and no invoices.
    for person in (world.planner, world.member):
        body = await _status(act_as(person), world)
        assert not body.get("months")
        assert not body.get("invoices")
        for hidden in ("delivered_cents", "invoiced_cents", "to_invoice_cents"):
            assert hidden not in body, (person.email, hidden)
    assert (
        await act_as(world.outsider).get(f"{_base(world)}/billing-status")
    ).status_code == 404
    assert (await _status(act_as(world.manager), world))["may_record_invoice"] is True


async def test_correcting_leaves_an_audit_trail(act_as, world, db_session):
    client = act_as(world.manager)
    await _close(client, world, "2026-01")
    export_id = await _deliver(client, world, "2026-01")
    invoice_id = (await _record(client, world, [export_id])).json()["invoices"][0]["id"]

    response = await client.patch(
        f"/api/outgoing-invoices/{invoice_id}",
        json={"amount_cents": MONTH_CENTS + 500, "invoice_number": "F-2026-009"},
    )
    assert response.status_code == 200, response.text
    invoice = response.json()["invoices"][0]
    assert invoice["invoice_number"] == "F-2026-009"
    assert invoice["difference_cents"] == 500
    assert response.json()["invoiced_cents"] == MONTH_CENTS + 500

    rows = (
        await db_session.execute(
            AuditLog.__table__.select().where(
                AuditLog.entity == "outgoing_invoice", AuditLog.action == UPDATE
            )
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].old_value == {
        "amount_cents": MONTH_CENTS,
        "invoice_number": "F-2026-001",
    }
    assert rows[0].new_value == {
        "amount_cents": MONTH_CENTS + 500,
        "invoice_number": "F-2026-009",
    }

    refused = await act_as(world.lezer).patch(
        f"/api/outgoing-invoices/{invoice_id}", json={"amount_cents": 1}
    )
    assert refused.status_code == 403


async def test_withdrawing_puts_the_month_back_to_delivered(act_as, world):
    seen = []

    async def handler(_session, event_type, payload):
        seen.append(payload)

    events.register_handler(events.INVOICE_WITHDRAWN, handler)
    client = act_as(world.manager)
    await _close(client, world, "2026-01")
    export_id = await _deliver(client, world, "2026-01")
    invoice_id = (await _record(client, world, [export_id])).json()["invoices"][0]["id"]

    no_reason = await client.post(
        f"/api/outgoing-invoices/{invoice_id}/withdraw", json={"reason": " "}
    )
    assert no_reason.status_code == 422
    response = await client.post(
        f"/api/outgoing-invoices/{invoice_id}/withdraw",
        json={"reason": "Bij de verkeerde opdracht vastgelegd"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["invoiced_cents"] == 0
    assert body["to_invoice_cents"] == MONTH_CENTS
    assert body["months"][0]["state"] == "delivered"
    withdrawn = body["invoices"][0]
    assert withdrawn["withdrawn_reason"] == "Bij de verkeerde opdracht vastgelegd"
    assert withdrawn["withdrawn_by_name"] == "Opdracht Manager"
    assert seen and seen[0]["reason"] == "Bij de verkeerde opdracht vastgelegd"

    # The delivery is free again, and so is the number.
    assert (await _record(client, world, [export_id])).status_code == 201
    # A withdrawn invoice takes no further change.
    assert (
        await client.patch(f"/api/outgoing-invoices/{invoice_id}", json={"note": "x"})
    ).status_code == 422


async def test_reopening_after_an_invoice_keeps_the_fact(act_as, world):
    client = act_as(world.manager)
    await _close(client, world, "2026-01")
    export_id = await _deliver(client, world, "2026-01")
    await _record(client, world, [export_id])

    reopened = await act_as(world.beheerder).post(
        f"{_base(world)}/months/2026-01/reopen", json={"reason": "Inzet was lager"}
    )
    assert reopened.status_code == 200, reopened.text
    body = await _status(act_as(world.manager), world)
    month = body["months"][0]
    # An invoice was sent; reopening does not undo that.
    assert month["state"] == "invoiced"
    assert month["closed"] is False
    assert month["invoice_on_earlier_delivery"] is True
    assert body["invoiced_cents"] == MONTH_CENTS
    # Nothing is delivered for the month as it stands now.
    assert body["delivered_cents"] == 0
    assert body["to_invoice_cents"] == -MONTH_CENTS

    # Closed again at less, and delivered again: the difference is visible.
    client = act_as(world.manager)
    await client.post(
        f"{_base(world)}/months/2026-01/close",
        json={
            "established": [
                {"allocation_id": str(world.allocation.id), "fte_pct": "40"}
            ]
        },
    )
    await _deliver(client, world, "2026-01")
    body = await _status(client, world)
    month = body["months"][0]
    assert month["closed"] is True
    assert month["delivered_cents"] == MONTH_CENTS // 2
    assert month["invoice_on_earlier_delivery"] is True
    assert body["to_invoice_cents"] == -(MONTH_CENTS // 2)


async def test_the_csv_says_nothing_about_an_invoice(act_as, world):
    client = act_as(world.manager)
    await _close(client, world, "2026-01")
    export_id = await _deliver(client, world, "2026-01")
    await _record(client, world, [export_id])
    text = (await client.get(f"/api/billing-exports/{export_id}/csv")).text.lower()
    for word in ("factuur", "invoice", "gefactureerd", "f-2026-001"):
        assert word not in text, word


def test_spread_adds_up_exactly():
    assert outgoing_invoices.spread(100, [1, 1, 1]) == [33, 33, 34]
    assert outgoing_invoices.spread(1000, [300, 700]) == [300, 700]
    assert outgoing_invoices.spread(-101, [1, 1]) == [-51, -50]
    assert sum(outgoing_invoices.spread(-101, [1, 1])) == -101
    assert outgoing_invoices.spread(90, [0, 0, 0]) == [30, 30, 30]
    assert outgoing_invoices.spread(5, []) == []


def test_nothing_is_invoiced_without_a_record():
    """A position built from months without an invoice has nothing invoiced."""
    month = outgoing_invoices.MonthBilling(
        month=date(2026, 1, 1),
        closed=True,
        state=outgoing_invoices.DELIVERED,
        deliverable_cents=100,
        export_id=None,
        delivered_at=None,
        delivered_by_name=None,
        delivered_cents=100,
        invoice_id=None,
        invoice_number=None,
        invoice_date=None,
        invoiced_cents=None,
        invoice_on_earlier_delivery=False,
    )
    position = outgoing_invoices.position_from_months(
        uuid4(), [month], year=None, billable=True
    )
    assert position.invoiced_cents == 0
    assert position.to_invoice_cents == 100
    assert position.to_deliver_cents == 0
