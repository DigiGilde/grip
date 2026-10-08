"""Federation: the only part of grip that knows about FSC.

Other instances and corpus systems are peers. Traffic to them goes through
the outbox and the own outway; traffic from them arrives through the inway
at the separate listener in :mod:`grip.federation.app`. The shapes that
cross the boundary come from the vendored contract under ``contract/``.

The domain plugs in through three registries (see :mod:`.registry`) and
queues messages with :func:`.outbox.enqueue`. It never imports transport
details, and this package never queries domain tables.
"""

from grip.federation.outbox import enqueue
from grip.federation.problems import FederationProblem
from grip.federation.registry import (
    InboundMessage,
    register_inbound_handler,
    register_message_builder,
    register_provider,
)

__all__ = [
    "FederationProblem",
    "InboundMessage",
    "enqueue",
    "register_inbound_handler",
    "register_message_builder",
    "register_provider",
]
