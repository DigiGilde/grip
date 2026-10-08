"""The seams between the federation module and the domain.

The federation module never touches domain tables. The domain registers:

- an inbound handler per pushed operation, which turns a received message
  into domain state;
- a provider per pull operation, which produces the answer for a peer.

- a message builder per domain event, which turns the event into the
  contract-shaped message for another instance.

Without a handler a message is stored and stays unprocessed. Without a
provider a pull operation answers 501. Without a builder an event leads to
no message.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.federation.contract_loader import ContractError, operations
from grip.federation.models import Peer


@dataclass(frozen=True)
class InboundMessage:
    """A validated message from a peer, as stored in the inbox."""

    message_id: UUID
    operation: str
    payload: dict[str, Any]
    path_parameters: dict[str, str]
    received_at: datetime


# Runs inside the request transaction, after validation and before the
# receipt is sent. Returns an optional result that is stored with the
# message. Raises FederationProblem (404, 409, 403) to refuse the message;
# nothing is stored then.
InboundHandler = Callable[
    [AsyncSession, Peer, InboundMessage], Awaitable[dict[str, Any] | None]
]

# Returns the response body for a pull operation, in the shape of the
# contract. Returns None for "not found or no relation" (404). Raises
# FederationProblem to refuse, for example 403 when inspection on request
# has not been granted. ``parameters`` holds path and query parameters by
# their contract names.
Provider = Callable[
    [AsyncSession, Peer, dict[str, Any]], Awaitable[dict[str, Any] | None]
]

# Turns the payload of a domain event into what has to be sent: a dict with
# ``message`` (the body in the shape of the contract) and optionally
# ``recipient`` (an organisation reference, when the receiver does not
# follow from the message) or ``recipients`` (a list, for a vacancy).
# Returns None when nothing has to be sent, for example for an internal
# assignment or a counterpart without grip. Builders read the domain through
# its service layer; the federation module itself does not.
MessageBuilder = Callable[
    [AsyncSession, dict[str, Any]], Awaitable[dict[str, Any] | None]
]

_inbound_handlers: dict[str, InboundHandler] = {}
_providers: dict[str, Provider] = {}
_message_builders: dict[str, MessageBuilder] = {}


def _check_operation(operation: str, *, pushed: bool) -> None:
    known = operations()
    if operation not in known:
        raise ContractError(f"The contract has no operation {operation!r}")
    if pushed != (known[operation].request_schema is not None):
        kind = "pushed" if pushed else "pull"
        raise ContractError(f"{operation!r} is not a {kind} operation")


def register_inbound_handler(operation: str, handler: InboundHandler) -> None:
    """Register the domain handler for a pushed operation (by operationId)."""
    _check_operation(operation, pushed=True)
    _inbound_handlers[operation] = handler


def get_inbound_handler(operation: str) -> InboundHandler | None:
    return _inbound_handlers.get(operation)


def register_provider(operation: str, provider: Provider) -> None:
    """Register the domain provider for a pull operation (by operationId)."""
    _check_operation(operation, pushed=False)
    _providers[operation] = provider


def get_provider(operation: str) -> Provider | None:
    return _providers.get(operation)


def register_message_builder(event_type: str, builder: MessageBuilder) -> None:
    """Register the builder that turns a domain event into a contract message."""
    _message_builders[event_type] = builder


def get_message_builder(event_type: str) -> MessageBuilder | None:
    return _message_builders.get(event_type)


def clear_registries() -> None:
    """Forget every handler, provider and builder. For tests."""
    _inbound_handlers.clear()
    _providers.clear()
    _message_builders.clear()
