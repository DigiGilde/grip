"""Remember what a read model computed until something it rests on changes.

The figures of an assignment are computed, never stored (docs/domein.md).
Computing them for every assignment on every request does not hold at the
size of a real organisation: a list of 400 assignments priced 400 times per
page view. This module keeps the outcome of such a computation in memory,
under a key that changes when anything the computation rests on changes, so
a value is computed once per change instead of once per request.

The key is read from the event stream, which records every change of domain
data (grip.events.completeness holds the build to that):

- the *local* stamp of an assignment is the latest event of its case;
- the *shared* stamp is the latest event that is not about exactly one
  assignment: a rate card, a billing scale, a cost item, a person, an
  organisation, a setting.

A value of assignment X is kept under (X, local stamp of X, shared stamp).
Closing a month of another assignment leaves it alone; a new rate card
drops everything. Reads of data (``data.read``) and the kinds in
``UNRELATED_KINDS`` never count.

Only kinds in ``LOCAL_KINDS`` are trusted to touch nothing but the
assignment they are filed under. A kind that is not listed counts for every
assignment, so a new kind is safe before anyone thinks about it.

Nothing here knows about access: what is remembered is the full read model,
and the route still leaves out what the reader may not see. A remembered
value holds no database rows, only plain values.

A change that is not about one assignment (a rate, a person, a cost item)
moves the shared stamp of all of them, while it changes the figures of few.
For that there is a second way to remember: ``by_content`` keeps the outcome
of a pure computation under a digest of everything it is given. After such
a change the inputs are read again, together, and only the assignments
whose inputs differ are computed again.

``READ_CACHE=verify`` (the test suite) computes every remembered value again
and fails when the two differ; ``READ_CACHE=off`` computes always.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import os
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable, Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.types import String

from grip.events.completeness import NOT_DOMAIN
from grip.events.retention import READ_TYPE
from grip.events.stream import events_written
from grip.models.stream_event import StreamEvent

# Subject kinds whose events, filed under an assignment, change nothing of
# any other assignment.
LOCAL_KINDS: frozenset[str] = frozenset(
    {
        "assignment",
        "assignment_role",
        "budget_line",
        "allocation",
        "month_close",
        "billing_export",
        "billing_delivery",
        "billing_terms",
        "billing_correction",
        "outgoing_invoice",
        "quote",
        "quote_acceptance",
        "quote_rejection",
        "quote_offer",
        "quote_draft",
        "final_report",
        # A message about one assignment: a factuurverzoek that was mailed.
        "mail_outbox",
    }
)

# Subject kinds that no figure of an assignment rests on.
UNRELATED_KINDS: frozenset[str] = frozenset(
    {
        "task",
        "task_note",
        "vacancy",
        "vacancy_step",
        "vacancy_decision",
        "vacancy_text",
        "vacancy_text_review",
        "vacancy_text_remark",
        "vacancy_publication",
        "vacancy_text_library",
        "form_template",
        "passkey_credential",
        "notification_preference",
        "push_subscription",
        # Who holds which function decides what a reader sees, not what the
        # figures are; a target is about a person's year, not an assignment.
        "person_role",
        "person_roles",
        "billability_target",
    }
)

# For a read model that prices inzet only: external costs do not touch it.
COST_KINDS: frozenset[str] = frozenset(
    {"cost_item", "invoice_line", "cost_coverage", "invoice_attachment"}
)

MODE_ON = "on"
MODE_OFF = "off"
MODE_VERIFY = "verify"


def _max_entries() -> int:
    try:
        return max(100, int(os.environ.get("READ_CACHE_MAX_ENTRIES", "8000")))
    except ValueError:
        return 8000


# How many values each of the two memories keeps; the oldest go first. A
# value of an assignment measured about 20 kB at 400 assignments, so 8,000
# is in the order of 150 MB per server process. Both memories mostly hold
# the same values, so the two together are not twice that.
MAX_ENTRIES = _max_entries()
MAX_CONTENT_ENTRIES = MAX_ENTRIES

_STAMPS = "grip_read_cache_stamps"
_EPOCH = "grip_read_cache_epoch"

_store: OrderedDict[Hashable, Any] = OrderedDict()
_by_content: OrderedDict[tuple[str, str], Any] = OrderedDict()
hits = 0
misses = 0
content_hits = 0
content_misses = 0


def mode() -> str:
    value = os.environ.get("READ_CACHE", MODE_ON).lower()
    return value if value in (MODE_ON, MODE_OFF, MODE_VERIFY) else MODE_ON


def clear() -> None:
    _store.clear()
    _by_content.clear()
    _shared_known.clear()


class StaleReadError(AssertionError):
    """A remembered value differs from what the same computation gives now."""


@dataclasses.dataclass(frozen=True)
class Stamp:
    local: str
    shared: str | None
    # Set while the session holds changes no event covers yet: such a
    # session shares nothing with any other.
    private: Hashable = None


# -- the session's own writes -------------------------------------------------


@sa_event.listens_for(Session, "before_flush")
def _on_flush(session: Session, flush_context: Any, instances: Any) -> None:
    changed = False
    recorded = False
    for obj in session.new:
        if isinstance(obj, StreamEvent):
            recorded = True
        elif _is_domain(obj):
            changed = True
    if not changed:
        changed = any(_is_domain(obj) for obj in session.deleted) or any(
            _is_domain(obj) and session.is_modified(obj) for obj in session.dirty
        )
    if changed or recorded:
        session.info.pop(_STAMPS, None)
    if changed and not recorded:
        # A change whose event has not been written yet: until it is, the
        # stream does not tell this session's state apart from the one
        # before, so what it computes is its own.
        session.info[_EPOCH] = (object(), session.info.get(_EPOCH, (None, 0))[1] + 1)


def _is_domain(obj: Any) -> bool:
    table = getattr(obj, "__tablename__", None)
    return table is not None and table not in NOT_DOMAIN


# -- stamps -------------------------------------------------------------------

# The newest event that counts for every assignment, looked for only among
# the events after ``upto``; with it the last event of the stream, and
# whether the event at ``upto`` is still the one that was seen there.
_SHARED_SQL = text(
    f"""
    SELECT
        (SELECT hash FROM stream_event WHERE seq = :upto) AS still,
        head.seq AS head_seq,
        head.hash AS head_hash,
        shared.hash AS shared_hash
    FROM (SELECT seq, hash FROM stream_event ORDER BY seq DESC LIMIT 1) AS head
    LEFT JOIN LATERAL (
        SELECT hash FROM stream_event
        WHERE seq > :upto
          AND type <> '{READ_TYPE}'
          AND subject_kind <> ALL(:unrelated)
          AND (case_kind IS DISTINCT FROM 'assignment'
               OR subject_kind <> ALL(:local))
        ORDER BY seq DESC LIMIT 1
    ) AS shared ON true
    """
).bindparams(
    bindparam("unrelated", type_=ARRAY(String)),
    bindparam("local", type_=ARRAY(String)),
)

# Per set of kinds: up to which event this process looked, the hash of that
# event, and the shared stamp found so far. The stream only grows, so the
# next look reads the events after it instead of walking back to the last
# shared one, which may be months and many reads ago.
_shared_known: dict[Hashable, tuple[int, str, str | None]] = {}


async def _shared_stamp(
    session: AsyncSession, ignore: frozenset[str], count: frozenset[str]
) -> str | None:
    key = (ignore, count)
    params = {
        "unrelated": sorted((UNRELATED_KINDS | ignore) - count),
        "local": sorted(LOCAL_KINDS),
    }
    known = _shared_known.get(key)
    row = None
    if known is not None:
        row = (await session.execute(_SHARED_SQL, {**params, "upto": known[0]})).first()
        if row is None or row.still != known[1]:
            # Another stream than the one that was seen: emptied, or filled
            # again from the start.
            _shared_known.pop(key, None)
            known = row = None
    if known is None:
        row = (await session.execute(_SHARED_SQL, {**params, "upto": 0})).first()
        if row is None:
            return None
        shared = row.shared_hash
    else:
        assert row is not None
        shared = row.shared_hash if row.shared_hash is not None else known[2]
    # Kept only by a session that wrote no event itself: what such a session
    # sees is committed, and stays.
    if events_written(session) == 0 and session.info.get(_EPOCH) is None:
        _shared_known[key] = (row.head_seq, row.head_hash, shared)
    if mode() == MODE_VERIFY and known is not None:
        full = (await session.execute(_SHARED_SQL, {**params, "upto": 0})).first()
        if full is None or full.shared_hash != shared:
            raise StaleReadError(
                "het gedeelde stempel klopt niet met de stroom: "
                f"{shared} tegenover {full.shared_hash if full else None}"
            )
    return shared


_LOCAL_SQL = text(
    """
    SELECT wanted.id, latest.hash
    FROM unnest(:ids) AS wanted(id)
    CROSS JOIN LATERAL (
        SELECT hash FROM stream_event
        WHERE case_kind = 'assignment' AND case_id = wanted.id
        ORDER BY seq DESC LIMIT 1
    ) AS latest
    """
).bindparams(bindparam("ids", type_=ARRAY(PG_UUID(as_uuid=True))))


async def stamps(
    session: AsyncSession,
    assignment_ids: Iterable[UUID],
    *,
    ignore: frozenset[str] = frozenset(),
    count: frozenset[str] = frozenset(),
) -> dict[UUID, Stamp]:
    """The stamp of each assignment; none for one without any event.

    Asked once per request for all the assignments a list shows: two
    statements, whatever the number of assignments. ``ignore`` names more
    kinds the read model does not rest on; ``count`` names kinds from
    ``UNRELATED_KINDS`` that it does rest on.
    """
    wanted = list(dict.fromkeys(assignment_ids))
    if not wanted or mode() == MODE_OFF:
        return {}
    # The statements below flush first, so the session's own events count.
    await session.flush()
    known: dict[Any, Any] = session.info.setdefault(_STAMPS, {})
    if ("shared", ignore, count) not in known:
        known["shared", ignore, count] = await _shared_stamp(session, ignore, count)
    local: dict[UUID, str | None] = known.setdefault("local", {})
    missing = [i for i in wanted if i not in local]
    if missing:
        rows = await session.execute(_LOCAL_SQL, {"ids": missing})
        found = {row[0]: row[1] for row in rows}
        for assignment_id in missing:
            local[assignment_id] = found.get(assignment_id)
    private = session.info.get(_EPOCH)
    shared = known["shared", ignore, count]
    return {
        i: Stamp(local[i], shared, private)  # type: ignore[arg-type]
        for i in wanted
        if local[i] is not None
    }


_HEAD_SQL = text(
    f"""
    SELECT hash FROM stream_event WHERE seq = (
        SELECT seq FROM stream_event WHERE type <> '{READ_TYPE}'
        ORDER BY seq DESC LIMIT 1
    )
    """
)


async def head_stamp(session: AsyncSession) -> tuple[str | None, Hashable]:
    """A value that changes with every change of domain data.

    The latest event that is not a read, and the mark of a session that
    holds changes no event covers yet.
    """
    await session.flush()
    head = (await session.execute(_HEAD_SQL)).scalar_one_or_none()
    return head, session.info.get(_EPOCH)


# -- remembering --------------------------------------------------------------


def _plain(value: Any) -> Any:
    """A value as nested plain data, to compare two computations."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return (
            type(value).__name__,
            tuple(
                (f.name, _plain(getattr(value, f.name)))
                for f in dataclasses.fields(value)
            ),
        )
    if isinstance(value, dict):
        return tuple(sorted((repr(k), _plain(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_plain(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(repr(_plain(v)) for v in value))
    if hasattr(value, "__table__"):
        raise TypeError(
            f"een onthouden waarde bevat een databaserij ({type(value).__name__})"
        )
    return value


async def remember_many[T](
    session: AsyncSession,
    name: str,
    assignment_ids: Iterable[UUID],
    key: Hashable,
    compute: Callable[[list[UUID]], Awaitable[dict[UUID, T]]],
    *,
    ignore: frozenset[str] = frozenset(),
    count: frozenset[str] = frozenset(),
) -> dict[UUID, T]:
    """``compute(ids)`` per assignment, or what it gave since the last change.

    ``name`` and ``key`` tell computations apart: the name of the read model
    and its arguments. ``compute`` is asked only for the assignments nothing
    is remembered of, all at once, so it can read what they share once. A
    value must be plain data (dataclasses, tuples, numbers, text); it is
    shared between requests and must not be changed.
    """
    global hits, misses
    wanted = list(dict.fromkeys(assignment_ids))
    current = mode()
    if current == MODE_OFF or not wanted:
        return await compute(wanted) if wanted else {}
    before = await stamps(session, wanted, ignore=ignore, count=count)
    result: dict[UUID, T] = {}
    missing: list[UUID] = []
    for assignment_id in wanted:
        stamp = before.get(assignment_id)
        full = (name, assignment_id, key, stamp)
        if stamp is not None and full in _store:
            _store.move_to_end(full)
            result[assignment_id] = _store[full]
        else:
            missing.append(assignment_id)
    hits += len(result)
    misses += len(missing)
    if current == MODE_VERIFY and result:
        fresh = await compute(list(result))
        for assignment_id, kept in result.items():
            if _plain(fresh[assignment_id]) != _plain(kept):
                raise StaleReadError(
                    f"{name} van opdracht {assignment_id} is veranderd zonder "
                    "dat de gebeurtenissen dat zeggen"
                )
    if missing:
        computed = await compute(missing)
        # Kept only when the stamp still holds: the computation may itself
        # have written (it should not), and then the value is of another
        # state.
        after = await stamps(session, missing, ignore=ignore, count=count)
        for assignment_id in missing:
            value = computed[assignment_id]
            result[assignment_id] = value
            stamp = before.get(assignment_id)
            if stamp is None or after.get(assignment_id) != stamp:
                continue
            if current == MODE_VERIFY:
                _plain(value)
            _store[(name, assignment_id, key, stamp)] = value
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)
    return {assignment_id: result[assignment_id] for assignment_id in wanted}


async def remember[T](
    session: AsyncSession,
    name: str,
    assignment_id: UUID,
    key: Hashable,
    compute: Callable[[], Awaitable[T]],
    *,
    ignore: frozenset[str] = frozenset(),
) -> T:
    """``remember_many`` for one assignment."""

    async def one(_ids: list[UUID]) -> dict[UUID, T]:
        return {assignment_id: await compute()}

    found = await remember_many(session, name, [assignment_id], key, one, ignore=ignore)
    return found[assignment_id]


async def remember_all[T](
    session: AsyncSession,
    name: str,
    key: Hashable,
    compute: Callable[[], Awaitable[T]],
) -> T:
    """``compute()``, or what it gave since the last change of any data.

    For a read model over many assignments or persons at once (a report):
    kept until the next event that is not a read.
    """
    global hits, misses
    current = mode()
    if current == MODE_OFF:
        return await compute()
    stamp = await head_stamp(session)
    if stamp[0] is None:
        return await compute()
    full = (name, key, stamp)
    if full in _store:
        _store.move_to_end(full)
        hits += 1
        kept: T = _store[full]
        if current == MODE_VERIFY and _plain(await compute()) != _plain(kept):
            raise StaleReadError(
                f"{name} is veranderd zonder dat de gebeurtenissen dat zeggen"
            )
        return kept
    misses += 1
    value = await compute()
    if await head_stamp(session) == stamp:
        if current == MODE_VERIFY:
            _plain(value)
        _store[full] = value
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)
    return value


# -- remembering by what a computation is given -------------------------------


def _canonical(value: Any) -> Any:
    """A value as nested plain data that reads the same for the same content."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return (
            type(value).__name__,
            tuple(
                _canonical(getattr(value, f.name)) for f in dataclasses.fields(value)
            ),
        )
    if isinstance(value, dict):
        return tuple(
            sorted(
                ((repr(_canonical(k)), _canonical(v)) for k, v in value.items()),
                key=lambda pair: pair[0],
            )
        )
    if isinstance(value, (list, tuple)):
        return tuple(_canonical(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(repr(_canonical(v)) for v in value))
    if isinstance(value, enum.Enum):
        return (type(value).__name__, value.name)
    table = getattr(value, "__table__", None)
    if table is not None:
        # A database row counts by the columns that were read. A column that
        # was not read cannot have been used: reading it later would fail.
        held = vars(value)
        return (
            table.name,
            tuple(
                (column.key, _canonical(held[column.key]))
                for column in table.columns
                if column.key in held
            ),
        )
    return value


def digest(*parts: Any) -> str:
    """One short text for the content of ``parts``.

    Two calls give the same text only when every part holds the same
    values. A part that is itself a digest (a text) costs nothing to add,
    so what many computations share is digested once by the caller.
    """
    return hashlib.sha256(repr(_canonical(parts)).encode()).hexdigest()


def by_content[T](name: str, content: str, compute: Callable[[], T]) -> T:
    """``compute()``, or what it gave before for the same content.

    ``content`` is the ``digest`` of everything ``compute`` reads. The
    computation must be pure: no database, no clock, nothing but its
    arguments. The value is shared between requests and must not be changed.
    """
    global content_hits, content_misses
    current = mode()
    if current == MODE_OFF:
        return compute()
    key = (name, content)
    if key in _by_content:
        _by_content.move_to_end(key)
        content_hits += 1
        kept: T = _by_content[key]
        if current == MODE_VERIFY and _plain(compute()) != _plain(kept):
            raise StaleReadError(
                f"{name} geeft iets anders voor wat dezelfde invoer zou zijn"
            )
        return kept
    content_misses += 1
    value = compute()
    if current == MODE_VERIFY:
        _plain(value)
    _by_content[key] = value
    while len(_by_content) > MAX_CONTENT_ENTRIES:
        _by_content.popitem(last=False)
    return value
