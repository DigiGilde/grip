"""A person's own notifications: the preference and the devices.

Everything here is about the person who asks. Nobody else sees a person's
devices or preference; an endpoint is never returned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.integrations.push import outbox, scan
from grip.integrations.push.config import push_config
from grip.models.push import KIND_TEST
from grip.schema.notifications import (
    DeviceIn,
    DeviceOut,
    NotificationsOut,
    PreferenceIn,
    PreferenceOut,
)
from grip.services import notifications

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _preference_out(preference: notifications.Preference) -> PreferenceOut:
    return PreferenceOut(
        push=preference.push,
        mail_summary=preference.mail_summary,
        tasks=preference.tasks,
        overdue=preference.overdue,
        decisions=preference.decisions,
        quiet_from=preference.quiet_from,
        quiet_until=preference.quiet_until,
        weekends_quiet=preference.weekends_quiet,
    )


def _require_push(settings: Settings) -> None:
    if push_config(settings) is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Meldingen zijn in deze omgeving niet ingesteld",
        )


@router.get("", response_model=NotificationsOut)
async def read_own(
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> NotificationsOut:
    config = push_config(settings)
    return NotificationsOut(
        available=config is not None,
        public_key=config.public_key if config else None,
        daily_cap=settings.PUSH_DAILY_CAP,
        mail_summary_available=False,
        preference=_preference_out(await notifications.preference_of(db, person.id)),
        devices=[
            DeviceOut.model_validate(device)
            for device in await notifications.devices_of(db, person.id)
        ],
    )


@router.put("/preference", response_model=PreferenceOut)
async def set_own_preference(
    body: PreferenceIn,
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
) -> PreferenceOut:
    values = body.model_dump(exclude_unset=True, exclude={"quiet"})
    if body.quiet is False:
        values["quiet_from"] = None
        values["quiet_until"] = None
    # A value left out keeps what it was; an explicit null for a switch
    # would be no choice at all.
    values = {
        key: value
        for key, value in values.items()
        if value is not None or key in ("quiet_from", "quiet_until")
    }
    return _preference_out(await notifications.set_preference(db, person, values))


@router.post("/devices", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def add_own_device(
    body: DeviceIn,
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DeviceOut:
    """Register this browser. Called after the person allowed notifications."""
    _require_push(settings)
    device, first = await notifications.add_device(
        db,
        person,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        label=body.label,
        # A push service on this machine, for trying it out locally.
        allow_insecure=settings.DEV_NO_AUTH,
    )
    if first:
        # What already waits is on the screen now; notify from here on.
        await scan.seed(db, person.id, settings)
    return DeviceOut.model_validate(device)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_own_device(
    device_id: UUID,
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
) -> None:
    device = await notifications.own_device(db, device_id, person)
    await notifications.remove_device(
        db, device, actor=person, reason="ingetrokken door de persoon zelf"
    )


@router.post("/test", status_code=status.HTTP_202_ACCEPTED, response_model=None)
async def send_own_test(
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    """Queue a trial notification to the person's own devices."""
    _require_push(settings)
    if not await notifications.devices_of(db, person.id):
        raise HTTPException(status_code=422, detail="Je hebt nog geen apparaat.")
    await outbox.enqueue(
        db,
        person_id=person.id,
        kind=KIND_TEST,
        dedupe_key=f"test:{person.id}:{uuid4()}",
        path="/meldingen",
        now=datetime.now(UTC),
    )
    return {"queued": True}
