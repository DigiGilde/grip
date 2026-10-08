"""Corrections on billing periods that were delivered before, as stored rows.

What is still to deliver for a delivered month is what the month costs now
minus what was delivered for it (``grip.services.price_changes``). Knowing
that asks for pricing every month, which is too much to do each time someone
opens a list. So the service that changes a price brings the stored
corrections up to date in its own transaction (``sync``), and everything
that only needs to know reads the rows: the tasks, the course of a billing
period, the period rows and the page "Factureren".

One open row per billing period. Two changes before it is delivered add up
in it, each with its cause; a change that is undone takes it away again;
delivering the difference closes it.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.calc import Month
from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.models.assignment import Assignment
from grip.models.billing_correction import BillingCorrection
from grip.models.billing_delivery import BillingDelivery, BillingTerms
from grip.models.month_close import BillingExport
from grip.models.person import Person
from grip.services import billing_periods, events, instance_settings

ENTITY = "billing_correction"


async def _rhythm(session: AsyncSession, assignment_id: UUID) -> str:
    terms = await session.get(BillingTerms, assignment_id)
    if terms is not None:
        return terms.rhythm
    # Imported here: that module reads this one.
    from grip.services.billing_deliveries import DEFAULT_RHYTHM

    rhythm = await instance_settings.get(session, DEFAULT_RHYTHM.key)
    return rhythm if rhythm in billing_periods.RHYTHMS else billing_periods.MONTHLY


def period_key_of(month: Month, rhythm: str) -> str:
    return billing_periods.periods_of([month], rhythm)[0].key


async def open_corrections(
    session: AsyncSession, assignment_ids: Iterable[UUID]
) -> dict[UUID, list[BillingCorrection]]:
    """The corrections still to deliver, per assignment."""
    wanted = set(assignment_ids)
    if not wanted:
        return {}
    rows = await session.scalars(
        select(BillingCorrection)
        .where(
            BillingCorrection.assignment_id.in_(wanted),
            BillingCorrection.delivered_at.is_(None),
        )
        .order_by(BillingCorrection.period_key)
    )
    found: dict[UUID, list[BillingCorrection]] = {}
    for row in rows:
        found.setdefault(row.assignment_id, []).append(row)
    return found


async def all_corrections(
    session: AsyncSession, assignment_ids: Iterable[UUID]
) -> dict[UUID, list[BillingCorrection]]:
    """Every correction, delivered or not, per assignment and in order."""
    wanted = set(assignment_ids)
    if not wanted:
        return {}
    rows = await session.scalars(
        select(BillingCorrection)
        .where(BillingCorrection.assignment_id.in_(wanted))
        .order_by(BillingCorrection.period_key, BillingCorrection.arose_at)
    )
    found: dict[UUID, list[BillingCorrection]] = {}
    for row in rows:
        found.setdefault(row.assignment_id, []).append(row)
    return found


def month_cents(rows: Iterable[BillingCorrection]) -> dict[Month, int]:
    """What open corrections say is still to deliver, per month."""
    result: dict[Month, int] = {}
    for row in rows:
        for key, cents in (row.months or {}).items():
            year, number = key.split("-")
            month = Month(int(year), int(number))
            result[month] = result.get(month, 0) + int(cents)
    return result


def causes_text(row: BillingCorrection) -> str:
    """Why, in one sentence part: "inzetschaal gewijzigd ...; tarievenkaart ..."."""
    seen: list[str] = []
    for entry in row.causes or []:
        cause = str(entry.get("cause") or "").strip()
        if cause and cause not in seen:
            seen.append(cause)
    return "; ".join(seen)


async def _differences(session: AsyncSession, assignment_id: UUID) -> dict[Month, int]:
    """Per delivered month what the month costs now minus what was delivered."""
    # Imported here: that module prices, and pricing is read widely.
    from grip.services import outgoing_invoices

    found: dict[Month, int] = {}
    for month in await outgoing_invoices.month_billing(session, assignment_id):
        if not month.closed or month.export_id is None:
            continue
        if month.deliverable_cents is None or month.delivered_cents is None:
            continue
        difference = month.deliverable_cents - month.delivered_cents
        if difference:
            found[Month.of(month.month)] = difference
    return found


async def _latest_delivery(
    session: AsyncSession, assignment_id: UUID, period_key: str
) -> UUID | None:
    return (
        await session.execute(
            select(BillingDelivery.id)
            .where(
                BillingDelivery.assignment_id == assignment_id,
                BillingDelivery.period_key == period_key,
            )
            .order_by(BillingDelivery.delivered_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def sync(
    session: AsyncSession,
    *,
    cause: str,
    actor: Person | None = None,
    assignment_ids: Iterable[UUID] | None = None,
    now: datetime | None = None,
) -> list[BillingCorrection]:
    """Bring the stored corrections in line with what the months cost now.

    Called in the transaction of whatever may have changed the price of a
    delivered month. Returns the rows that arose or changed. Without
    ``assignment_ids``: every assignment that ever delivered something.
    """
    now = now or datetime.now(UTC)
    if assignment_ids is None:
        rows = await session.execute(select(BillingExport.assignment_id).distinct())
        wanted = set(rows.scalars())
    else:
        wanted = set(assignment_ids)
    existing = await open_corrections(session, wanted)
    touched: list[BillingCorrection] = []
    for assignment_id in sorted(wanted, key=str):
        rhythm = await _rhythm(session, assignment_id)
        per_period: dict[str, dict[str, int]] = {}
        for month, cents in (await _differences(session, assignment_id)).items():
            per_period.setdefault(period_key_of(month, rhythm), {})[str(month)] = cents
        current = {row.period_key: row for row in existing.get(assignment_id, [])}
        assignment = await session.get(Assignment, assignment_id)
        for period_key in sorted(set(per_period) | set(current)):
            months = per_period.get(period_key)
            row = current.get(period_key)
            if not months:
                # The change was undone before anyone delivered the difference.
                assert row is not None
                await _withdraw(session, row, actor=actor, cause=cause)
                continue
            amount = sum(months.values())
            entry = {
                "cause": cause,
                "at": now.isoformat(),
                "by_name": actor.name if actor is not None else None,
            }
            if row is None:
                row = BillingCorrection(
                    assignment_id=assignment_id,
                    period_key=period_key,
                    amount_cents=amount,
                    months=months,
                    causes=[entry],
                    follows_delivery_id=await _latest_delivery(
                        session, assignment_id, period_key
                    ),
                    arose_at=now,
                    arose_by_id=actor.id if actor is not None else None,
                )
                session.add(row)
                await session.flush()
                record_audit(
                    session,
                    actor=actor,
                    action=CREATE,
                    entity=ENTITY,
                    entity_id=row.id,
                    assignment_id=assignment_id,
                    new_value=_audit(row),
                )
            elif dict(row.months or {}) != months:
                old = _audit(row)
                row.amount_cents = amount
                row.months = months
                row.causes = [*(row.causes or []), entry]
                await session.flush()
                record_audit(
                    session,
                    actor=actor,
                    action=UPDATE,
                    entity=ENTITY,
                    entity_id=row.id,
                    assignment_id=assignment_id,
                    old_value=old,
                    new_value=_audit(row),
                )
            else:
                continue
            touched.append(row)
            await events.emit(
                session,
                events.BILLING_CORRECTION_AROSE,
                {
                    "correction_id": str(row.id),
                    "assignment_id": str(assignment_id),
                    "assignment_uri": assignment.uri if assignment else None,
                    "assignment_name": assignment.name if assignment else None,
                    "period_key": period_key,
                    # The first month of the difference, for readers of the
                    # event from before corrections were kept per period.
                    "month": sorted(months)[0],
                    "difference_cents": amount,
                    "cause": cause,
                },
            )
    return touched


def _audit(row: BillingCorrection) -> dict[str, Any]:
    return {
        "period_key": row.period_key,
        "amount_cents": row.amount_cents,
        "months": dict(row.months or {}),
        "causes": [str(entry.get("cause") or "") for entry in row.causes or []],
    }


async def _withdraw(
    session: AsyncSession, row: BillingCorrection, *, actor: Person | None, cause: str
) -> None:
    record_audit(
        session,
        actor=actor,
        action=DELETE,
        entity=ENTITY,
        entity_id=row.id,
        assignment_id=row.assignment_id,
        old_value=_audit(row),
        note=cause,
    )
    await session.delete(row)
    await session.flush()


async def mark_delivered(
    session: AsyncSession,
    assignment_id: UUID,
    months: Iterable[Month],
    delivery: BillingDelivery,
    *,
    actor: Person | None,
) -> list[BillingCorrection]:
    """The differences on these months went along with ``delivery``."""
    wanted = {str(month) for month in months}
    closed: list[BillingCorrection] = []
    for row in (await open_corrections(session, [assignment_id])).get(
        assignment_id, []
    ):
        if not wanted & set(row.months or {}):
            continue
        row.delivered_delivery_id = delivery.id
        row.delivered_at = delivery.delivered_at
        closed.append(row)
        record_audit(
            session,
            actor=actor,
            action=UPDATE,
            entity=ENTITY,
            entity_id=row.id,
            assignment_id=assignment_id,
            old_value={"delivered": False},
            new_value={"delivered": True, "delivery_id": str(delivery.id)},
        )
    await session.flush()
    return closed


async def _run() -> int:
    """Store the corrections that stand open on every assignment. Run once
    after the migration that introduced the stored row, so differences from
    before it are not lost from sight."""
    from grip.core.database import async_session, close_db

    try:
        async with async_session() as db:
            touched = await sync(
                db, cause="verschil van voor de vastlegging van naverrekeningen"
            )
            await db.commit()
        print(f"{len(touched)} naverrekening(en) vastgelegd.")
    finally:
        await close_db()
    return 0


if __name__ == "__main__":
    import asyncio
    import sys

    sys.exit(asyncio.run(_run()))
