"""The Functiegebouw Rijk in this instance: reading, correcting, reloading.

The public site of the Functiegebouw Rijk has no open machine endpoint: its
API is given out on request. Until this instance has that access, the list
comes from a reference file in the repository that was read from the public
overview page once, with the address and the date in its header. The
beheerder corrects or adds entries; a reload of the file upserts on the
identifier of the source and leaves rows a beheerder changed alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip.core.audit import CREATE, UPDATE, record_audit
from grip.models.assignment import BudgetLine
from grip.models.function_framework import (
    MAX_SCALE,
    MIN_SCALE,
    SOURCE_MANUAL,
    SOURCE_REFERENCE,
    FunctionFamily,
    FunctionGroup,
)
from grip.models.person import Person
from grip.models.rates import RateCard, ScaleBand
from grip.services.errors import DomainError, DomainValidationError, NotFoundError

REFERENCE_FILE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "function_framework"
    / "functiegebouw-rijk.json"
)


class ScaleOutsideGroupError(DomainError):
    """The scale is not one of the group's, and no reason was given."""

    def __init__(self, scale: int, group_name: str, scales: list[int]) -> None:
        super().__init__(
            f"Schaal {scale} hoort niet bij de functiegroep {group_name} "
            f"({describe_scales(scales)}). Kies een schaal van de groep, of geef "
            "aan dat de schaal afwijkt en waarom."
        )


@dataclass(frozen=True)
class ReferenceInfo:
    name: str
    source_url: str
    read_on: date
    families: int
    groups: int


@dataclass(frozen=True)
class ReloadResult:
    families_created: int
    families_updated: int
    groups_created: int
    groups_updated: int
    # Rows a beheerder changed by hand, which the reload left as they are.
    groups_kept: int


def describe_scales(scales: list[int]) -> str:
    """ "schaal 12" or "schaal 11 t/m 13", or a list when there are gaps."""
    ordered = sorted(scales)
    if len(ordered) == 1:
        return f"schaal {ordered[0]}"
    if ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"schaal {ordered[0]} t/m {ordered[-1]}"
    return "schaal " + ", ".join(str(scale) for scale in ordered)


def read_reference(path: Path | None = None) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (path or REFERENCE_FILE).read_text(encoding="utf-8")
    )
    return data


def reference_info(data: dict[str, Any] | None = None) -> ReferenceInfo:
    data = data or read_reference()
    return ReferenceInfo(
        name=data["name"],
        source_url=data["source_url"],
        read_on=date.fromisoformat(data["read_on"]),
        families=len(data["families"]),
        groups=sum(len(family["groups"]) for family in data["families"]),
    )


def _clean_scales(scales: Any) -> list[int]:
    if not isinstance(scales, list | tuple) or not scales:
        raise DomainValidationError("Een functiegroep heeft minstens een schaal.")
    cleaned: set[int] = set()
    for scale in scales:
        if isinstance(scale, bool) or not isinstance(scale, int):
            raise DomainValidationError("Een schaal is een heel getal.")
        if not MIN_SCALE <= scale <= MAX_SCALE:
            raise DomainValidationError(
                f"Een schaal ligt tussen {MIN_SCALE} en {MAX_SCALE}."
            )
        cleaned.add(scale)
    return sorted(cleaned)


