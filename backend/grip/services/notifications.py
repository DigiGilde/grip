"""How a person is told that something waits for them, and on which devices.

One preference per person covers both ways of telling (a notification on a
device, a summary by mail), so they never double up. Devices are the
browsers that agreed to be notified; a person manages only their own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.models.person import Person
from grip.models.push import NotificationPreference, PushSubscription
from grip.services.errors import DomainValidationError, NotFoundError

MAX_DEVICES_PER_PERSON = 10

# The kinds a person can switch, each covering one or more kinds of push.
GROUP_TASKS = "tasks"
GROUP_OVERDUE = "overdue"
GROUP_DECISIONS = "decisions"
GROUPS = (GROUP_TASKS, GROUP_OVERDUE, GROUP_DECISIONS)

DEFAULT_QUIET_FROM = time(19, 0)
DEFAULT_QUIET_UNTIL = time(7, 30)


@dataclass(frozen=True)
class Preference:
    push: bool = True
    mail_summary: bool = False
    tasks: bool = True
    overdue: bool = True
    decisions: bool = True
    quiet_from: time | None = DEFAULT_QUIET_FROM
    quiet_until: time | None = DEFAULT_QUIET_UNTIL
    weekends_quiet: bool = True

    def wants(self, group: str) -> bool:
        return self.push and bool(getattr(self, group, False))

    def resumes_at(self, moment: datetime, zone: ZoneInfo) -> datetime | None:
        """When sending may go on, or None when it is not quiet now."""
        local = moment.astimezone(zone)
        for _ in range(8):
            wait = self._quiet_end(local)
            if wait is None:
                break
            local = wait
        return None if local == moment.astimezone(zone) else local.astimezone(UTC)

    def _quiet_end(self, local: datetime) -> datetime | None:
        if self.weekends_quiet and local.weekday() >= 5:
            monday = (local + timedelta(days=7 - local.weekday())).date()
            return datetime.combine(monday, time(0, 0), local.tzinfo)
        start, end = self.quiet_from, self.quiet_until
        if start is None or end is None or start == end:
            return None
        now = local.time()
        if start < end:
            if start <= now < end:
                return datetime.combine(local.date(), end, local.tzinfo)
            return None
        # Over midnight: quiet from the evening until the morning.
        if now >= start:
            return datetime.combine(local.date() + timedelta(days=1), end, local.tzinfo)
        if now < end:
            return datetime.combine(local.date(), end, local.tzinfo)
        return None


def _from_row(row: NotificationPreference | None) -> Preference:
    if row is None:
        return Preference()
    kinds = row.kinds or {}
    return Preference(
        push=row.push,
        mail_summary=row.mail_summary,
        tasks=bool(kinds.get(GROUP_TASKS, True)),
        overdue=bool(kinds.get(GROUP_OVERDUE, True)),
        decisions=bool(kinds.get(GROUP_DECISIONS, True)),
        quiet_from=row.quiet_from,
        quiet_until=row.quiet_until,
        weekends_quiet=row.weekends_quiet,
    )


async def preference_of(db: AsyncSession, person_id: UUID) -> Preference:
    return _from_row(await db.get(NotificationPreference, person_id))


async def preferences_of(
    db: AsyncSession, person_ids: set[UUID]
) -> dict[UUID, Preference]:
    if not person_ids:
        return {}
    rows = await db.scalars(
        select(NotificationPreference).where(
            NotificationPreference.person_id.in_(person_ids)
        )
    )
    found = {row.person_id: _from_row(row) for row in rows}
    return {person_id: found.get(person_id, Preference()) for person_id in person_ids}


async def set_preference(
    db: AsyncSession, person: Person, values: dict[str, Any]
) -> Preference:
    """Change the person's own preference. Only the given keys change."""
    current = await preference_of(db, person.id)
    merged = {
        "push": current.push,
        "mail_summary": current.mail_summary,
        GROUP_TASKS: current.tasks,
        GROUP_OVERDUE: current.overdue,
        GROUP_DECISIONS: current.decisions,
        "quiet_from": current.quiet_from,
        "quiet_until": current.quiet_until,
        "weekends_quiet": current.weekends_quiet,
        **values,
    }
    if (merged["quiet_from"] is None) != (merged["quiet_until"] is None):
        raise DomainValidationError(
            "Geef een begin en een einde van de stille uren, of geen van beide."
        )
    row = await db.get(NotificationPreference, person.id)
    if row is None:
        row = NotificationPreference(person_id=person.id)
        db.add(row)
    row.push = bool(merged["push"])
    row.mail_summary = bool(merged["mail_summary"])
    row.kinds = {group: bool(merged[group]) for group in GROUPS}
    row.quiet_from = merged["quiet_from"]
    row.quiet_until = merged["quiet_until"]
    row.weekends_quiet = bool(merged["weekends_quiet"])
    await db.flush()
    record_audit(
        db,
        actor=person,
        action=UPDATE,
        entity="notification_preference",
        entity_id=person.id,
        person_id=person.id,
        new_value={
            "push": row.push,
            "mail_summary": row.mail_summary,
            **row.kinds,
            "quiet": row.quiet_from is not None,
            "weekends_quiet": row.weekends_quiet,
        },
    )
    return _from_row(row)


