"""What the domain asks about the channel "to the client's own instance".

The domain decides that a quote is offered and through which channel; it
does not know how instances are connected. It asks two things through
:mod:`grip.services.quote_channels`, and this module answers them: can a
quote be sent to the instance at this base URI, and what became of a quote
that was sent.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import get_settings
from grip.federation.contract_loader import SERVICE_OPDRACHTVERKEER
from grip.federation.models import (
    OUTBOX_PENDING,
    OUTBOX_SENT,
    PEER_ROLE_COUNTERPART,
    FederationOutbox,
    Peer,
)
from grip.federation.peers import (
    find_peer_for_organisation,
    normalize_uri,
    usable_peers,
)
from grip.models.organisation import Organisation
from grip.services.quote_channels import NOT_CONNECTED

NO_OWN_IDENTITY = (
    "Deze instantie kan nog niets naar andere instanties sturen: de eigen "
    "TOOI-URI is niet ingesteld. Vraag de beheerder."
)
NO_GRANT = (
    "De opdrachtgever is niet gekoppeld: met de instantie van deze "
    f"organisatie is geen contract voor {SERVICE_OPDRACHTVERKEER} vastgelegd."
)


async def connection_check(db: AsyncSession, instance_uri: str) -> str | None:
    """None when a quote can go to that instance, otherwise why not.

    Connected means: an active peer whose base URI is that instance, with a
    grant for the service the quote travels over.
    """
    if not get_settings().INSTANCE_TOOI_URI:
        # A message names its sender by TOOI URI; without one nothing that
        # this instance sends is valid.
        return NO_OWN_IDENTITY
    peer = await find_peer_for_organisation(db, {"instance_uri": instance_uri})
    if peer is None:
        return NOT_CONNECTED
    if not (peer.grant_hashes or {}).get(SERVICE_OPDRACHTVERKEER):
        return NO_GRANT
    return None


async def delivery_state(db: AsyncSession, quote_id: UUID) -> str | None:
    """pending, sent or refused for a quote that was offered to an instance.

    The id of the message is the id of the quote, so offering the same quote
    to the same instance twice is one message.
    """
    row = (
        (
            await db.execute(
                select(FederationOutbox)
                .where(
                    FederationOutbox.message_id == quote_id,
                    FederationOutbox.operation == "sendQuote",
                )
                .order_by(FederationOutbox.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    if row.status == OUTBOX_PENDING:
        return "pending"
    if row.status == OUTBOX_SENT:
        return "sent"
    return "refused"


async def possible_executors(db: AsyncSession) -> set[UUID]:
    """The organisations a cost item can be asked of (ADR 0052).

    Those whose instance is an active counterparty with a grant for the
    service the request travels over.
    """
    if not get_settings().INSTANCE_TOOI_URI:
        return set()
    peers = (
        await db.execute(usable_peers().where(Peer.role == PEER_ROLE_COUNTERPART))
    ).scalars()
    bases = {
        normalize_uri(peer.base_uri)
        for peer in peers
        if (peer.grant_hashes or {}).get(SERVICE_OPDRACHTVERKEER)
    }
    if not bases:
        return set()
    rows = await db.execute(
        select(Organisation.id, Organisation.instance_uri).where(
            Organisation.instance_uri.is_not(None)
        )
    )
    return {
        organisation_id
        for organisation_id, instance_uri in rows
        if normalize_uri(instance_uri) in bases
    }
