"""Messages to other instances: queue them, send them, retry them.

The domain never sends anything itself. It queues a message in the same
transaction as its own change; the worker sends it through the outway. That
keeps the application working when the other side cannot be reached.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from grip.core.config import Settings
from grip.federation import signing
from grip.federation.contract_loader import operation, validation_errors
from grip.federation.models import (
    OUTBOX_DEAD,
    OUTBOX_PENDING,
    OUTBOX_REJECTED,
    OUTBOX_SENT,
    FederationOutbox,
    Peer,
)
from grip.federation.outway import (
    MissingGrantError,
    OutwayClient,
    OutwayNotConfiguredError,
)

logger = logging.getLogger(__name__)

_BACKOFF_BASE_SECONDS = 30
_BACKOFF_MAX_SECONDS = 3600
_MAX_ERROR_LENGTH = 2000

# Answers that will not change by trying again: the receiver understood the
# message and refused it.
_PERMANENT_STATUS_CODES = frozenset({400, 403, 404, 409, 410, 422})


class OutboundMessageInvalidError(Exception):
    """A message does not follow the contract and is not queued."""

    def __init__(self, operation_id: str, errors: list[str]) -> None:
        super().__init__(f"{operation_id}: " + "; ".join(errors))
        self.errors = errors


class OutboundMessageConflictError(Exception):
    """A message with this id but other content was queued for this peer before."""


async def enqueue(
    db: AsyncSession,
    peer: Peer,
    operation_id: str,
    payload: dict[str, Any],
    **path_parameters: str,
) -> FederationOutbox:
    """Queue a contract message for a peer.

    The payload is validated against the contract before it enters the
    outbox. Queueing the same message twice returns the existing row.
    """
    op = operation(operation_id)
    if op.request_schema is None:
        raise ValueError(f"{operation_id} is not a pushed operation")
    errors = validation_errors(op.request_schema, payload)
    if errors:
        raise OutboundMessageInvalidError(operation_id, errors)

    message_id = UUID(payload["id"])
    existing = (
        await db.execute(
            select(FederationOutbox).where(
                FederationOutbox.peer_id == peer.id,
                FederationOutbox.message_id == message_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        same = signing.payload_hash(existing.payload) == signing.payload_hash(payload)
        if same and existing.operation == operation_id:
            return existing
        raise OutboundMessageConflictError(
            f"Message {message_id} was queued before with other content"
        )

    row = FederationOutbox(
        message_id=message_id,
        peer_id=peer.id,
        service=op.service,
        operation=operation_id,
        method=op.method,
        path=op.url_path(**path_parameters),
        payload=payload,
        status=OUTBOX_PENDING,
        attempts=0,
        next_attempt_at=datetime.now(UTC),
    )
    db.add(row)
    await db.flush()
    return row


def backoff_seconds(attempts: int) -> int:
    """Wait before the next attempt, after ``attempts`` failed ones."""
    return min(_BACKOFF_BASE_SECONDS * 2 ** max(attempts - 1, 0), _BACKOFF_MAX_SECONDS)


@dataclass
class SendStats:
    sent: int = 0
    retried: int = 0
    rejected: int = 0
    dead: int = 0

    @property
    def total(self) -> int:
        return self.sent + self.retried + self.rejected + self.dead


def _fail(
    row: FederationOutbox, error: str, settings: Settings, stats: SendStats
) -> None:
    row.last_error = error[:_MAX_ERROR_LENGTH]
    if row.attempts >= settings.FEDERATION_MAX_ATTEMPTS:
        row.status = OUTBOX_DEAD
        stats.dead += 1
        logger.error(
            "Outbox message %s (%s) gave up after %d attempts: %s",
            row.message_id,
            row.operation,
            row.attempts,
            row.last_error,
        )
        return
    row.next_attempt_at = datetime.now(UTC) + timedelta(
        seconds=backoff_seconds(row.attempts)
    )
    stats.retried += 1


async def _send_one(
    row: FederationOutbox, outway: OutwayClient, settings: Settings, stats: SendStats
) -> None:
    row.attempts += 1
    try:
        response = await outway.request(
            row.peer, row.service, row.method, row.path, json=row.payload
        )
    except (OutwayNotConfiguredError, MissingGrantError) as exc:
        _fail(row, f"configuration: {exc}", settings, stats)
        return
    except httpx.HTTPError as exc:
        _fail(row, f"{type(exc).__name__}: {exc}", settings, stats)
        return

    row.last_status_code = response.status_code
    if response.status_code in (200, 201):
        row.status = OUTBOX_SENT
        row.sent_at = datetime.now(UTC)
        row.last_error = None
        stats.sent += 1
        return
    detail = response.text[:500]
    if response.status_code in _PERMANENT_STATUS_CODES:
        row.status = OUTBOX_REJECTED
        row.last_error = f"HTTP {response.status_code}: {detail}"[:_MAX_ERROR_LENGTH]
        stats.rejected += 1
        logger.warning(
            "Outbox message %s (%s) was refused by peer %s: %s",
            row.message_id,
            row.operation,
            row.peer.peer_id,
            row.last_error,
        )
        return
    _fail(row, f"HTTP {response.status_code}: {detail}", settings, stats)


async def send_due(
    db: AsyncSession, outway: OutwayClient, settings: Settings, *, limit: int = 20
) -> SendStats:
    """Send the messages that are due. The caller commits.

    Rows are locked with SKIP LOCKED, so two workers never send the same
    message at the same moment. A receiver handles a repeat anyway: the
    message id makes every push idempotent.
    """
    rows = (
        (
            await db.execute(
                select(FederationOutbox)
                .where(
                    FederationOutbox.status == OUTBOX_PENDING,
                    FederationOutbox.next_attempt_at <= datetime.now(UTC),
                )
                .order_by(FederationOutbox.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True, of=FederationOutbox)
            )
        )
        .scalars()
        .all()
    )
    stats = SendStats()
    for row in rows:
        await _send_one(row, outway, settings, stats)
    await db.flush()
    return stats


async def run_outbox_loop(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Send due messages forever. Started by the worker."""
    outway = OutwayClient(settings)
    try:
        while True:
            try:
                async with session_factory() as db:
                    stats = await send_due(db, outway, settings)
                    await db.commit()
                if stats.total:
                    logger.info("Outbox: %s", stats)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Outbox loop failed; trying again later")
            await asyncio.sleep(settings.FEDERATION_OUTBOX_INTERVAL_SECONDS)
    finally:
        await outway.aclose()
