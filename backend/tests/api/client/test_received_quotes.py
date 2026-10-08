"""Received quotes: the list, the frozen snapshot, deciding and delivery."""

from __future__ import annotations

from sqlalchemy import select

from grip.federation.events import register_event_handlers
from grip.federation.models import OUTBOX_SENT, FederationOutbox


async def test_list_shows_received_quotes_and_who_may_decide(
    client, cast, act_as, received
):
    act_as(cast.signer)
    (row,) = (await client.get("/api/received-quotes")).json()["items"]
    assert row["id"] == str(received.quote.id) and row["status"] == "issued"
    assert row["assignment_name"] == "Opdracht Alfa"
    assert row["contractor_name"] == "Voorbeeldgilde"
    assert row["total_cents"] == received.quote.total_cents
    assert row["may_decide"] is True

    # The requester owns the assignment and reads the quote, but does not sign.
    act_as(cast.requester)
    (row,) = (await client.get("/api/received-quotes")).json()["items"]
    assert row["may_decide"] is False and "total_cents" in row

    act_as(cast.planner)
    (row,) = (await client.get("/api/received-quotes")).json()["items"]
    assert "total_cents" not in row and row["may_decide"] is False

    act_as(cast.outsider)
    assert (await client.get("/api/received-quotes")).json()["items"] == []


async def test_detail_is_the_snapshot_as_issued_with_its_hash(
    client, cast, act_as, received
):
    act_as(cast.signer)
    response = await client.get(f"/api/received-quotes/{received.quote.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["may_decide"] is True and body["deliveries"] == []
    quote = body["quote"]
    assert quote["snapshot_hash"] == received.quote.snapshot_hash
    assert quote["total_cents"] == 6 * 1440000
    (line,) = quote["content"]["lines"]
    assert line["description"] == "Productmanager" and line["fte"] == "0.8"

    # Without class B the content, the hash and the amounts are absent.
    act_as(cast.planner)
    body = (await client.get(f"/api/received-quotes/{received.quote.id}")).json()
    assert "snapshot_hash" not in body["quote"] and "content" not in body["quote"]
    assert "6 * 1440000" not in str(body) and str(6 * 1440000) not in str(body)

    act_as(cast.outsider)
    hidden = await client.get(f"/api/received-quotes/{received.quote.id}")
    assert hidden.status_code == 404
    missing = await client.get(
        "/api/received-quotes/00000000-0000-4000-8000-000000000000"
    )
    assert missing.status_code == 404


async def test_decision_and_its_delivery_show_on_the_quote(
    client, db_session, cast, act_as, received
):
    register_event_handlers()
    act_as(cast.signer)
    accepted = await client.post(
        f"/api/received-quotes/{received.quote.id}/acceptance",
        json={"signer_function": "Directeur"},
    )
    assert accepted.status_code == 201, accepted.text

    body = (await client.get(f"/api/received-quotes/{received.quote.id}")).json()
    assert body["quote"]["status"] == "accepted" and body["may_decide"] is False
    assert body["quote"]["acceptance"]["form"] == "own_instance"
    (delivery,) = body["deliveries"]
    assert delivery["operation"] == "sendAcceptance"
    assert delivery["status"] == "pending" and delivery["sent_at"] is None

    # The worker delivered it.
    queued = await db_session.scalar(
        select(FederationOutbox).where(FederationOutbox.operation == "sendAcceptance")
    )
    queued.status = OUTBOX_SENT
    await db_session.flush()
    body = (await client.get(f"/api/received-quotes/{received.quote.id}")).json()
    assert body["deliveries"][0]["status"] == "sent"

    (row,) = (await client.get("/api/received-quotes")).json()["items"]
    assert row["status"] == "accepted" and row["may_decide"] is False


async def test_a_quote_this_instance_issued_is_not_a_received_one(
    client, db_session, cast, act_as
):
    from datetime import date
    from decimal import Decimal

    from grip.services import assignments, quotes, rates

    await rates.create_rate_card(db_session, 2026, actor=cast.beheerder)
    await rates.set_rate_band(db_session, 2026, "D", 1800000, actor=cast.beheerder)
    await rates.set_rate_card_status(db_session, 2026, "active", actor=cast.beheerder)
    someone = await assignments.upsert_organisation(
        db_session, name="Voorbeeldafnemer", tooi_uri=None
    )
    own_work = await assignments.create_assignment(
        db_session,
        name="Eigen werk",
        actor=cast.beheerder,
        client_organisation_id=someone.id,
    )
    await assignments.add_budget_line(
        db_session,
        own_work.id,
        description="Developer",
        kind="personnel",
        role="Developer",
        fte=Decimal("1"),
        rate_category="D",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        actor=cast.beheerder,
    )
    issued = await quotes.issue_quote(db_session, own_work.id, actor=cast.beheerder)
    act_as(cast.beheerder)
    assert (await client.get("/api/received-quotes")).json()["items"] == []
    response = await client.get(f"/api/received-quotes/{issued.id}")
    assert response.status_code == 404
