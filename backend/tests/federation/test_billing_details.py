"""The client gives new billing details: sendBillingDetails at the contractor.

A change is taken over only when it was given later than what the billing
terms hold from the client. An older one is received and kept, and changes
nothing. All names and addresses are fictional.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from grip.core import clock
from grip.core.config import get_settings
from grip.federation.bridge import register_bridge
from grip.federation.bridge.organisations import from_reference, own_organisation
from grip.federation.models import FederationInbox
from grip.models.billing_delivery import BillingTerms
from grip.services import assignments, billing_deliveries

from .conftest import CLIENT_BASE, CLIENT_PEER_ID, as_peer, example, t

ASSIGNMENT_UUID = "3f2a8c54-6d1b-4f0e-9a77-1c2b3d4e5f60"
ASSIGNMENT_URI = f"{CLIENT_BASE}/id/opdracht/{ASSIGNMENT_UUID}"
PATH = f"/v1/opdrachten/{ASSIGNMENT_UUID}/factuurinformatie"
CLIENT = {
    "tooi_uri": "https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
    "name": "Voorbeeldministerie",
    "instance_uri": CLIENT_BASE,
}
STRANGER_PEER_ID = "00000000000000000060"


@pytest.fixture(autouse=True)
def _bridge(monkeypatch):
    monkeypatch.setattr(
        get_settings(),
        "INSTANCE_TOOI_URI",
        "https://identifier.overheid.nl/tooi/id/oorg/oorg00000",
    )
    register_bridge()


@pytest.fixture(autouse=True)
def _now():
    """After the moments in the examples, which a change may not lie beyond."""
    with clock.at(datetime(2027, 3, 1, tzinfo=UTC)):
        yield


@pytest.fixture
async def assignment(db_session, make_peer):
    """This instance as contractor of an assignment the client's grip shares."""
    client = await from_reference(db_session, CLIENT)
    own = await own_organisation(db_session)
    row = await assignments.create_assignment(
        db_session,
        name="Opdracht Alfa",
        actor=None,
        client_organisation_id=client.id,
        contractor_organisation_id=own.id,
        uri=ASSIGNMENT_URI,
    )
    assignments.share_with_instance(row, CLIENT_BASE)
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    await make_peer(STRANGER_PEER_ID, base_uri="https://grip.ander.example")
    await db_session.flush()
    return row


def _change(given_at: str, **details) -> dict:
    body = example("billing-details-change")
    body["id"] = str(uuid.uuid4())
    body[t("given_at")] = given_at
    body[t("billing_details")] = {**body[t("billing_details")], **details}
    return body


async def _terms(db_session, assignment) -> BillingTerms:
    await db_session.flush()
    row = await db_session.get(BillingTerms, assignment.id)
    assert row is not None
    await db_session.refresh(row)
    return row


async def test_a_change_goes_into_the_billing_terms(fed_client, db_session, assignment):
    # What the manager typed in before is replaced: the client's word wins.
    await billing_deliveries.set_terms(
        db_session,
        assignment.id,
        actor=None,
        details={"organisation": "Overgetypt", "contact_name": "Iemand"},
    )
    body = example("billing-details-change")
    response = await fed_client.put(PATH, json=body, headers=as_peer(CLIENT_PEER_ID))
    assert response.status_code == 201, response.text

    terms = await _terms(db_session, assignment)
    assert terms.details == {
        "organisation": "Voorbeeldministerie",
        "attention_of": "Financieel Dienstencentrum Voorbeeld",
        "address": "Postbus 00001",
        "postcode_city": "0000 AB Den Haag",
        "reference": "VPL-2027-0007",
    }
    assert terms.details_given_at == datetime.fromisoformat(body[t("given_at")])
    inbox = (await db_session.execute(select(FederationInbox))).scalar_one()
    assert inbox.result == {"assignment_id": str(assignment.id), "applied": True}

    # The same message again is a duplicate and changes nothing.
    again = await fed_client.put(PATH, json=body, headers=as_peer(CLIENT_PEER_ID))
    assert again.status_code == 200, again.text
    assert again.json()[t("outcome")] == "duplicaat"


