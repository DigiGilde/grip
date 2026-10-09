"""Organisations: searching the list, manual additions, and the register sync.

Clients and contractors are picked from one list. Most of it comes from the
public register of government organisations (see
``grip.integrations.organisations``); what the register does not hold is
added by hand and marked as manual.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import BytesIO
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Text,
    and_,
    case,
    cast,
    exists,
    func,
    or_,
    select,
    true,
)
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core import clock
from grip.core.audit import CREATE, UPDATE, record_audit
from grip.integrations.organisations.source import (
    REGISTRY_URL,
    RegistryFormatError,
    RegistryUnavailableError,
    fetch_registry,
    iter_root_organisations,
)
from grip.integrations.organisations.sync import SyncRefusedError, apply_registry
from grip.models.assignment import Assignment
from grip.models.organisation import (
    SOURCE_MANUAL,
    SOURCE_REGISTRY,
    Organisation,
    OrganisationSyncRun,
)
from grip.models.person import Person
from grip.services import stale
from grip.services.errors import DomainValidationError, NotFoundError

PATH_SEPARATOR = " > "
MAX_PAGE_SIZE = 100

# Types the register hangs under a ministry without making them its parts.
# A unit of such a type is shown below the ministry it is related to. The
# same set Wies uses for its organisation picker.
NESTED_TYPES = frozenset(
    {"Agentschap", "Zelfstandig bestuursorgaan", "Adviescollege", "Inspectie"}
)

# Without a query the list starts with what is most often meant.
_TYPE_ORDER = ("Ministerie", "Agentschap", "Zelfstandig bestuursorgaan", "Inspectie")

_ACCENTED = "áàâäãåéèêëíìîïóòôöõúùûüçñ"
_PLAIN = "aaaaaaeeeeiiiiooooouuuucn"


def fold(value: str) -> str:
    """Lower case without accents, so "financien" finds "Financiën"."""
    return value.lower().translate(str.maketrans(_ACCENTED, _PLAIN))


def _fold_sql(expression: ColumnElement[Any]) -> ColumnElement[str]:
    return func.translate(func.lower(expression), _ACCENTED, _PLAIN)


def _like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class OrganisationHit:
    organisation: Organisation
    # Labels from the top of the hierarchy down to the organisation itself.
    path: tuple[str, ...]

    @property
    def path_label(self) -> str:
        return PATH_SEPARATOR.join(self.path)


@dataclass(frozen=True)
class SearchResult:
    items: list[OrganisationHit]
    total: int
    page: int
    page_size: int


# --- reading ------------------------------------------------------------------


async def get_organisation(
    db: AsyncSession, organisation_id: uuid.UUID
) -> Organisation:
    organisation = await db.get(Organisation, organisation_id)
    if organisation is None:
        raise NotFoundError("Organisatie", organisation_id)
    return organisation


async def with_paths(
    db: AsyncSession, organisations: list[Organisation]
) -> list[OrganisationHit]:
    """Give each organisation its place in the hierarchy.

    Two organisations with the same name are told apart by what is above
    them. A unit of a nested type without a parent is placed under the
    ministry the register relates it to.
    """
    known: dict[uuid.UUID, Organisation] = {o.id: o for o in organisations}
    wanted = {o.parent_id for o in organisations if o.parent_id} - known.keys()
    while wanted:
        rows = (
            (await db.execute(select(Organisation).where(Organisation.id.in_(wanted))))
            .scalars()
            .all()
        )
        for row in rows:
            known[row.id] = row
        wanted = {r.parent_id for r in rows if r.parent_id} - known.keys()

    def root_of(organisation: Organisation) -> Organisation:
        current = organisation
        guard = 0
        while current.parent_id and current.parent_id in known and guard < 20:
            current = known[current.parent_id]
            guard += 1
        return current

    ministry_toois = {
        root.related_ministry_tooi
        for root in (root_of(o) for o in organisations)
        if root.main_type in NESTED_TYPES and root.related_ministry_tooi
    }
    ministries: dict[str, Organisation] = {}
    if ministry_toois:
        for row in (
            (
                await db.execute(
                    select(Organisation).where(
                        Organisation.tooi_uri.in_(ministry_toois),
                        Organisation.unit_key.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        ):
            ministries[row.tooi_uri or ""] = row

    hits = []
    for organisation in organisations:
        chain = [organisation]
        guard = 0
        while chain[-1].parent_id and chain[-1].parent_id in known and guard < 20:
            chain.append(known[chain[-1].parent_id])
            guard += 1
        root = chain[-1]
        if root.main_type in NESTED_TYPES and root.related_ministry_tooi:
            ministry = ministries.get(root.related_ministry_tooi)
            if ministry is not None and ministry.id != root.id:
                chain.append(ministry)
        hits.append(
            OrganisationHit(
                organisation=organisation,
                path=tuple(o.display_name for o in reversed(chain)),
            )
        )
    return hits


def _abbreviation_match(pattern_or_value: str, *, exact: bool) -> ColumnElement[bool]:
    element = func.jsonb_array_elements_text(Organisation.abbreviations).table_valued(
        "value"
    )
    folded = _fold_sql(element.c.value)
    condition = (
        folded == pattern_or_value
        if exact
        else folded.like(pattern_or_value, escape="\\")
    )
    return exists(select(1).select_from(element).where(condition))


async def search_organisations(
    db: AsyncSession,
    *,
    query: str = "",
    organisation_type: str | None = None,
    source: str | None = None,
    include_ended: bool = False,
    page: int = 1,
    page_size: int = 20,
    today: date | None = None,
) -> SearchResult:
    """Search on name and abbreviation.

    Every word of the query must occur in the name, the label or an
    abbreviation. Ranking: an exact abbreviation first, then an exact name,
    then an abbreviation or name that starts with the query, then a word in
    the name that starts with it, then the rest. Within a rank, organisations
    already used on an assignment come first.
    """
    today = today or clock.today()
    page = max(1, page)
    page_size = max(1, min(MAX_PAGE_SIZE, page_size))
    folded_query = " ".join(fold(query).split())

    name = _fold_sql(Organisation.name)
    label = _fold_sql(func.coalesce(Organisation.label, Organisation.name))
    haystack = _fold_sql(
        func.concat(
            func.coalesce(Organisation.label, ""),
            " ",
            Organisation.name,
            " ",
            cast(Organisation.abbreviations, Text),
        )
    )

    conditions: list[ColumnElement[bool]] = []
    if not include_ended:
        conditions.append(
            or_(Organisation.end_date.is_(None), Organisation.end_date > today)
        )
    if organisation_type:
        conditions.append(Organisation.organisation_types.contains([organisation_type]))
    if source in (SOURCE_REGISTRY, SOURCE_MANUAL):
        conditions.append(Organisation.source == source)
    for word in folded_query.split():
        conditions.append(haystack.like(f"%{_like(word)}%", escape="\\"))

    used = exists(
        select(1).where(
            or_(
                Assignment.client_organisation_id == Organisation.id,
                Assignment.contractor_organisation_id == Organisation.id,
            )
        )
    )
    used_rank = case((used, 0), else_=1)

    if folded_query:
        prefix = f"{_like(folded_query)}%"
        word_prefix = f"% {_like(folded_query)}%"
        rank = case(
            (_abbreviation_match(folded_query, exact=True), 0),
            (or_(name == folded_query, label == folded_query), 1),
            (_abbreviation_match(prefix, exact=False), 2),
            (
                or_(name.like(prefix, escape="\\"), label.like(prefix, escape="\\")),
                3,
            ),
            (
                or_(
                    name.like(word_prefix, escape="\\"),
                    label.like(word_prefix, escape="\\"),
                ),
                4,
            ),
            else_=5,
        )
        # Within a rank: what was used before, then an organisation before
        # its parts ("financien" means the ministry, not a team named so).
        part_rank = case((Organisation.parent_id.is_(None), 0), else_=1)
        order = [
            rank,
            used_rank,
            part_rank,
            func.length(label),
            label,
            Organisation.id,
        ]
    else:
        type_rank = case(
            *[(Organisation.main_type == t, i) for i, t in enumerate(_TYPE_ORDER)],
            else_=len(_TYPE_ORDER),
        )
        manual_rank = case((Organisation.source == SOURCE_MANUAL, 0), else_=1)
        # Parts of an organisation are found by searching, not by browsing.
        top_level = case((Organisation.parent_id.is_(None), 0), else_=1)
        order = [used_rank, manual_rank, top_level, type_rank, label, Organisation.id]

    where = and_(*conditions) if conditions else None
    count_stmt = select(func.count()).select_from(Organisation)
    stmt = select(Organisation)
    if where is not None:
        count_stmt = count_stmt.where(where)
        stmt = stmt.where(where)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        (
            await db.execute(
                stmt.order_by(*order).limit(page_size).offset((page - 1) * page_size)
            )
        )
        .scalars()
        .all()
    )
    return SearchResult(
        items=await with_paths(db, list(rows)),
        total=total,
        page=page,
        page_size=page_size,
    )


async def type_counts(
    db: AsyncSession, *, today: date | None = None
) -> list[tuple[str, int]]:
    """Organisation types with the number of current organisations of each."""
    today = today or clock.today()
    element = func.jsonb_array_elements_text(
        Organisation.organisation_types
    ).table_valued("value")
    rows = await db.execute(
        select(element.c.value, func.count())
        .select_from(Organisation)
        .join(element, true())
        .where(or_(Organisation.end_date.is_(None), Organisation.end_date > today))
        .group_by(element.c.value)
        .order_by(element.c.value)
    )
    return [(name, count) for name, count in rows.all()]


# --- manual organisations -----------------------------------------------------


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", fold(name)).strip("-")
    return slug[:90] or "eenheid"


async def _registered_tooi(db: AsyncSession, parent: Organisation) -> str | None:
    """TOOI URI of the nearest organisation above that has one."""
    current: Organisation | None = parent
    guard = 0
    while current is not None and guard < 20:
        if current.tooi_uri:
            return current.tooi_uri
        current = (
            await db.get(Organisation, current.parent_id) if current.parent_id else None
        )
        guard += 1
    return None


async def create_manual_organisation(
    db: AsyncSession,
    *,
    name: str,
    parent_id: uuid.UUID | None = None,
    instance_uri: str | None = None,
    actor: Person | None,
    today: date | None = None,
) -> Organisation:
    """Add a party the register does not hold, or a unit below one it does.

    A unit gets the TOOI URI of the nearest registered organisation above it
    and an own key. Asking for a name that already exists in the same place
    returns the existing organisation instead of making a second one.
    """
    today = today or clock.today()
    name = " ".join(name.split())
    if not name:
        raise DomainValidationError("Geef de organisatie een naam.")
    if len(name) > 255:
        raise DomainValidationError("De naam is te lang.")

    parent: Organisation | None = None
    if parent_id is not None:
        parent = await db.get(Organisation, parent_id)
        if parent is None:
            raise DomainValidationError("De bovenliggende organisatie bestaat niet.")
        if parent.end_date is not None and parent.end_date <= today:
            raise DomainValidationError(
                "De bovenliggende organisatie bestaat niet meer."
            )

    same_place = (
        Organisation.parent_id.is_(None)
        if parent is None
        else Organisation.parent_id == parent.id
    )
    twin = (
        (
            await db.execute(
                select(Organisation)
                .where(
                    same_place,
                    _fold_sql(Organisation.name) == fold(name),
                    or_(Organisation.end_date.is_(None), Organisation.end_date > today),
                )
                .order_by(Organisation.source.desc(), Organisation.created_at)
            )
        )
        .scalars()
        .first()
    )
    if twin is not None:
        return twin

    tooi_uri = await _registered_tooi(db, parent) if parent is not None else None
    unit_key: str | None = None
    if tooi_uri is not None:
        base = _slug(name)
        taken = set(
            (
                await db.execute(
                    select(Organisation.unit_key).where(
                        Organisation.tooi_uri == tooi_uri
                    )
                )
            )
            .scalars()
            .all()
        )
        unit_key = base
        suffix = 2
        while unit_key in taken:
            unit_key = f"{base}-{suffix}"
            suffix += 1

    organisation = Organisation(
        name=name,
        source=SOURCE_MANUAL,
        parent_id=parent.id if parent else None,
        tooi_uri=tooi_uri,
        unit_key=unit_key,
        instance_uri=instance_uri or None,
    )
    db.add(organisation)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="organisation",
        entity_id=organisation.id,
        new_value={
            "name": name,
            "source": SOURCE_MANUAL,
            "parent_id": str(parent.id) if parent else None,
        },
    )
    return organisation


async def update_organisation(
    db: AsyncSession,
    organisation_id: uuid.UUID,
    changes: dict[str, Any],
    *,
    actor: Person | None,
) -> Organisation:
    """Change what grip owns.

    Of an organisation from the register only the instance URI can be
    changed; everything else follows the register. A manual organisation can
    also be renamed and given an end date.
    """
    organisation = await get_organisation(db, organisation_id)
    allowed = {"instance_uri"}
    await stale.check(db, organisation, "deze organisatie")
    stale.touch(organisation)
    if organisation.source == SOURCE_MANUAL:
        allowed |= {"name", "end_date"}
    refused = sorted(set(changes) - allowed)
    if refused:
        raise DomainValidationError(
            "Deze organisatie komt uit het register; alleen het adres van de "
            "grip-instantie is hier te wijzigen."
            if organisation.source == SOURCE_REGISTRY
            else f"Niet te wijzigen: {', '.join(refused)}."
        )
    old: dict[str, Any] = {}
    new: dict[str, Any] = {}
    for key, value in changes.items():
        if key == "name":
            value = " ".join(str(value).split())
            if not value:
                raise DomainValidationError("Geef de organisatie een naam.")
        if key == "instance_uri":
            value = (value or "").strip() or None
            if value is not None and not value.startswith(("https://", "http://")):
                raise DomainValidationError(
                    "Het adres van de instantie is een volledige URI."
                )
        current = getattr(organisation, key)
        if current != value:
            old[key] = current.isoformat() if isinstance(current, date) else current
            new[key] = value.isoformat() if isinstance(value, date) else value
            setattr(organisation, key, value)
    if new:
        await db.flush()
        record_audit(
            db,
            actor=actor,
            action=UPDATE,
            entity="organisation",
            entity_id=organisation.id,
            old_value=old,
            new_value=new,
        )
    return organisation


# --- the register sync --------------------------------------------------------


async def last_sync_run(db: AsyncSession) -> OrganisationSyncRun | None:
    return (
        (
            await db.execute(
                select(OrganisationSyncRun)
                .order_by(OrganisationSyncRun.finished_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def run_registry_sync(
    db: AsyncSession,
    *,
    actor: Person | None,
    url: str = REGISTRY_URL,
    content: bytes | None = None,
    today: date | None = None,
) -> OrganisationSyncRun:
    """Fetch the register and bring the list in line with it.

    The export is downloaded in full before anything changes, and the changes
    are applied inside one savepoint: a failure anywhere leaves the list as it
    was. The run itself is always recorded, also when it failed, so the
    beheerder sees what happened. ``content`` is for tests and for a file
    that was downloaded earlier.
    """
    started_at = datetime.now(UTC)
    result: dict[str, Any] = {}
    error: str | None = None
    try:
        if content is None:
            content = await fetch_registry(url)
        async with db.begin_nested():
            counts = await apply_registry(
                db, iter_root_organisations(BytesIO(content)), today=today
            )
        result = counts.as_dict()
    except (RegistryUnavailableError, RegistryFormatError, SyncRefusedError) as exc:
        error = str(exc)

    run = OrganisationSyncRun(
        started_at=started_at,
        finished_at=datetime.now(UTC),
        status="failed" if error else "completed",
        source_url=url,
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
            entity="organisation_sync",
            entity_id=run.id,
            new_value=result,
        )
    return run
