"""Where the federation module meets the domain.

The rest of ``grip.federation`` is transport: peers, the outbox and the
inbox, signing, the routes of the contract. It knows nothing of assignments
or quotes. The domain service layer knows nothing of other instances. This
package connects the two, and is the only place that imports both:

- :mod:`.inbound`: what a received message does in the domain;
- :mod:`.builders`: the message another instance gets for a domain event;
- :mod:`.providers`: what this instance answers when another one asks;
- :mod:`.acceptance`: signing a received quote in the client's own instance.

Everything here works in code names. The translation to the Dutch terms of
the contract happens at the boundary, in :mod:`grip.federation.terms`.
"""

from __future__ import annotations

from grip.federation.registry import (
    register_inbound_handler,
    register_message_builder,
    register_provider,
)


def register_bridge() -> None:
    """Register every handler, builder and provider. Safe to call twice."""
    from grip.federation.bridge.builders import BUILDERS
    from grip.federation.bridge.inbound import HANDLERS
    from grip.federation.bridge.providers import PROVIDERS

    for operation, handler in HANDLERS.items():
        register_inbound_handler(operation, handler)
    for operation, provider in PROVIDERS.items():
        register_provider(operation, provider)
    for event_type, builder in BUILDERS.items():
        register_message_builder(event_type, builder)
