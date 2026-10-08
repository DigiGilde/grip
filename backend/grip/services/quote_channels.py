"""The channels through which an issued quote can be offered to a client.

Issuing a quote freezes it. Offering it is a separate act, and the channel
is chosen then, per offer:

- ``client_instance``: the quote goes to the client's own grip instance,
  where the client signs it;
- ``signing_link``: the client is invited to sign in this instance;
- ``document``: the quote goes out as a document and a signed copy comes
  back.

Whether the first channel is possible depends on a connection with the
client's instance. The domain does not know how instances are connected
(ADR 0015), so it asks through the two functions below. The part of grip
that does know registers them; while nobody has, that channel is not
available and says why.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.quote import (
    OFFER_CHANNELS,
    OFFER_CLIENT_INSTANCE,
    OFFER_DOCUMENT,
    OFFER_SIGNING_LINK,
)

# Reasons in the words of someone who offers a quote. They say what is the
# case for the client, not how grip is deployed.
NOT_CONNECTED = "Het grip van de opdrachtgever is niet gekoppeld aan dit grip."
NO_INSTANCE = "De opdrachtgever gebruikt grip nog niet."
NO_CLIENT = "Deze opdracht heeft geen opdrachtgever."
EXCHANGE_OFF = "Uitwisselen met andere organisaties staat uit."

# Returns None when quotes can be sent to the instance with this base URI,
# otherwise the reason in words a user can act on.
ConnectionCheck = Callable[[AsyncSession, str], Awaitable[str | None]]
# The state of delivery of a quote that was offered to a client's instance:
# pending, sent, refused, or None when nothing was queued.
DeliveryLookup = Callable[[AsyncSession, UUID], Awaitable[str | None]]

_connection_check: ConnectionCheck | None = None
_delivery_lookup: DeliveryLookup | None = None


def register_connection_check(check: ConnectionCheck | None) -> None:
    global _connection_check
    _connection_check = check


def register_delivery_lookup(lookup: DeliveryLookup | None) -> None:
    global _delivery_lookup
    _delivery_lookup = lookup


def clear() -> None:
    """Forget what was registered. For tests."""
    register_connection_check(None)
    register_delivery_lookup(None)


@dataclass(frozen=True)
class ChannelOption:
    channel: str
    available: bool
    # Why the channel cannot be used, when it cannot.
    reason: str | None = None
    # The channel that fits how this assignment came about.
    suggested: bool = False


async def client_instance_unavailable(
    db: AsyncSession, instance_uri: str | None, *, has_client: bool = True
) -> str | None:
    """Why a quote cannot go to the client's instance, or None when it can."""
    if not has_client:
        return NO_CLIENT
    if not instance_uri:
        return NO_INSTANCE
    if _connection_check is None:
        return EXCHANGE_OFF
    return await _connection_check(db, instance_uri)


async def delivery_state(db: AsyncSession, quote_id: UUID) -> str | None:
    if _delivery_lookup is None:
        return None
    return await _delivery_lookup(db, quote_id)


__all__ = [
    "EXCHANGE_OFF",
    "NOT_CONNECTED",
    "NO_CLIENT",
    "NO_INSTANCE",
    "OFFER_CHANNELS",
    "OFFER_CLIENT_INSTANCE",
    "OFFER_DOCUMENT",
    "OFFER_SIGNING_LINK",
    "ChannelOption",
    "client_instance_unavailable",
    "clear",
    "delivery_state",
    "register_connection_check",
    "register_delivery_lookup",
]
