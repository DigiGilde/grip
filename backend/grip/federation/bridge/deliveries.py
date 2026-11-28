"""What does not arrive at another instance, told to the domain (ADR 0061).

The outbox says per peer which messages do not arrive; the domain keeps that
for the beheerder's task. The reason is the same code on both sides.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.federation.registry import PeerDeliveries
from grip.services import delivery_trouble


async def report(
    db: AsyncSession, deliveries: list[PeerDeliveries], peer_ids: set[UUID] | None
) -> None:
    await delivery_trouble.report(
        db,
        [
            delivery_trouble.Trouble(
                peer_id=item.peer_id,
                peer_name=item.peer_name,
                since=item.since,
                message_count=item.count,
                final=item.final,
                reason=item.failure,
                retry_until=item.retry_until,
            )
            for item in deliveries
        ],
        peer_ids=peer_ids,
    )