def _clean_name(name: str | None, what: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise DomainValidationError(f"Een {what} heeft een naam nodig.")
    return cleaned


def _check_validity(valid_from: date | None, valid_to: date | None) -> None:
    if valid_from and valid_to and valid_to < valid_from:
        raise DomainValidationError("De einddatum ligt voor de begindatum.")


async def list_families(
    db: AsyncSession, *, include_ended: bool = False, today: date | None = None
) -> list[FunctionFamily]:
    """Families with their groups, in the order of the source.

    Without ``include_ended`` only what is valid today: what a vacancy can
    choose from.
    """
    result = await db.execute(
        select(FunctionFamily)
        .options(selectinload(FunctionFamily.groups))
        .order_by(FunctionFamily.position, FunctionFamily.name)
        .execution_options(populate_existing=True)
    )
    families = list(result.scalars())
    if include_ended:
        return families
    day = today or date.today()
    return [
        family
        for family in families
        if family.valid_to is None or family.valid_to >= day
    ]


async def get_group(db: AsyncSession, group_id: UUID) -> FunctionGroup:
    result = await db.execute(
        select(FunctionGroup)
        .where(FunctionGroup.id == group_id)
        .options(selectinload(FunctionGroup.family))
        .execution_options(populate_existing=True)
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise NotFoundError("Functiegroep", group_id)
    return group


async def get_family(db: AsyncSession, family_id: UUID) -> FunctionFamily:
    family = await db.get(FunctionFamily, family_id)
    if family is None:
        raise NotFoundError("Functiefamilie", family_id)
    return family


def _key_from(name: str) -> str:
    key = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")
    while "--" in key:
        key = key.replace("--", "-")
    return key[:100] or "familie"


async def create_family(
    db: AsyncSession, *, actor: Person | None, name: str
) -> FunctionFamily:
    name = _clean_name(name, "functiefamilie")
    key = _key_from(name)
    existing = await db.execute(select(FunctionFamily).where(FunctionFamily.key == key))
    if existing.scalar_one_or_none() is not None:
        raise DomainValidationError("Er is al een functiefamilie met deze naam.")
    position = len(await list_families(db, include_ended=True)) + 1
    family = FunctionFamily(key=key, name=name, position=position, source=SOURCE_MANUAL)
    db.add(family)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="function_family",
        entity_id=family.id,
        new_value={"name": name},
    )
    return family


async def update_family(
    db: AsyncSession,
    family_id: UUID,
    *,
    actor: Person | None,
    changes: dict[str, Any],
) -> FunctionFamily:
    family = await get_family(db, family_id)
    unknown = set(changes) - {"name", "valid_to"}
    if unknown:
        raise DomainValidationError(
            "Van een functiefamilie zijn alleen de naam en de einddatum te wijzigen."
        )
    old = {name: getattr(family, name) for name in changes}
    if "name" in changes:
        family.name = _clean_name(changes["name"], "functiefamilie")
    if "valid_to" in changes:
        _check_validity(family.valid_from, changes["valid_to"])
        family.valid_to = changes["valid_to"]
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="function_family",
        entity_id=family.id,
        old_value={name: _plain(value) for name, value in old.items()},
        new_value={name: _plain(getattr(family, name)) for name in changes},
    )
    return family


async def create_group(
    db: AsyncSession,
    *,
    actor: Person | None,
    family_id: UUID,
    name: str,
    scales: list[int],
) -> FunctionGroup:
    family = await get_family(db, family_id)
    result = await db.execute(
        select(FunctionGroup).where(FunctionGroup.family_id == family.id)
    )
    position = len(list(result.scalars())) + 1
    group = FunctionGroup(
        family_id=family.id,
        name=_clean_name(name, "functiegroep"),
        scales=_clean_scales(scales),
        position=position,
        source=SOURCE_MANUAL,
        edited_at=datetime.now(UTC),
        edited_by_id=actor.id if actor else None,
    )
    db.add(group)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="function_group",
        entity_id=group.id,
        new_value={"name": group.name, "scales": group.scales},
    )
    return await get_group(db, group.id)


async def update_group(
    db: AsyncSession,
    group_id: UUID,
    *,
    actor: Person | None,
    changes: dict[str, Any],
) -> FunctionGroup:
    """Correct a group. A vacancy that already printed the old name keeps it."""
    group = await get_group(db, group_id)
    unknown = set(changes) - {"name", "scales", "family_id", "valid_to"}
    if unknown:
        raise DomainValidationError(
            "Van een functiegroep zijn de naam, de schalen, de familie en de "
            "einddatum te wijzigen."
        )
    old = {name: getattr(group, name) for name in changes}
    if "name" in changes:
        group.name = _clean_name(changes["name"], "functiegroep")
    if "scales" in changes:
        group.scales = _clean_scales(changes["scales"])
    if "family_id" in changes:
        group.family_id = (await get_family(db, changes["family_id"])).id
    if "valid_to" in changes:
        _check_validity(group.valid_from, changes["valid_to"])
        group.valid_to = changes["valid_to"]
    group.edited_at = datetime.now(UTC)
    group.edited_by_id = actor.id if actor else None
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="function_group",
        entity_id=group.id,
        old_value={name: _plain(value) for name, value in old.items()},
        new_value={name: _plain(getattr(group, name)) for name in changes},
    )
    return await get_group(db, group.id)


def _plain(value: Any) -> Any:
    if isinstance(value, date | UUID):
        return str(value)
    return value


