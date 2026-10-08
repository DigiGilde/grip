"""The bridge: what another instance gets to see, and what it may not do.

The exchange of a request, a quote and an acceptance between two instances
is covered in ``test_two_instances``. These tests cover the hand-over to a
parent instance, billing data for a client, the corpus view, and refusals.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from grip.access import LocalDecider
from grip.access.peer_deps import CORPUS_SPENDING, NO_CORPUS_RELATION, PeerAccess
from grip.access.sql import SqlRelationSource
from grip.calc import Month
from grip.core.config import get_settings
from grip.federation import terms
from grip.federation.bridge import register_bridge
from grip.federation.bridge.organisations import from_reference, own_organisation
from grip.federation.bridge.settings import get_bridge_settings
from grip.federation.models import PEER_ROLE_CORPUS, PEER_ROLE_PARENT
from grip.models.person import Person
from grip.services import assignments, costs, month_close, quotes, rates

from .conftest import CLIENT_BASE, CLIENT_PEER_ID, as_peer, t

PARENT_PEER_ID = "00000000000000000040"
CORPUS_PEER_ID = "00000000000000000050"
CORPUS_BASE = "https://corpus.voorbeeldministerie.example"
NODE_URI = f"{CORPUS_BASE}/id/node/0b6f1c1e-5a0e-4a53-9a43-0d3e1d6b2a03"
ASSIGNMENT_UUID = "3f2a8c54-6d1b-4f0e-9a77-1c2b3d4e5f60"
ASSIGNMENT_URI = f"{CLIENT_BASE}/id/opdracht/{ASSIGNMENT_UUID}"
CLIENT = {
    "tooi_uri": "https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
    "name": "Voorbeeldministerie",
    "unit_key": "directie-voorbeeld",
    "instance_uri": CLIENT_BASE,
}


@pytest.fixture(autouse=True)
def _bridge(monkeypatch):
    monkeypatch.setattr(
        get_settings(),
        "INSTANCE_TOOI_URI",
        "https://identifier.overheid.nl/tooi/id/oorg/oorg00000",
    )
    register_bridge()
    get_bridge_settings.cache_clear()
    yield
    get_bridge_settings.cache_clear()


@pytest.fixture
async def world(db_session, make_peer):
    """This instance as contractor of one assignment, with one person on it."""
    for year, cents in ((2026, 1800000), (2027, 1890000)):
        await rates.create_rate_card(db_session, year, actor=None)
        await rates.set_rate_band(db_session, year, "D", cents, actor=None)
        await rates.set_scale_band(db_session, year, 14, "D", actor=None)
        await rates.set_rate_card_status(db_session, year, "active", actor=None)
    person = Person(name="Medewerker Voorbeeld", email="medewerker@example.org")
    db_session.add(person)
    await db_session.flush()
    await rates.set_person_scale(
        db_session, person.id, date(2026, 1, 1), 14, actor=None
    )

    client = await from_reference(db_session, CLIENT)
    own = await own_organisation(db_session)
    assignment = await assignments.create_assignment(
        db_session,
        name="Opdracht Alfa",
        actor=None,
        traffic_form="federated",
        client_organisation_id=client.id,
        contractor_organisation_id=own.id,
        context_refs=[NODE_URI],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        uri=ASSIGNMENT_URI,
    )
    line = await assignments.add_budget_line(
        db_session,
        assignment.id,
        description="Productmanager",
        kind="personnel",
        role="Productmanager",
        fte=Decimal("0.8"),
        rate_category="D",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        actor=None,
    )
    allocation = await assignments.add_allocation(
        db_session,
        line.id,
        person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal("80"),
        actor=None,
    )
    await month_close.close_month(
        db_session,
        assignment.id,
        Month(2026, 1),
        actor=None,
        established={allocation.id: Decimal("60")},
        closed_at=datetime(2026, 2, 3, 9, 0, tzinfo=UTC),
    )
    item = await costs.create_cost_item(
        db_session, description="Hosting", actor=None, budgeted_cents=1200000
    )
    await costs.add_invoice_line(
        db_session,
        item.id,
        kind="actual",
        amount_cents=1500000,
        actor=None,
        period=date(2026, 3, 1),
    )
    await costs.set_coverage(db_session, item.id, line.id, Decimal("30"), actor=None)

    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE, financial_inspection=True)
    await make_peer(
        PARENT_PEER_ID, base_uri="https://grip.moeder.example", role=PEER_ROLE_PARENT
    )
    await make_peer(CORPUS_PEER_ID, base_uri=CORPUS_BASE, role=PEER_ROLE_CORPUS)
    await db_session.flush()
    return {"assignment": assignment, "line": line, "person": person}


async def _get(fed_client, path, peer_id, **params):
    return await fed_client.get(path, params=params, headers=as_peer(peer_id))


# --- the client ------------------------------------------------------------


async def test_client_reads_its_assignment_without_money_or_names(fed_client, world):
    response = await _get(
        fed_client, f"/v1/opdrachten/{ASSIGNMENT_UUID}", CLIENT_PEER_ID
    )
    assert response.status_code == 200, response.text
    body = terms.from_contract(response.json())
    assert body["uri"] == ASSIGNMENT_URI and body["status"] == "draft"
    assert body["client"]["instance_uri"] == CLIENT_BASE
    assert "spending" not in body
    assert "Medewerker" not in response.text


async def test_billing_data_of_a_closed_month_per_line_without_names(fed_client, world):
    path = f"/v1/opdrachten/{ASSIGNMENT_UUID}/factuurgegevens"
    closed = await _get(fed_client, path, CLIENT_PEER_ID, maand="2026-01")
    assert closed.status_code == 200, closed.text
    body = terms.from_contract(closed.json())
    # 60 percent established, category D in 2026.
    assert body["total"]["amount_cents"] == 1080000
    assert body["basis"] == "actual_allocation"
    assert [line["description"] for line in body["lines"]] == ["Productmanager"]
    assert "Medewerker" not in closed.text

    still_open = await _get(fed_client, path, CLIENT_PEER_ID, maand="2026-02")
    assert still_open.status_code == 404, "an open month has no billing data"


async def test_client_without_the_financial_part_is_refused_not_told_404(
    fed_client, db_session, world
):
    from sqlalchemy import select

    from grip.federation.models import Peer

    peer = await db_session.scalar(select(Peer).where(Peer.peer_id == CLIENT_PEER_ID))
    peer.financial_inspection = False
    await db_session.flush()
    path = f"/v1/opdrachten/{ASSIGNMENT_UUID}/factuurgegevens"
    response = await _get(fed_client, path, CLIENT_PEER_ID, maand="2026-01")
    assert response.status_code == 403
    assert "op verzoek" in response.json()["detail"]


async def test_another_instance_does_not_see_the_assignment(
    fed_client, world, make_peer
):
    await make_peer("00000000000000000060", base_uri="https://grip.ander.example")
    for suffix in ("", "/voortgang", "/uitputting"):
        response = await _get(
            fed_client,
            f"/v1/opdrachten/{ASSIGNMENT_UUID}{suffix}",
            "00000000000000000060",
        )
        assert response.status_code == 404, suffix


# --- the parent instance ---------------------------------------------------


async def test_handover_assignments_with_totals(fed_client, world):
    response = await _get(fed_client, "/v1/doorgifte/opdrachten", PARENT_PEER_ID)
    assert response.status_code == 200, response.text
    (entry,) = terms.from_contract(response.json())["results"]
    assert entry["assignment"]["uri"] == ASSIGNMENT_URI
    assert entry["budgeted"]["amount_cents"] == 12 * 1440000
    # January at the established 60 percent, the other months as planned,
    # plus 30 percent of the hosting forecast.
    assert entry["used"]["amount_cents"] == 1080000 + 11 * 1440000 + 450000


async def test_handover_staffing_is_head_counts_by_default(fed_client, world):
    response = await _get(
        fed_client, "/v1/doorgifte/bemensing", PARENT_PEER_ID, maand="2026-03"
    )
    assert response.status_code == 200, response.text
    (row,) = terms.from_contract(response.json())["results"]
    assert row["headcount"] == 1 and row["role"] == "Productmanager"
    assert row["fte_pct"] == "80" and "person" not in row
    assert "Medewerker" not in response.text


async def test_handover_staffing_with_names_when_the_instance_allows_it(
    fed_client, world, monkeypatch
):
    monkeypatch.setenv("HANDOVER_STAFFING_WITH_NAMES", "1")
    get_bridge_settings.cache_clear()
    response = await _get(
        fed_client, "/v1/doorgifte/bemensing", PARENT_PEER_ID, maand="2026-03"
    )
    assert response.status_code == 200, response.text
    (row,) = terms.from_contract(response.json())["results"]
    assert row["person"] == {
        "name": "Medewerker Voorbeeld",
        "email": "medewerker@example.org",
    }
    assert "headcount" not in row


async def test_handover_capacity_costs_and_billing(fed_client, world):
    capacity = terms.from_contract(
        (await _get(fed_client, "/v1/doorgifte/capaciteit", PARENT_PEER_ID)).json()
    )
    assert capacity["open_roles"] == 0 and capacity["sought_fte"] == "0"

    costs_response = await _get(
        fed_client, "/v1/doorgifte/kosten", PARENT_PEER_ID, jaar=2026
    )
    assert costs_response.status_code == 200, costs_response.text
    (item,) = terms.from_contract(costs_response.json())["results"]
    assert item["forecast"]["amount_cents"] == 1500000
    assert item["covered"]["amount_cents"] == 450000
    assert item["coverage"][0]["assignment_uri"] == ASSIGNMENT_URI

    billing = await _get(
        fed_client, "/v1/doorgifte/factuurgegevens", PARENT_PEER_ID, maand="2026-01"
    )
    (month,) = terms.from_contract(billing.json())["results"]
    assert month["total"]["amount_cents"] == 1080000


async def test_handover_is_for_the_parent_only(fed_client, world):
    for path, params in (
        ("/v1/doorgifte/opdrachten", {}),
        ("/v1/doorgifte/bemensing", {"maand": "2026-03"}),
        ("/v1/doorgifte/kosten", {"jaar": 2026}),
    ):
        response = await _get(fed_client, path, CLIENT_PEER_ID, **params)
        assert response.status_code == 403, path


# --- the corpus ------------------------------------------------------------


async def test_corpus_sees_phase_and_spending_at_its_node(fed_client, world):
    response = await _get(
        fed_client, "/v1/opdrachten", CORPUS_PEER_ID, nodeUri=NODE_URI
    )
    assert response.status_code == 200, response.text
    page = terms.from_contract(response.json())
    (entry,) = page["results"]
    assert page["total"] == 1 and entry["status"] == "draft"
    assert entry["spending"]["budgeted"]["amount_cents"] == 12 * 1440000
    assert set(entry["spending"]) == {"budgeted", "used", "as_of"}
    assert "Medewerker" not in response.text

    other_node = await _get(
        fed_client,
        "/v1/opdrachten",
        CORPUS_PEER_ID,
        nodeUri=f"{CORPUS_BASE}/id/node/7c1d2f3a-1111-4222-8333-444455556666",
    )
    assert terms.from_contract(other_node.json())["results"] == []


async def test_corpus_spending_rule_needs_the_reference(db_session, world, make_peer):
    await make_peer(
        "00000000000000000070",
        base_uri="https://corpus.anderministerie.example",
        role=PEER_ROLE_CORPUS,
    )
    relations = SqlRelationSource(
        db_session, instance_base_uri=get_settings().INSTANCE_BASE_URI
    )
    assignment_id = world["assignment"].id
    referenced = PeerAccess(LocalDecider(relations), relations, CORPUS_PEER_ID)
    stranger = PeerAccess(LocalDecider(relations), relations, "00000000000000000070")
    client = PeerAccess(LocalDecider(relations), relations, CLIENT_PEER_ID)
    assert (await referenced.spending_totals(assignment_id)).reason == CORPUS_SPENDING
    assert (await stranger.spending_totals(assignment_id)).reason == NO_CORPUS_RELATION
    # A client gets totals only through class B, which is never a default.
    assert not (await client.spending_totals(assignment_id)).allowed


# --- refusals of pushed messages -------------------------------------------


async def test_acceptance_for_a_quote_of_someone_else_is_404(
    fed_client, db_session, world, make_peer
):
    from .conftest import example

    quote = await quotes.issue_quote(db_session, world["assignment"].id, actor=None)
    await make_peer("00000000000000000060", base_uri="https://grip.ander.example")
    rejection = example("rejection")
    rejection[t("quote_id")] = str(quote.id)
    path = f"/v1/offertes/{quote.id}/afwijzingen"
    stranger = await fed_client.post(
        path, json=rejection, headers=as_peer("00000000000000000060")
    )
    assert stranger.status_code == 404
    # The client itself, but with a hash that is not the quote's.
    wrong_hash = await fed_client.post(
        path, json=rejection, headers=as_peer(CLIENT_PEER_ID)
    )
    assert wrong_hash.status_code == 409
