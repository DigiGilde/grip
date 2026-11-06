"""A cost item that another organisation keeps (ADR 0052, 0053).

Here such an item is a reference: its own URI, the executor and what is this
organisation's own, the coverage by its budget lines. Description, amount
and invoice lines belong to the executor. This side asks the executor to
make or change the item, and reads it there when it needs it.

Until the executor applied a request, the reference holds what was asked;
after that it holds nothing of the executor's. What is read is never stored.

The domain does not know how instances are connected (ADR 0015). It asks
through two lookups that the part of grip that does know registers: which
organisations can be an executor, and what an executor has for a set of
references. While nobody has, no organisation can be chosen and nothing can
be read.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import UPDATE, record_audit
from grip.models.cost import (
    REQUEST_APPLIED,
    REQUEST_REFUSED,
    REQUEST_STATUSES,
    REQUEST_UNDELIVERED,
    REQUEST_WAITING,
    CostItem,
)
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.services import read_cache
from grip.services.assignments import mint_uri
from grip.services.errors import DomainValidationError
from grip.services.guards import audit_fields

URI_SEGMENT = "kostenpost"

NOT_CONNECTED = (
    "Met deze organisatie is geen koppeling. Een kostenpost kan alleen worden "
    "uitgevoerd door een organisatie waarmee grip gekoppeld is."
)
LINES_AT_EXECUTOR = (
    "De facturen van deze kostenpost staan bij de organisatie die haar "
    "uitvoert. Ze zijn hier niet te wijzigen."
)
EXECUTOR_FIXED = "De organisatie die een kostenpost uitvoert, kan niet wijzigen."
REQUESTED_HERE = (
    "Deze kostenpost is gevraagd door een andere organisatie en kan zelf geen "
    "uitvoerder hebben."
)

_REQUEST_FIELDS = (
    "description",
    "budgeted_cents",
    "request_period",
    "request_sequence",
    "request_status",
    "executor_has_item",
)


# -- who can be an executor ----------------------------------------------------

# The ids of the organisations a cost item can be asked of.
ExecutorLookup = Callable[[AsyncSession], Awaitable[set[UUID]]]

_executor_lookup: ExecutorLookup | None = None


def register_executor_lookup(lookup: ExecutorLookup | None) -> None:
    global _executor_lookup
    _executor_lookup = lookup


async def possible_executor_ids(session: AsyncSession) -> set[UUID]:
    if _executor_lookup is None:
        return set()
    return await _executor_lookup(session)


async def possible_executors(session: AsyncSession) -> list[Organisation]:
    """The organisations a cost item can be asked of, by name."""
    ids = await possible_executor_ids(session)
    if not ids:
        return []
    rows = await session.execute(select(Organisation).where(Organisation.id.in_(ids)))
    return sorted(rows.scalars(), key=lambda o: (o.label or o.name).casefold())


async def require_possible_executor(
    session: AsyncSession, organisation_id: UUID
) -> None:
    if organisation_id not in await possible_executor_ids(session):
        raise DomainValidationError(NOT_CONNECTED)


# -- what the executor has -------------------------------------------------------


@dataclass(frozen=True)
class FetchedLine:
    kind: str
    amount_cents: int
    reference: str | None = None
    description: str | None = None
    period: date | None = None


@dataclass(frozen=True)
class FetchedItem:
    """A cost item as its executor gave it just now."""

    description: str
    budgeted_cents: int
    lines: tuple[FetchedLine, ...]


# Reads at one executor the items behind these references, by cost item id
# here. None for an item the executor does not have; the whole answer is
# None when the executor could not be read.
Reader = Callable[
    [AsyncSession, UUID, list[UUID]], Awaitable[dict[UUID, FetchedItem | None] | None]
]

_reader: Reader | None = None


def register_reader(reader: Reader | None) -> None:
    global _reader
    _reader = reader


def clear() -> None:
    """Forget what was registered. For tests."""
    register_executor_lookup(None)
    register_reader(None)


class ReferenceState(StrEnum):
    # The executor has not made the item yet: the request is on its way.
    WAITING = "waiting"
    REFUSED = "refused"
    # The request could not be delivered; it is not tried again.
    UNDELIVERED = "undelivered"
    # Read at the executor just now.
    FOUND = "found"
    # The executor could not be read, or does not have the item (anymore).
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class Reference:
    cost_item_id: UUID
    executor_name: str
    state: ReferenceState
    # What the executor has; only when found.
    content: FetchedItem | None = None
    # What became of a later request to change the item, while the executor
    # has not applied it: waiting, refused or undelivered.
    change: str | None = None

    @property
    def counts(self) -> bool:
        """Only what was read at the executor counts in a total."""
        return self.state is ReferenceState.FOUND

    @property
    def unknown(self) -> bool:
        """Something is spent here that cannot be counted now: a total that
        includes this reference is incomplete."""
        return self.state in (
            ReferenceState.WAITING,
            ReferenceState.UNDELIVERED,
            ReferenceState.UNREACHABLE,
        )


def is_reference(item: CostItem) -> bool:
    return item.executor_organisation_id is not None


def reference_uri(cost_item_id: UUID) -> str:
    return mint_uri(URI_SEGMENT, cost_item_id)


async def _names(session: AsyncSession, ids: set[UUID]) -> dict[UUID, str]:
    if not ids:
        return {}
    rows = await session.execute(
        select(Organisation.id, Organisation.label, Organisation.name).where(
            Organisation.id.in_(ids)
        )
    )
    return {organisation_id: label or name for organisation_id, label, name in rows}


def _state_before_creation(item: CostItem) -> ReferenceState:
    if item.request_status == REQUEST_REFUSED:
        return ReferenceState.REFUSED
    if item.request_status == REQUEST_UNDELIVERED:
        return ReferenceState.UNDELIVERED
    return ReferenceState.WAITING


async def read(
    session: AsyncSession, items: Iterable[CostItem]
) -> dict[UUID, Reference]:
    """What every reference among ``items`` stands for now, by cost item id.

    One question per executor for all its references. Items without an
    executor are left out.
    """
    references = [item for item in items if is_reference(item)]
    if not references:
        return {}
    read_cache.read_elsewhere()
    names = await _names(
        session,
        {item.executor_organisation_id for item in references},  # type: ignore[misc]
    )
    by_executor: dict[UUID, list[CostItem]] = {}
    for item in references:
        if item.executor_has_item:
            assert item.executor_organisation_id is not None
            by_executor.setdefault(item.executor_organisation_id, []).append(item)
    fetched: dict[UUID, FetchedItem | None] = {}
    unreachable: set[UUID] = set()
    for executor_id, own in by_executor.items():
        ids = [item.id for item in own]
        answer = None if _reader is None else await _reader(session, executor_id, ids)
        if answer is None:
            unreachable.update(ids)
        else:
            fetched.update({i: answer.get(i) for i in ids})

    found: dict[UUID, Reference] = {}
    for item in references:
        assert item.executor_organisation_id is not None
        name = names.get(item.executor_organisation_id, "")
        if not item.executor_has_item:
            found[item.id] = Reference(item.id, name, _state_before_creation(item))
            continue
        content = fetched.get(item.id)
        if item.id in unreachable or content is None:
            found[item.id] = Reference(item.id, name, ReferenceState.UNREACHABLE)
            continue
        change = item.request_status if item.request_status != REQUEST_APPLIED else None
        found[item.id] = Reference(
            item.id, name, ReferenceState.FOUND, content=content, change=change
        )
    return found


# -- asking the executor ----------------------------------------------------------


async def ask(
    session: AsyncSession,
    item: CostItem,
    *,
    actor: Person | None,
    description: str,
    budgeted_cents: int,
    period: date | None = None,
) -> None:
    """Ask the executor to make the item, or to change it as given.

    The request waits here until the part of grip that sends it to the
    executor has done so; a later request overtakes one that waits.
    """
    if budgeted_cents < 0:
        raise DomainValidationError("Een bedrag kan niet negatief zijn.")
    old = audit_fields(item, _REQUEST_FIELDS)
    item.description = description
    item.budgeted_cents = budgeted_cents
    if not item.executor_has_item and period is not None:
        item.request_period = period
    item.request_sequence += 1
    item.request_status = REQUEST_WAITING
    await session.flush()
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="cost_item",
        entity_id=item.id,
        old_value=old,
        new_value=audit_fields(item, _REQUEST_FIELDS),
    )


async def waiting(session: AsyncSession) -> list[CostItem]:
    """References with a request that the executor has not answered yet."""
    rows = await session.execute(
        select(CostItem)
        .where(
            CostItem.executor_organisation_id.is_not(None),
            CostItem.request_status == REQUEST_WAITING,
        )
        .order_by(CostItem.updated_at, CostItem.id)
    )
    return list(rows.scalars())


async def answered(
    session: AsyncSession, cost_item_id: UUID, sequence: int, outcome: str
) -> None:
    """The executor answered request number ``sequence``.

    ``outcome`` is applied, refused or undelivered. Once the executor
    applied the last request, what was asked is no longer kept here. An
    answer to a request that a later one overtook only says whether the
    executor has the item.
    """
    if outcome not in REQUEST_STATUSES or outcome == REQUEST_WAITING:
        raise ValueError(f"not an answer: {outcome}")
    item = await session.get(CostItem, cost_item_id)
    if item is None or not is_reference(item):
        return
    old = audit_fields(item, _REQUEST_FIELDS)
    if outcome == REQUEST_APPLIED:
        item.executor_has_item = True
    if sequence == item.request_sequence:
        item.request_status = outcome
        if outcome == REQUEST_APPLIED:
            item.description = None
            item.budgeted_cents = None
            item.request_period = None
    new = audit_fields(item, _REQUEST_FIELDS)
    if new == old:
        return
    await session.flush()
    record_audit(
        session,
        actor=None,
        action=UPDATE,
        entity="cost_item",
        entity_id=item.id,
        old_value=old,
        new_value=new,
    )


__all__ = [
    "EXECUTOR_FIXED",
    "LINES_AT_EXECUTOR",
    "NOT_CONNECTED",
    "REQUESTED_HERE",
    "FetchedItem",
    "FetchedLine",
    "Reference",
    "ReferenceState",
    "answered",
    "ask",
    "clear",
    "is_reference",
    "possible_executor_ids",
    "possible_executors",
    "read",
    "reference_uri",
    "register_executor_lookup",
    "register_reader",
    "require_possible_executor",
    "waiting",
]