async def reload_reference(
    db: AsyncSession, *, actor: Person | None, data: dict[str, Any] | None = None
) -> ReloadResult:
    """Bring the tables in line with the reference file.

    Families are matched on their key, groups on the identifier of the
    source. Nothing is removed: a group that is no longer in the file stays,
    for the beheerder to end. A group a beheerder changed is left alone.
    """
    data = data or read_reference()
    families = {
        family.key: family for family in await list_families(db, include_ended=True)
    }
    result = await db.execute(
        select(FunctionGroup).where(FunctionGroup.source_id.is_not(None))
    )
    groups = {group.source_id: group for group in result.scalars()}

    counts = {"fc": 0, "fu": 0, "gc": 0, "gu": 0, "gk": 0}
    for family_position, entry in enumerate(data["families"], start=1):
        family = families.get(entry["key"])
        if family is None:
            family = FunctionFamily(
                key=entry["key"],
                name=entry["name"],
                position=family_position,
                source=SOURCE_REFERENCE,
                source_url=entry.get("source_url"),
            )
            db.add(family)
            await db.flush()
            families[family.key] = family
            counts["fc"] += 1
        elif family.source == SOURCE_REFERENCE and (
            family.name != entry["name"]
            or family.position != family_position
            or family.source_url != entry.get("source_url")
        ):
            family.name = entry["name"]
            family.position = family_position
            family.source_url = entry.get("source_url")
            counts["fu"] += 1

        for group_position, item in enumerate(entry["groups"], start=1):
            scales = _clean_scales(item["scales"])
            group = groups.get(item["source_id"])
            if group is None:
                db.add(
                    FunctionGroup(
                        family_id=family.id,
                        name=item["name"],
                        scales=scales,
                        position=group_position,
                        source=SOURCE_REFERENCE,
                        source_id=item["source_id"],
                        source_url=item.get("source_url"),
                    )
                )
                counts["gc"] += 1
                continue
            same = (
                group.name == item["name"]
                and list(group.scales) == scales
                and group.family_id == family.id
                and group.position == group_position
                and group.source_url == item.get("source_url")
            )
            if same:
                continue
            if group.edited_at is not None:
                counts["gk"] += 1
                continue
            group.name = item["name"]
            group.scales = scales
            group.family_id = family.id
            group.position = group_position
            group.source_url = item.get("source_url")
            counts["gu"] += 1
    await db.flush()
    outcome = ReloadResult(
        families_created=counts["fc"],
        families_updated=counts["fu"],
        groups_created=counts["gc"],
        groups_updated=counts["gu"],
        groups_kept=counts["gk"],
    )
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="function_framework",
        entity_id="functiegebouw-rijk",
        new_value={
            "reloaded_from": data.get("source_url"),
            "read_on": data.get("read_on"),
            "groups_created": outcome.groups_created,
            "groups_updated": outcome.groups_updated,
            "groups_kept": outcome.groups_kept,
        },
    )
    return outcome


# --- what a vacancy needs ----------------------------------------------------


def check_scale(
    group: FunctionGroup, scale: int | None, deviation_reason: str | None
) -> str | None:
    """Check a scale against the group; return the reason to store, if any.

    A scale of the group needs no reason (and none is kept). A scale outside
    it is refused unless a reason says why it deviates.
    """
    if scale is None or scale in group.scales:
        return None
    reason = (deviation_reason or "").strip()
    if not reason:
        raise ScaleOutsideGroupError(scale, group.name, list(group.scales))
    return reason


async def budget_line_scales(
    db: AsyncSession, budget_line_id: UUID | None
) -> list[int] | None:
    """The scales the rate category of a budget line stands for.

    Read from the scale mapping of the rate card valid when the line starts,
    or of the most recent card before it. ``None`` when the line has no
    category or no rate card says which scales it covers.
    """
    if budget_line_id is None:
        return None
    line = await db.get(BudgetLine, budget_line_id)
    if line is None or not line.rate_category:
        return None
    day = line.start_date or date.today()
    result = await db.execute(
        select(RateCard.valid_from, ScaleBand.scale)
        .join(RateCard, RateCard.id == ScaleBand.rate_card_id)
        .where(ScaleBand.category == line.rate_category)
        .order_by(RateCard.valid_from)
    )
    by_start: dict[date, list[int]] = {}
    for valid_from, scale in result.all():
        by_start.setdefault(valid_from, []).append(scale)
    if not by_start:
        return None
    earlier = [candidate for candidate in by_start if candidate <= day]
    chosen = max(earlier) if earlier else min(by_start)
    return sorted(by_start[chosen])
