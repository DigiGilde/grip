"""A message from another organisation does not change a closed dossier (ADR 0057)."""

from __future__ import annotations

from sqlalchemy import func, select

from grip.core import clock
from grip.federation.bridge.organisations import from_reference, own_organisation
from grip.models.stream_event import StreamEvent
from grip.services import assignments, dossiers, quotes

from .conftest import (
    CLIENT_BASE,
    CLIENT_PEER_ID,
    CONTRACTOR_BASE,
    CONTRACTOR_PEER_ID,
    as_peer,
    example,
    t,
)
from .test_bridge import (  # noqa: F401
    ASSIGNMENT_URI,
    ASSIGNMENT_UUID,
    CLIENT,
    _bridge,
    world,
)


async def test_a_rejection_for_a_closed_dossier_is_refused(
    fed_client,
    db_session,
    world,  # noqa: F811
):
    client = await from_reference(db_session, CLIENT)
    other = await assignments.create_assignment(
        db_session,
        name="Opdracht Beta",
        actor=None,
        client_organisation_id=client.id,
        contractor_organisation_id=(await own_organisation(db_session)).id,
    )
    await assignments.share_with_instance(db_session, other, CLIENT_BASE)
    await assignments.add_budget_line(
        db_session,
        other.id,
        description="Hosting",
        kind="fixed",
        amount_cents=150000,
        year=2026,
        actor=None,
    )
    quote = await quotes.issue_quote(db_session, other.id, actor=None)
    await assignments.transition(db_session, other.id, "cancelled", actor=None)
    await dossiers.close_dossier(
        db_session, other.id, actor=None, closed_on=clock.today()
    )

    rejection = example("rejection")
    rejection[t("quote_id")] = str(quote.id)
    rejection[t("quote_hash")] = quote.snapshot_hash
    response = await _post(fed_client, quote.id, rejection)
    assert response.status_code == 400
    assert "Het dossier is gesloten. Wijzigen kan weer" in response.text
    await db_session.refresh(quote)
    assert quote.status == "issued"


async def test_a_final_report_for_a_closed_dossier_is_refused(
    fed_client, db_session, make_peer
):
    await make_peer()
    contractor = await from_reference(
        db_session,
        {
            "tooi_uri": "https://identifier.overheid.nl/tooi/id/ministerie/mnre0001",
            "name": "Voorbeelddienst",
            "instance_uri": CONTRACTOR_BASE,
        },
    )
    ours = await assignments.create_assignment(
        db_session,
        name="Opdracht Gamma",
        actor=None,
        client_organisation_id=(await own_organisation(db_session)).id,
        contractor_organisation_id=contractor.id,
        uri=ASSIGNMENT_URI,
    )
    await assignments.share_with_instance(db_session, ours, CONTRACTOR_BASE)
    await assignments.transition(db_session, ours.id, "cancelled", actor=None)
    await dossiers.close_dossier(
        db_session, ours.id, actor=None, closed_on=clock.today()
    )

    response = await fed_client.put(
        f"/v1/opdrachten/{ASSIGNMENT_UUID}/eindrapport",
        json=example("final-report"),
        headers=as_peer(CONTRACTOR_PEER_ID),
    )
    assert response.status_code == 400
    assert "Het dossier is gesloten. Wijzigen kan weer" in response.text
    received = await db_session.scalar(
        select(func.count())
        .select_from(StreamEvent)
        .where(StreamEvent.subject_kind == "final_report_received")
    )
    assert received == 0


async def _post(fed_client, quote_id, body):
    return await fed_client.post(
        f"/v1/offertes/{quote_id}/afwijzingen",
        json=body,
        headers=as_peer(CLIENT_PEER_ID),
    )
