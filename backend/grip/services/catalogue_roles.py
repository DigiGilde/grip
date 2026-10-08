"""The role catalogue: the fixed words a personnel budget line is staffed in.

A budget line refers to a role here. Where the link with Wies is configured
the catalogue follows the skills of Wies, so both systems use the same words;
without it the catalogue is kept by hand. A role someone needs while filling
in a budget can be added on the spot and is then marked for the beheerder.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.core.config import Settings
from grip.integrations.wies.client import (
    WiesNotConfiguredError,
    WiesSkill,
    WiesUnavailableError,
    fetch_skills,
)
from grip.models.assignment import BudgetLine, canonical_role_name
from grip.models.catalogue_role import (
    ROLE_SOURCE_MANUAL,
    ROLE_SOURCE_WIES,
    CatalogueRole,
    CatalogueRoleSyncRun,
)
from grip.models.person import Person
from grip.services.errors import DomainValidationError, NotFoundError

_ACCENTED = "áàâäãåéèêëíìîïóòôöõúùûüçñ"
_PLAIN = "aaaaaaeeeeiiiiooooouuuucn"


def _fold(value: str) -> str:
    return value.lower().translate(str.maketrans(_ACCENTED, _PLAIN))


def _like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class RoleRow:
    role: CatalogueRole
    # Budget lines that refer to the role.
    usage_count: int


# --- reading ------------------------------------------------------------------


async def get_role(db: AsyncSession, role_id: uuid.UUID) -> CatalogueRole:
    role = await db.get(CatalogueRole, role_id)
    if role is None:
        raise NotFoundError("Rol", role_id)
    return role


async def find_by_name(db: AsyncSession, name: str) -> CatalogueRole | None:
    """The role with this name, whatever the capitals or the spacing."""
    clean = canonical_role_name(name)
    if not clean:
        return None
    return (
        await db.execute(
            select(CatalogueRole).where(func.lower(CatalogueRole.name) == clean.lower())
        )
    ).scalar_one_or_none()


async def _usage(
    db: AsyncSession, role_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, int]:
    ids = list(role_ids)
    if not ids:
        return {}
    rows = await db.execute(
        select(BudgetLine.role_id, func.count())
        .where(BudgetLine.role_id.in_(ids))
        .group_by(BudgetLine.role_id)
    )
    return {role_id: count for role_id, count in rows.all()}


async def list_roles(
    db: AsyncSession,
    *,
    query: str = "",
    include_inactive: bool = False,
    limit: int = 200,
) -> list[RoleRow]:
    """Roles matching the query: a name that starts with it first, then the rest."""
    folded = _fold(" ".join(query.split()))
    name = func.translate(func.lower(CatalogueRole.name), _ACCENTED, _PLAIN)
    stmt = select(CatalogueRole)
    if not include_inactive:
        stmt = stmt.where(CatalogueRole.is_active.is_(True))
    for word in folded.split():
        stmt = stmt.where(name.like(f"%{_like(word)}%", escape="\\"))
    if folded:
        starts = name.like(f"{_like(folded)}%", escape="\\")
        stmt = stmt.order_by((name == folded).desc(), starts.desc(), name)
    else:
        stmt = stmt.order_by(name)
    roles = list(
        (await db.execute(stmt.limit(max(1, min(500, limit))))).scalars().all()
    )
    usage = await _usage(db, [r.id for r in roles])
    return [RoleRow(role=r, usage_count=usage.get(r.id, 0)) for r in roles]


async def with_usage(db: AsyncSession, role: CatalogueRole) -> RoleRow:
    return RoleRow(role=role, usage_count=(await _usage(db, [role.id])).get(role.id, 0))


# --- changing -----------------------------------------------------------------


async def create_role(
    db: AsyncSession,
    *,
    name: str,
    description: str | None = None,
    actor: Person | None,
    needs_review: bool = False,
) -> CatalogueRole:
    """Add a role by hand.

    Asking for a name that already exists returns the existing role, so two
    people who miss the same word do not make two roles. A role that was
    switched off is not handed out this way.
    """
    clean = canonical_role_name(name)
    if not clean:
        raise DomainValidationError("Geef de rol een naam.")
    existing = await find_by_name(db, clean)
    if existing is not None:
        if not existing.is_active:
            raise DomainValidationError(
                f"De rol '{existing.name}' bestaat al maar is uitgeschakeld. "
                "De beheerder kan haar weer inschakelen."
            )
        return existing
    role = CatalogueRole(
        id=uuid.uuid4(),
        name=clean,
        description=(description or "").strip() or None,
        source=ROLE_SOURCE_MANUAL,
        needs_review=needs_review,
        created_by_id=actor.id if actor else None,
    )
    db.add(role)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="catalogue_role",
        entity_id=role.id,
        new_value={
            "name": role.name,
            "source": role.source,
            "needs_review": needs_review,
        },
    )
    return role


async def update_role(
    db: AsyncSession,
    role_id: uuid.UUID,
    changes: dict[str, Any],
    *,
    actor: Person | None,
) -> CatalogueRole:
    """Rename, describe, switch on or off, or mark as reviewed.

    Renaming renames the role on every budget line that uses it; quotes that
    were issued keep the words they were issued with. A name another role
    already has is refused: those two are to be merged.
    """
    role = await get_role(db, role_id)
    allowed = {"name", "description", "is_active", "needs_review"}
    refused = sorted(set(changes) - allowed)
    if refused:
        raise DomainValidationError(f"Niet te wijzigen: {', '.join(refused)}.")
    old: dict[str, Any] = {}
    new: dict[str, Any] = {}
    for key, value in changes.items():
        if key == "name":
            value = canonical_role_name(str(value or ""))
            if not value:
                raise DomainValidationError("Geef de rol een naam.")
            twin = await find_by_name(db, value)
            if twin is not None and twin.id != role.id:
                raise DomainValidationError(
                    f"Er is al een rol '{twin.name}'. Voeg de twee samen als ze "
                    "hetzelfde betekenen."
                )
        elif key == "description":
            value = (value or "").strip() or None
        else:
            value = bool(value)
        if getattr(role, key) != value:
            old[key] = getattr(role, key)
            new[key] = value
            setattr(role, key, value)
    if new:
        await db.flush()
        if "name" in new:
            # The database renamed the lines (the foreign key cascades); make
            # lines this session already holds read the new name.
            for obj in list(db.sync_session.identity_map.values()):
                if isinstance(obj, BudgetLine) and obj.role_id == role.id:
                    await db.refresh(obj, ["role"])
        record_audit(
            db,
            actor=actor,
            action=UPDATE,
            entity="catalogue_role",
            entity_id=role.id,
            old_value=old,
            new_value=new,
        )
    return role


async def merge_roles(
    db: AsyncSession,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    *,
    actor: Person | None,
) -> tuple[CatalogueRole, int]:
    """Make two roles one: every line of the source becomes a line of the target.

    The source disappears. When only the source was linked to a skill in
    Wies, the target takes that link over, so the next sync does not bring
    the source back. Returns the target and the number of lines rewritten.
    """
    if source_id == target_id:
        raise DomainValidationError(
            "Kies twee verschillende rollen om samen te voegen."
        )
    source = await get_role(db, source_id)
    target = await get_role(db, target_id)
    if source.wies_public_id and target.wies_public_id:
        raise DomainValidationError(
            "Beide rollen komen uit Wies. Voeg ze daar samen; grip volgt bij de "
            "volgende keer ophalen."
        )
    source_name, source_wies = source.name, source.wies_public_id

    result = await db.execute(
        update(BudgetLine)
        .where(BudgetLine.role_id == source.id)
        .values(role_id=target.id, role=target.name)
        .execution_options(synchronize_session=False)
    )
    moved = result.rowcount or 0
    for obj in list(db.sync_session.identity_map.values()):
        if isinstance(obj, BudgetLine) and obj.role_id == source.id:
            await db.refresh(obj, ["role", "role_id"])
    await db.execute(delete(CatalogueRole).where(CatalogueRole.id == source.id))
    await db.flush()
    db.sync_session.expunge(source)
    if source_wies and not target.wies_public_id:
        target.wies_public_id = source_wies
        target.source = ROLE_SOURCE_WIES
    target.needs_review = False
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=DELETE,
        entity="catalogue_role",
        entity_id=source_id,
        old_value={"name": source_name, "wies_public_id": source_wies},
        new_value={
            "merged_into": str(target.id),
            "merged_into_name": target.name,
            "budget_lines_rewritten": moved,
        },
    )
    return target, moved


# --- following Wies -----------------------------------------------------------


@dataclass
class RoleSyncCounts:
    seen: int = 0
    created: int = 0
    # A manual role with the name of a skill: now linked to that skill.
    adopted: int = 0
    renamed: int = 0
    reactivated: int = 0
    unchanged: int = 0
    # Gone from Wies and still on a budget line: switched off, kept.
    deactivated: int = 0
    # Gone from Wies and used nowhere: removed.
    deleted: int = 0
    # A skill renamed to a name another role already has: left for a merge.
    conflicts: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


async def apply_wies_skills(
    db: AsyncSession, skills: Iterable[WiesSkill]
) -> RoleSyncCounts:
    """Bring the catalogue in line with the skills of Wies."""
    skills = list(skills)
    counts = RoleSyncCounts(seen=len(skills))
    if not skills:
        raise DomainValidationError(
            "Wies gaf geen enkele rol terug. Er is niets gewijzigd."
        )
    roles = list((await db.execute(select(CatalogueRole))).scalars().all())
    by_wies = {r.wies_public_id: r for r in roles if r.wies_public_id}
    by_name = {r.name.lower(): r for r in roles}
    seen_ids: set[uuid.UUID] = set()

    for skill in skills:
        name = canonical_role_name(skill.name)
        role = by_wies.get(skill.public_id)
        if role is None:
            twin = by_name.get(name.lower())
            if twin is not None and not twin.wies_public_id:
                twin.wies_public_id = skill.public_id
                twin.source = ROLE_SOURCE_WIES
                twin.needs_review = False
                twin.is_active = True
                if twin.name != name:
                    del by_name[twin.name.lower()]
                    twin.name = name
                    by_name[name.lower()] = twin
                counts.adopted += 1
                seen_ids.add(twin.id)
                continue
            if twin is not None:
                # Two skills in Wies with one name; the first keeps it.
                counts.conflicts += 1
                continue
            role = CatalogueRole(
                id=uuid.uuid4(),
                name=name,
                source=ROLE_SOURCE_WIES,
                wies_public_id=skill.public_id,
            )
            db.add(role)
            by_name[name.lower()] = role
            by_wies[skill.public_id] = role
            counts.created += 1
            seen_ids.add(role.id)
            continue

        seen_ids.add(role.id)
        changed = False
        if role.name != name:
            holder = by_name.get(name.lower())
            if holder is not None and holder.id != role.id:
                counts.conflicts += 1
            else:
                by_name.pop(role.name.lower(), None)
                role.name = name
                by_name[name.lower()] = role
                counts.renamed += 1
                changed = True
        if not role.is_active:
            role.is_active = True
            counts.reactivated += 1
            changed = True
        if role.source != ROLE_SOURCE_WIES:
            role.source = ROLE_SOURCE_WIES
            changed = True
        if not changed:
            counts.unchanged += 1
    await db.flush()

    gone = [r for r in roles if r.wies_public_id and r.id not in seen_ids]
    usage = await _usage(db, [r.id for r in gone])
    for role in gone:
        if usage.get(role.id, 0) > 0:
            if role.is_active:
                role.is_active = False
                counts.deactivated += 1
        else:
            await db.delete(role)
            counts.deleted += 1
    await db.flush()
    return counts


async def last_sync_run(db: AsyncSession) -> CatalogueRoleSyncRun | None:
    return (
        (
            await db.execute(
                select(CatalogueRoleSyncRun)
                .order_by(CatalogueRoleSyncRun.finished_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def run_wies_sync(
    db: AsyncSession,
    settings: Settings,
    *,
    actor: Person | None,
    skills: list[WiesSkill] | None = None,
) -> CatalogueRoleSyncRun:
    """Fetch the skills of Wies and bring the catalogue in line with them.

    The list is fetched in full before anything changes, and the changes are
    applied in one savepoint: a failure leaves the catalogue as it was. The
    run is recorded either way. ``skills`` is for tests.
    """
    result: dict[str, Any] = {}
    error: str | None = None
    try:
        if skills is None:
            skills = await fetch_skills(settings)
        async with db.begin_nested():
            result = (await apply_wies_skills(db, skills)).as_dict()
    except (WiesNotConfiguredError, WiesUnavailableError, DomainValidationError) as exc:
        error = str(exc)
    run = CatalogueRoleSyncRun(
        finished_at=datetime.now(UTC),
        status="failed" if error else "completed",
        result=result,
        error=error,
        started_by_id=actor.id if actor else None,
    )
    db.add(run)
    await db.flush()
    if not error:
        record_audit(
            db,
            actor=actor,
            action=UPDATE,
            entity="catalogue_role_sync",
            entity_id=run.id,
            new_value=result,
        )
    return run


async def review_count(db: AsyncSession) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(CatalogueRole)
            .where(
                CatalogueRole.needs_review.is_(True), CatalogueRole.is_active.is_(True)
            )
        )
    ).scalar_one()


__all__ = [
    "RoleRow",
    "RoleSyncCounts",
    "apply_wies_skills",
    "create_role",
    "find_by_name",
    "get_role",
    "last_sync_run",
    "list_roles",
    "merge_roles",
    "review_count",
    "run_wies_sync",
    "update_role",
    "with_usage",
]
