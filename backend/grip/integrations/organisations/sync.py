"""Upserts the organisations of the public register into grip.

The rules follow the organisation sync of Wies (wies/core/services/
organizations.py, RijksICTGilde, EUPL v. 1.2), so both systems end up with
the same list:

- an organisation is matched on its TOOI identifier;
- the hierarchy comes from the nesting in the export;
- an organisation that already ended is not created, only updated when grip
  has it;
- an organisation that is no longer in the export gets today as end date;
- an ended organisation that nothing refers to is removed.

Different from Wies: a part without a TOOI identifier is matched on the
register's own id instead of on name, parent and type; the intelligence
services are left out at import rather than hidden afterwards; and the run is
refused when the export holds far fewer organisations than grip already has.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.database import Base
from grip.integrations.organisations.source import RegistryOrganisation
from grip.models.organisation import SOURCE_MANUAL, SOURCE_REGISTRY, Organisation

# With at least this many organisations in grip, an export holding fewer than
# half of them is taken for a broken export, not for a real change.
_SHRINK_GUARD_MINIMUM = 100


class SyncRefusedError(RuntimeError):
    """The export cannot be right; nothing was changed."""


@dataclass
class SyncCounts:
    seen: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    # Manual rows that turned out to be in the register and were taken over.
    adopted: int = 0
    # No longer in the export: given today as end date.
    closed: int = 0
    # Ended and referred to by nothing: removed.
    deleted: int = 0
    # Already ended in the export and unknown to grip: not created.
    skipped_ended: int = 0
    excluded: int = 0
    # The same identifier twice in one export; the second is not matched on it.
    duplicate_identifiers: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def _count(record: RegistryOrganisation) -> int:
    return 1 + sum(_count(child) for child in record.children)


_FIELDS = (
    "name",
    "label",
    "tooi_uri",
    "abbreviations",
    "organisation_types",
    "main_type",
    "related_ministry_tooi",
    "registry_id",
    "source_url",
    "end_date",
)


def _values(record: RegistryOrganisation) -> dict[str, object]:
    return {
        "name": record.name[:255],
        "label": record.label[:300],
        "tooi_uri": record.tooi_uri,
        "abbreviations": list(record.abbreviations),
        "organisation_types": list(record.organisation_types),
        "main_type": record.organisation_types[0][:100]
        if record.organisation_types
        else None,
        "related_ministry_tooi": record.related_ministry_tooi,
        "registry_id": record.registry_id or None,
        "source_url": record.source_url,
        "end_date": record.end_date,
    }


class _Sync:
    def __init__(
        self, db: AsyncSession, existing: list[Organisation], today: date
    ) -> None:
        self.db = db
        self.today = today
        self.counts = SyncCounts()
        self.seen: set[uuid.UUID] = set()
        # A unit below a registered organisation shares its TOOI URI and has a
        # unit key; only the row without a key is the organisation itself.
        self.by_tooi = {
            o.tooi_uri: o for o in existing if o.tooi_uri and o.unit_key is None
        }
        self.by_registry_id = {o.registry_id: o for o in existing if o.registry_id}
        self.used_tooi: set[str] = set()
        self.used_registry_id: set[str] = set()

    def _find(self, record: RegistryOrganisation) -> Organisation | None:
        tooi = record.tooi_uri
        if tooi and tooi in self.used_tooi:
            self.counts.duplicate_identifiers += 1
            record.tooi_uri = tooi = None
        registry_id = record.registry_id
        if registry_id and registry_id in self.used_registry_id:
            self.counts.duplicate_identifiers += 1
            record.registry_id = registry_id = ""
        found = None
        if tooi:
            found = self.by_tooi.get(tooi)
        if found is None and registry_id:
            found = self.by_registry_id.get(registry_id)
        if found is not None and found.id in self.seen:
            found = None
        if tooi:
            self.used_tooi.add(tooi)
        if registry_id:
            self.used_registry_id.add(registry_id)
        return found

    def visit(
        self,
        record: RegistryOrganisation,
        parent: Organisation | None,
        *,
        keep_parent: bool = False,
    ) -> None:
        if record.excluded:
            self.counts.excluded += _count(record)
            return
        if not record.name:
            return
        self.counts.seen += 1
        organisation = self._find(record)
        values = _values(record)
        ended = record.end_date is not None and record.end_date < self.today

        if organisation is None:
            if ended:
                self.counts.skipped_ended += 1
                # Its parts ended with it. They are not created either, but
                # one grip already has must still get its end date.
                for child in record.children:
                    self.visit(child, None, keep_parent=True)
                return
            organisation = Organisation(
                id=uuid.uuid4(),
                source=SOURCE_REGISTRY,
                parent_id=parent.id if parent else None,
                **values,
            )
            self.db.add(organisation)
            self.counts.created += 1
        else:
            changed = False
            if organisation.source != SOURCE_REGISTRY:
                organisation.source = SOURCE_REGISTRY
                self.counts.adopted += 1
                changed = True
            for name in _FIELDS:
                if getattr(organisation, name) != values[name]:
                    setattr(organisation, name, values[name])
                    changed = True
            if not keep_parent:
                parent_id = parent.id if parent else None
                if organisation.parent_id != parent_id:
                    organisation.parent_id = parent_id
                    changed = True
            if changed:
                self.counts.updated += 1
            else:
                self.counts.unchanged += 1

        self.seen.add(organisation.id)
        if organisation.tooi_uri:
            self.by_tooi[organisation.tooi_uri] = organisation
        for child in record.children:
            self.visit(child, organisation)


async def _referenced_ids(db: AsyncSession) -> set[uuid.UUID]:
    """Organisations any other table points at.

    Read from the table metadata, so a new reference to an organisation is
    respected here without anyone remembering to add it.
    """
    referenced: set[uuid.UUID] = set()
    target = Organisation.__table__.c.id
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if table is Organisation.__table__ and column.name == "parent_id":
                continue
            if any(fk.column is target for fk in column.foreign_keys):
                rows = await db.execute(
                    select(column).where(column.is_not(None)).distinct()
                )
                referenced.update(rows.scalars().all())
    return referenced


async def apply_registry(
    db: AsyncSession,
    roots: Iterable[RegistryOrganisation],
    *,
    today: date | None = None,
) -> SyncCounts:
    """Bring the organisation table in line with the export.

    Changes are flushed, not committed: the caller owns the transaction, and
    an exception here leaves it to the caller to roll everything back.
    """
    today = today or date.today()
    existing = list((await db.execute(select(Organisation))).scalars().all())
    active_before = sum(
        1
        for o in existing
        if o.source == SOURCE_REGISTRY and (o.end_date is None or o.end_date > today)
    )

    sync = _Sync(db, existing, today)
    for root in roots:
        sync.visit(root, None)
    counts = sync.counts

    if counts.seen == 0:
        raise SyncRefusedError(
            "De export bevat geen organisaties. Er is niets gewijzigd."
        )
    if active_before >= _SHRINK_GUARD_MINIMUM and counts.seen < active_before / 2:
        raise SyncRefusedError(
            f"De export bevat {counts.seen} organisaties, terwijl grip er "
            f"{active_before} heeft. Dat is te weinig om te vertrouwen. "
            "Er is niets gewijzigd."
        )
    await db.flush()

    # No longer in the export: close, never delete outright.
    for organisation in existing:
        if (
            organisation.source == SOURCE_REGISTRY
            and organisation.id not in sync.seen
            and (organisation.end_date is None or organisation.end_date > today)
        ):
            organisation.end_date = today
            counts.closed += 1
    await db.flush()

    # Ended and referred to by nothing: remove, leaves first.
    referenced = await _referenced_ids(db)
    everything = list((await db.execute(select(Organisation))).scalars().all())
    children: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for organisation in everything:
        if organisation.parent_id is not None:
            children[organisation.parent_id].add(organisation.id)
    candidates = {
        o.id: o
        for o in everything
        if o.source == SOURCE_REGISTRY
        and o.end_date is not None
        and o.end_date <= today
        and o.id not in referenced
    }
    while True:
        leaves = [o for o in candidates.values() if not children.get(o.id)]
        if not leaves:
            break
        for organisation in leaves:
            await db.delete(organisation)
            del candidates[organisation.id]
            if organisation.parent_id is not None:
                children[organisation.parent_id].discard(organisation.id)
            counts.deleted += 1
        await db.flush()

    return counts


__all__ = ["SOURCE_MANUAL", "SyncCounts", "SyncRefusedError", "apply_registry"]