async def test_an_older_change_is_received_and_not_taken_over(
    fed_client, db_session, assignment
):
    newer = _change("2027-01-04T09:15:00+01:00", adres="Postbus 00002")
    older = _change("2027-01-03T09:15:00+01:00", adres="Postbus 00003")
    same = _change("2027-01-04T09:15:00+01:00", adres="Postbus 00004")
    latest = _change("2027-02-01T08:00:00Z", adres="Postbus 00005")

    for body, applied in ((newer, True), (older, False), (same, False)):
        response = await fed_client.put(
            PATH, json=body, headers=as_peer(CLIENT_PEER_ID)
        )
        assert response.status_code == 201, response.text
        row = await db_session.scalar(
            select(FederationInbox).where(
                FederationInbox.message_id == uuid.UUID(body["id"])
            )
        )
        assert row.result["applied"] is applied
    terms = await _terms(db_session, assignment)
    assert terms.details["address"] == "Postbus 00002"

    response = await fed_client.put(PATH, json=latest, headers=as_peer(CLIENT_PEER_ID))
    assert response.status_code == 201, response.text
    terms = await _terms(db_session, assignment)
    assert terms.details["address"] == "Postbus 00005"
    assert terms.details_given_at == datetime(2027, 2, 1, 8, 0, tzinfo=UTC)


async def test_a_change_after_the_acceptance_needs_a_later_moment(
    fed_client, db_session, assignment
):
    """The details of the acceptance have the moment of signing."""
    from grip.services import billing_details

    signed_at = datetime(2027, 1, 10, 12, 0, tzinfo=UTC)
    await billing_details.take(
        db_session,
        assignment.id,
        {
            "organisation": "Voorbeeldministerie",
            "address": "Postbus 00009",
            "postcode_city": "0000 AA Den Haag",
        },
        given_at=signed_at,
        actor=None,
    )
    before = _change("2027-01-04T09:15:00+01:00")
    response = await fed_client.put(PATH, json=before, headers=as_peer(CLIENT_PEER_ID))
    assert response.status_code == 201, response.text
    assert (await _terms(db_session, assignment)).details["address"] == "Postbus 00009"


async def test_a_moment_in_the_future_does_not_block_a_later_change(
    fed_client, db_session, assignment
):
    ahead = _change("2099-01-01T00:00:00Z", adres="Postbus 00006")
    response = await fed_client.put(PATH, json=ahead, headers=as_peer(CLIENT_PEER_ID))
    assert response.status_code == 201, response.text
    terms = await _terms(db_session, assignment)
    assert terms.details_given_at == datetime(2027, 3, 1, tzinfo=UTC)

    with clock.at(datetime(2027, 4, 1, tzinfo=UTC)):
        later = _change("2027-03-15T09:00:00Z", adres="Postbus 00007")
        response = await fed_client.put(
            PATH, json=later, headers=as_peer(CLIENT_PEER_ID)
        )
        assert response.status_code == 201, response.text
    assert (await _terms(db_session, assignment)).details["address"] == "Postbus 00007"


async def test_unknown_assignment_is_404_and_another_caller_403(
    fed_client, db_session, assignment
):
    body = example("billing-details-change")
    unknown = await fed_client.put(
        f"/v1/opdrachten/{uuid.uuid4()}/factuurinformatie",
        json=body,
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert unknown.status_code == 404, unknown.text
    stranger = await fed_client.put(PATH, json=body, headers=as_peer(STRANGER_PEER_ID))
    assert stranger.status_code == 403, stranger.text
    assert await db_session.get(BillingTerms, assignment.id) is None
    assert (await db_session.execute(select(FederationInbox))).scalars().all() == []


async def test_a_change_without_an_address_is_refused_by_the_contract(
    fed_client, db_session, assignment
):
    body = example("billing-details-change.zonder-moment", "invalid")
    response = await fed_client.put(PATH, json=body, headers=as_peer(CLIENT_PEER_ID))
    assert response.status_code == 400, response.text
    incomplete = example("billing-details-change")
    del incomplete[t("billing_details")][t("address")]
    response = await fed_client.put(
        PATH, json=incomplete, headers=as_peer(CLIENT_PEER_ID)
    )
    assert response.status_code == 400, response.text
    assert await db_session.get(BillingTerms, assignment.id) is None