# -- devices -------------------------------------------------------------------


def _check_endpoint(endpoint: str) -> str:
    parts = urlsplit(endpoint.strip())
    if parts.scheme != "https" or not parts.netloc:
        raise DomainValidationError("Het adres van het apparaat is niet geldig.")
    return endpoint.strip()


async def devices_of(db: AsyncSession, person_id: UUID) -> list[PushSubscription]:
    rows = await db.scalars(
        select(PushSubscription)
        .where(PushSubscription.person_id == person_id)
        .order_by(PushSubscription.created_at.desc())
    )
    return list(rows)


async def add_device(
    db: AsyncSession,
    person: Person,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    label: str,
    allow_insecure: bool = False,
) -> tuple[PushSubscription, bool]:
    """Register this browser for the person. Returns the device and whether
    it is the person's first.

    The same browser subscribing again (its keys changed, or another person
    now uses it) replaces what was there: an endpoint reaches one browser,
    and it must notify whoever is logged in on it now.
    """
    address = endpoint.strip() if allow_insecure else _check_endpoint(endpoint)
    existing = (
        await db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == address)
        )
    ).scalar_one_or_none()
    owned = await devices_of(db, person.id)
    if existing is None and len(owned) >= MAX_DEVICES_PER_PERSON:
        raise DomainValidationError(
            f"Je hebt al {MAX_DEVICES_PER_PERSON} apparaten. Trek er eerst een in."
        )
    name = (label.strip() or "Apparaat")[:100]
    if existing is not None:
        existing.p256dh = p256dh
        existing.auth = auth
        # The same browser registering again without a name keeps its name.
        if label.strip() or existing.person_id != person.id:
            existing.label = name
        existing.person_id = person.id
        existing.failure_count = 0
        device = existing
    else:
        device = PushSubscription(
            person_id=person.id, endpoint=address, p256dh=p256dh, auth=auth, label=name
        )
        db.add(device)
    await db.flush()
    record_audit(
        db,
        actor=person,
        action=CREATE if existing is None else UPDATE,
        entity="push_subscription",
        entity_id=device.id,
        person_id=person.id,
        # The endpoint is personal data and stays out of the stream; the
        # host says which push service carries the messages.
        new_value={"label": device.label, "push_service": urlsplit(address).netloc},
    )
    return device, not owned


async def remove_device(
    db: AsyncSession, device: PushSubscription, *, actor: Person | None, reason: str
) -> None:
    record_audit(
        db,
        actor=actor,
        action=DELETE,
        entity="push_subscription",
        entity_id=device.id,
        person_id=device.person_id,
        old_value={"label": device.label},
        new_value={"reason": reason},
    )
    await db.delete(device)
    await db.flush()


async def own_device(
    db: AsyncSession, device_id: UUID, person: Person
) -> PushSubscription:
    device = await db.get(PushSubscription, device_id)
    if device is None or device.person_id != person.id:
        raise NotFoundError("Apparaat", device_id)
    return device
