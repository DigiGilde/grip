"""Messages to other instances: queue them, send them, retry them.

The domain never sends anything itself. It queues a message in the same
transaction as its own change; the worker sends it through the outway. That
keeps the application working when the other side cannot be reached.

A message that does not arrive is tried again for ``FEDERATION_RETRY_DAYS``
from its first failure, with a pause that doubles up to four hours, unless
the receiver refuses it for good (ADR 0061).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from grip.core import clock
from grip.core.config import Settings
from grip.federation import signing, terms, undelivered
from grip.federation.contract_loader import operation, validation_errors
from grip.federation.models import (
    FAILURE_CONFIGURATION,
    FAILURE_CONFLICT,
    FAILURE_GONE,
    FAILURE_INVALID,
    FAILURE_NO_CONNECTION,
    FAILURE_NOT_FOUND,
    FAILURE_OTHER,
    FAILURE_RECEIVER_ERROR,
    FAILURE_TIMEOUT,
    FAILURE_UNKNOWN_SENDER,
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
from grip.federation.registry import get_delivery_hook, outbox_sources

logger = logging.getLogger(__name__)

_BACKOFF_BASE_SECONDS = 30
_BACKOFF_MAX_SECONDS = 4 * 3600
_MAX_ERROR_LENGTH = 2000
# A message counts as not arriving from this many failures in a row: one or
# two are a blip that the next attempt usually solves.
NOTICE_AFTER_FAILURES = 3

# Answers that will not change by trying again: the message itself is wrong
# or conflicts with what the receiver has. Any other answer can change: a
# receiver that does not know this instance yet (401, 403) or does not have
# what the message is about yet (404) may accept it at the next attempt.
_FINAL_STATUS_CODES = {
    400: FAILURE_INVALID,
    409: FAILURE_CONFLICT,
    410: FAILURE_GONE,
    422: FAILURE_INVALID,
}


def _failure_of_answer(status_code: int) -> str:
    if status_code in (401, 403):
        return FAILURE_UNKNOWN_SENDER
    if status_code == 404:
        return FAILURE_NOT_FOUND
    if 500 <= status_code <= 599:
        return FAILURE_RECEIVER_ERROR
    return FAILURE_OTHER


def _failure_of_error(error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.TimeoutException):
        return FAILURE_TIMEOUT
    if isinstance(error, httpx.TransportError):
        return FAILURE_NO_CONNECTION
    return FAILURE_OTHER


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

    ``payload`` and the path parameters are in code names; they are
    translated to contract terms here. The payload is validated against the
    contract before it enters the outbox. Queueing the same message twice
    returns the existing row.
    """
    op = operation(operation_id)
    if op.request_schema is None:
        raise ValueError(f"{operation_id} is not a pushed operation")
    # The message is built in code names and crosses the boundary in
    # contract terms; what is stored is exactly what will be sent.
    payload = terms.to_contract(payload)
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
        path=op.url_path(
            **{
                terms.contract_parameter(name): value
                for name, value in path_parameters.items()
            }
        ),
        payload=payload,
        status=OUTBOX_PENDING,
        attempts=0,
        next_attempt_at=clock.now(),
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
    row: FederationOutbox,
    failure: str,
    error: str,
    settings: Settings,
    stats: SendStats,
) -> None:
    now = clock.now()
    row.failure = failure
    row.last_error = error[:_MAX_ERROR_LENGTH]
    if row.retry_until is None:
        row.retry_until = now + timedelta(days=settings.FEDERATION_RETRY_DAYS)
    if row.failing_since is None and row.attempts >= NOTICE_AFTER_FAILURES:
        row.failing_since = now
    if now >= row.retry_until:
        row.status = OUTBOX_DEAD
        row.failing_since = row.failing_since or now
        stats.dead += 1
        logger.error(
            "Outbox message %s (%s) gave up after %d attempts: %s",
            row.message_id,
            row.operation,
            row.attempts,
            row.last_error,
        )
        return
    # The last attempt falls on the end of the window, not after it.
    row.next_attempt_at = min(
        now + timedelta(seconds=backoff_seconds(row.attempts)), row.retry_until
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
        _fail(row, FAILURE_CONFIGURATION, f"configuration: {exc}", settings, stats)
        return
    except httpx.HTTPError as exc:
        _fail(
            row, _failure_of_error(exc), f"{type(exc).__name__}: {exc}", settings, stats
        )
        return

    row.last_status_code = response.status_code
    if response.status_code in (200, 201):
        row.status = OUTBOX_SENT
        row.sent_at = clock.now()
        row.last_error = None
        row.failure = None
        row.failing_since = None
        row.retry_until = None
        stats.sent += 1
        return
    detail = response.text[:500]
    final = _FINAL_STATUS_CODES.get(response.status_code)
    if final is not None:
        row.status = OUTBOX_REJECTED
        row.failure = final
        row.last_error = f"HTTP {response.status_code}: {detail}"[:_MAX_ERROR_LENGTH]
        row.failing_since = row.failing_since or clock.now()
        stats.rejected += 1
        logger.warning(
            "Outbox message %s (%s) was refused by peer %s: %s",
            row.message_id,
            row.operation,
            row.peer.peer_id,
            row.last_error,
        )
        return
    _fail(
        row,
        _failure_of_answer(response.status_code),
        f"HTTP {response.status_code}: {detail}",
        settings,
        stats,
    )


async def send_due(
    db: AsyncSession, outway: OutwayClient, settings: Settings, *, limit: int = 20
) -> SendStats:
    """Send the messages that are due. The caller commits.

    Rows are locked with SKIP LOCKED, so two workers never send the same
    message at the same moment. A receiver handles a repeat anyway: the
    message id makes every push idempotent.

    First the registered sources queue what waits outside of an event;
    after each message that was sent, refused or given up, its delivery
    hook hears of it. Last, the domain hears per peer what does not arrive.

    An example instance sends nothing in the first minutes of its reset
    hour (:func:`grip.core.example.in_reset_window`).
    """
    # Imported here: grip.core.example reaches the models, which import this.
    from grip.core.example import in_reset_window

    if in_reset_window(settings):
        return SendStats()
    for source in outbox_sources():
        await source(db)
    rows = (
        (
            await db.execute(
                select(FederationOutbox)
                .where(
                    FederationOutbox.status == OUTBOX_PENDING,
                    FederationOutbox.next_attempt_at <= clock.now(),
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
        hook = get_delivery_hook(row.operation)
        if hook is not None and row.status != OUTBOX_PENDING:
            await hook(db, row)
    await db.flush()
    await undelivered.report_safely(db)
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
