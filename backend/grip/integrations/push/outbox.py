"""Notices to send: queued by the scanner, sent by the worker.

The pattern of the mail outbox with its own table. What differs is what
stands between a queued notice and a device:

- the person's preference (push off, or this kind off: not sent);
- quiet hours (kept until they end, then sent as one);
- the day's cap (not sent beyond it);
- several notices of one kind waiting together become one.

A notice carries no sentence and no name: a kind, a number and a path. The
service worker chooses the words from its own fixed list.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from grip.core.config import Settings
from grip.integrations.push import webpush
from grip.integrations.push.config import PushConfig, push_config
from grip.models.push import (
    KIND_OVERDUE,
    KIND_TASKS,
    KIND_TEST,
    PUSH_FAILED,
    PUSH_QUEUED,
    PUSH_SENT,
    PUSH_SKIPPED,
    PushOutbox,
    PushSubscription,
)
from grip.services import notifications

logger = logging.getLogger(__name__)

PAYLOAD_VERSION = 1
MAX_ATTEMPTS = 6
_BACKOFF_BASE_SECONDS = 30
_BACKOFF_MAX_SECONDS = 1800
# A device that keeps failing is dropped after this many failures in a row.
MAX_DEVICE_FAILURES = 10

# Which switch of the preference a kind falls under.
GROUP_OF = {
    KIND_TASKS: notifications.GROUP_TASKS,
    KIND_OVERDUE: notifications.GROUP_OVERDUE,
}
# Kinds that count things: several waiting together are added up.
_COUNTED = {KIND_TASKS, KIND_OVERDUE}


def group_of(kind: str) -> str:
    return GROUP_OF.get(kind, notifications.GROUP_DECISIONS)


def payload_of(row: PushOutbox) -> dict[str, Any]:
    """What goes to the device. Nothing in it tells a stranger anything:
    a kind from a fixed list, a number, a path of ids, an opaque id."""
    payload: dict[str, Any] = {
        "v": PAYLOAD_VERSION,
        "k": row.kind,
        "n": row.count,
        "p": row.path,
        "i": str(row.id),
    }
    if row.badge is not None:
        payload["b"] = row.badge
    return payload


async def enqueue(
    db: AsyncSession,
    *,
    person_id: UUID,
    kind: str,
    dedupe_key: str,
    count: int = 1,
    badge: int | None = None,
    path: str = "/",
    now: datetime | None = None,
) -> PushOutbox | None:
    """Queue one notice. The same key queues nothing new."""
    existing = (
        await db.execute(
            select(PushOutbox.id).where(PushOutbox.dedupe_key == dedupe_key)
        )
    ).first()
    if existing is not None:
        return None
    row = PushOutbox(
        person_id=person_id,
        kind=kind,
        count=count,
        badge=badge,
        path=path,
        dedupe_key=dedupe_key[:200],
        status=PUSH_QUEUED,
        attempts=0,
        next_attempt_at=now or datetime.now(UTC),
    )
    db.add(row)
    await db.flush()
    return row


def _backoff(attempts: int) -> timedelta:
    return timedelta(
        seconds=min(
            _BACKOFF_BASE_SECONDS * 2 ** max(attempts - 1, 0), _BACKOFF_MAX_SECONDS
        )
    )


async def _sent_today(
    db: AsyncSession, person_id: UUID, config: PushConfig, moment: datetime
) -> int:
    local = moment.astimezone(config.timezone)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    result = await db.execute(
        select(func.count())
        .select_from(PushOutbox)
        .where(
            PushOutbox.person_id == person_id,
            PushOutbox.status == PUSH_SENT,
            PushOutbox.kind != KIND_TEST,
            PushOutbox.sent_at >= start,
        )
    )
    return int(result.scalar() or 0)


def _merge(rows: list[PushOutbox]) -> list[PushOutbox]:
    """Per kind the one notice to send; the others are marked as taken up.

    The newest stays, because its path and badge are the latest; for a kind
    that counts, the numbers are added up.
    """
    by_kind: dict[str, list[PushOutbox]] = defaultdict(list)
    for row in rows:
        by_kind[row.kind].append(row)
    keep: list[PushOutbox] = []
    for kind, group in by_kind.items():
        group.sort(key=lambda row: row.created_at)
        newest = group[-1]
        if len(group) > 1:
            if kind in _COUNTED:
                newest.count = sum(row.count for row in group)
                # More than one thing: the list, not one of them.
                newest.path = newest.path.split("?")[0]
            for older in group[:-1]:
                older.status = PUSH_SKIPPED
                older.last_error = "samengevoegd"
        keep.append(newest)
    return keep


async def send_due(
    db: AsyncSession,
    settings: Settings,
    client: Any,
    *,
    now: datetime | None = None,
    limit: int = 200,
) -> int:
    """Send what is due. Returns how many notices reached a device."""
    config = push_config(settings)
    if config is None:
        return 0
    moment = now or datetime.now(UTC)
    due = list(
        await db.scalars(
            select(PushOutbox)
            .where(
                PushOutbox.status == PUSH_QUEUED, PushOutbox.next_attempt_at <= moment
            )
            .order_by(PushOutbox.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    if not due:
        return 0
    by_person: dict[UUID, list[PushOutbox]] = defaultdict(list)
    for row in due:
        by_person[row.person_id].append(row)
    preferences = await notifications.preferences_of(db, set(by_person))
    delivered = 0
    for person_id, rows in by_person.items():
        preference = preferences[person_id]
        wanted: list[PushOutbox] = []
        for row in rows:
            if row.kind == KIND_TEST or preference.wants(group_of(row.kind)):
                wanted.append(row)
            else:
                row.status = PUSH_SKIPPED
                row.last_error = "staat uit"
        ordinary = [row for row in wanted if row.kind != KIND_TEST]
        resume = preference.resumes_at(moment, config.timezone) if ordinary else None
        if resume is not None:
            # Quiet now: keep them, and send them as one when it ends.
            for row in ordinary:
                row.next_attempt_at = resume
            wanted = [row for row in wanted if row.kind == KIND_TEST]
        devices = list(
            await db.scalars(
                select(PushSubscription).where(PushSubscription.person_id == person_id)
            )
        )
        sent_today = await _sent_today(db, person_id, config, moment)
        for row in _merge(wanted):
            if not devices:
                row.status = PUSH_SKIPPED
                row.last_error = "geen apparaat"
                continue
            if row.kind != KIND_TEST and sent_today >= config.daily_cap:
                row.status = PUSH_SKIPPED
                row.last_error = "dagmaximum"
                continue
            if await _send_row(db, config, client, row, devices, moment):
                delivered += 1
                if row.kind != KIND_TEST:
                    sent_today += 1
    await db.flush()
    return delivered


async def _send_row(
    db: AsyncSession,
    config: PushConfig,
    client: Any,
    row: PushOutbox,
    devices: list[PushSubscription],
    moment: datetime,
) -> bool:
    payload = payload_of(row)
    reached = False
    retry = False
    error: str | None = None
    for device in list(devices):
        target = webpush.Target(device.endpoint, device.p256dh, device.auth)
        try:
            # The topic lets the push service replace an older notice of
            # this kind that the device has not fetched yet.
            await webpush.send(client, config, target, payload, topic=row.kind)
        except webpush.PushError as exc:
            error = str(exc)
            if exc.gone:
                devices.remove(device)
                await notifications.remove_device(
                    db, device, actor=None, reason="het apparaat is afgemeld"
                )
                continue
            device.failure_count += 1
            if device.failure_count >= MAX_DEVICE_FAILURES:
                devices.remove(device)
                await notifications.remove_device(
                    db, device, actor=None, reason="het apparaat is onbereikbaar"
                )
                continue
            retry = retry or exc.retry
            continue
        reached = True
        device.last_success_at = moment
        device.failure_count = 0
    row.attempts += 1
    if reached:
        row.status = PUSH_SENT
        row.sent_at = moment
        row.last_error = None
        return True
    row.last_error = (error or "geen apparaat")[:300]
    if retry and row.attempts < MAX_ATTEMPTS:
        row.next_attempt_at = moment + _backoff(row.attempts)
    else:
        row.status = PUSH_FAILED if error else PUSH_SKIPPED
    return False


async def run_push_loop(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Look for something to notify about, and send what is due, forever."""
    import httpx

    from grip.integrations.push import scan

    interval = max(settings.PUSH_SCAN_INTERVAL_SECONDS, 5)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                async with session_factory() as db:
                    await scan.scan(db, settings)
                    await db.commit()
                async with session_factory() as db:
                    sent = await send_due(db, settings, client)
                    await db.commit()
                if sent:
                    logger.info("Meldingen verstuurd: %s", sent)
            except Exception:
                logger.exception("De meldingen konden niet worden verwerkt")
            await asyncio.sleep(interval)
