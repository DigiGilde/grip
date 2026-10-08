"""Settings of an instance that the organisation itself changes.

A setting is known here by its key, its default and how a value is checked.
A key without a row in the database has its default. Reading goes through
``get``; changing through ``set_values``, which checks the value and writes
an audit row. Another part of grip that needs a setting declares it with
``declare`` and reads it the same way.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import UPDATE, record_audit
from grip.models.instance_setting import InstanceSetting
from grip.models.person import Person
from grip.services.errors import DomainValidationError

Check = Callable[[Any], Any]


@dataclass(frozen=True)
class Setting:
    key: str
    default: Any
    # Returns the value to store, or raises DomainValidationError.
    check: Check
    # What the setting does, for the beheerder.
    label: str


_declared: dict[str, Setting] = {}


def declare(key: str, default: Any, check: Check, label: str) -> Setting:
    """Make a setting known. Declaring the same key again replaces it."""
    setting = Setting(key, default, check, label)
    _declared[key] = setting
    return setting


def declared() -> dict[str, Setting]:
    return dict(_declared)


def one_of(*choices: str) -> Check:
    def check(value: Any) -> str:
        if value not in choices:
            raise DomainValidationError(
                f"Kies een van: {', '.join(choices)}. Gekregen: {value!r}."
            )
        return str(value)

    return check


def boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise DomainValidationError("Deze instelling is aan of uit.")
    return value


def whole_cents(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DomainValidationError(
            "Een bedrag is een geheel aantal centen van nul of meer."
        )
    return value


async def get(db: AsyncSession, key: str) -> Any:
    """The value of a setting, or its default when it was never set."""
    setting = _declared[key]
    row = await db.get(InstanceSetting, key)
    return setting.default if row is None else row.value


async def get_all(db: AsyncSession) -> dict[str, Any]:
    rows = {
        row.key: row.value
        for row in (await db.execute(select(InstanceSetting))).scalars()
    }
    return {
        key: rows.get(key, setting.default)
        for key, setting in sorted(_declared.items())
    }


async def set_values(
    db: AsyncSession, values: dict[str, Any], *, actor: Person | None
) -> dict[str, Any]:
    """Change settings. An unknown key or a wrong value changes nothing."""
    unknown = sorted(set(values) - set(_declared))
    if unknown:
        raise DomainValidationError(f"Onbekende instelling: {', '.join(unknown)}")
    checked = {key: _declared[key].check(value) for key, value in values.items()}
    old: dict[str, Any] = {}
    new: dict[str, Any] = {}
    for key, value in checked.items():
        row = await db.get(InstanceSetting, key)
        before = _declared[key].default if row is None else row.value
        if before == value:
            continue
        if row is None:
            db.add(
                InstanceSetting(
                    key=key,
                    value=value,
                    updated_by_id=actor.id if actor is not None else None,
                )
            )
        else:
            row.value = value
            row.updated_by_id = actor.id if actor is not None else None
        old[key], new[key] = before, value
    await db.flush()
    if new:
        record_audit(
            db,
            actor=actor,
            action=UPDATE,
            entity="instance_setting",
            entity_id="instance",
            old_value=old,
            new_value=new,
        )
    return await get_all(db)
