"""Taking a typed text that never belonged out of a moment (ADR 0057).

A beheerder chooses texts in one moment of an assignment. In one transaction
grip records every fact of the case that holds one of them again without it,
as a herstelfeit (``fact_restated``), and then erases the values of those facts
and of every other event of the case that holds it as typed text. The database
only erases every value of an event, never one field. Not touched: the frozen
content of an issued quote, what was sent to another organisation, and an event
that only mentions the text elsewhere.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.chronicle import restate
from grip.chronicle.facts import FACTS, LINE
from grip.chronicle.ledger import Gram
from grip.chronicle.writer import SUBJECT_KIND, establish
from grip.core.audit import UPDATE, record_audit
from grip.events import context, retention, stream
from grip.models.assignment import Assignment
from grip.models.person import Person
from grip.models.quote import Quote
from grip.models.stream_event import CASE_ASSIGNMENT, StreamEvent
from grip.repositories.chronicle import ChronicleRepository
from grip.services.canonical import read
from grip.services.errors import DomainValidationError, NotFoundError

# The reason an erasure gives in the stream.
REASON = "restated"
# Grip writes the change lines that bring the rows in line with a herstelfeit;
# who chose to take the text out is the actor of the herstelfeit.
JOB = "restatement"
# Who is on which line holds no typed text, and a stand reads it: a match there
# is a coincidence of a short text, and erasing it would leave stands unknown.
_NEVER_ERASED = ("allocation",)
# A change record of a line names its detail as the screens do.
_AUDIT_KEYS = {(LINE, "detail"): "description"}
# The keys under which another event can hold one of the typed texts. Only
# these are searched: a decision, a status or a piece of evidence that happens
# to mention the text elsewhere keeps its values.
_TEXT_KEYS = frozenset(
    {text.column for text in restate.TYPED_TEXTS} | set(_AUDIT_KEYS.values())
)


def _typed(value: Any) -> list[str]:
    """The values under the keys of typed text, at any depth."""
    if isinstance(value, Mapping):
        found: list[str] = []
        for key, item in value.items():
            if key in _TEXT_KEYS and isinstance(item, str):
                found.append(item)
            else:
                found += _typed(item)
        return found
    if isinstance(value, list | tuple):
        return [text for item in value for text in _typed(item)]
    return []


@dataclass(frozen=True)
class Restated:
    # The positions of the herstelfeiten, in the order they were recorded.
    seqs: list[int]
    # In words, the quotes that still hold a text that went.
    kept: list[str]
    # How many events lost their values.
    erased: int


def moment_of(grams: Iterable[Gram], seq: int) -> Gram:
    """The moment at ``seq``, as long as its values are known."""
    gram = next(
        (item for item in grams if item.seq == seq and FACTS[item.fact].moment), None
    )
    if gram is None or gram.erased:
        raise NotFoundError("Moment", seq)
    return gram


async def quote_contents(
    session: AsyncSession, assignment_id: UUID
) -> list[tuple[str | None, dict[str, Any]]]:
    """The kenmerk and the frozen content of every quote of the case."""
    rows = await session.execute(
        select(Quote.reference, Quote.canonical)
        .where(Quote.assignment_id == assignment_id)
        .order_by(Quote.issued_at, Quote.id)
    )
    return [(row.reference, read(row.canonical)) for row in rows]


def kept(
    contents: Iterable[tuple[str | None, dict[str, Any]]], texts: Sequence[str]
) -> list[str]:
    """In words, the quotes that hold one of the texts."""
    return [
        "De tekst staat ook in "
        f"{f'offerte {reference}' if reference else 'een offerte'}; "
        "die blijft zoals ze is gemaakt."
        for reference, content in contents
        if restate.contains(content, texts)
    ]


async def _holding(
    session: AsyncSession, assignment_id: UUID, texts: Sequence[str]
) -> list[int]:
    """The other events of the case whose values hold one of the texts."""
    rows = await session.execute(
        select(
            StreamEvent.seq,
            StreamEvent.old_value,
            StreamEvent.new_value,
            StreamEvent.payload,
            StreamEvent.note,
        ).where(
            StreamEvent.case_kind == CASE_ASSIGNMENT,
            StreamEvent.case_id == assignment_id,
            StreamEvent.erased_at.is_(None),
            # A fact is restated, never only erased.
            ~(
                (StreamEvent.subject_kind == SUBJECT_KIND)
                & StreamEvent.action.is_(None)
            ),
            StreamEvent.type != retention.ERASED_TYPE,
            StreamEvent.subject_kind.notin_(_NEVER_ERASED),
        )
    )
    return [
        row.seq
        for row in rows
        if restate.contains(
            [
                *_typed(row.old_value),
                *_typed(row.new_value),
                *_typed(row.payload),
                row.note or "",
            ],
            texts,
        )
    ]


async def _audit(
    session: AsyncSession, patch: dict[str, Any], *, assignment_id: UUID
) -> None:
    # What the row holds now; what it held is the text that went. The stream
    # fills in the actor when it flushes, so the flush is inside the scope.
    await session.flush()
    with context.scope(correlation_id=context.current().correlation_id, job=JOB):
        record_audit(
            session,
            actor=None,
            action=UPDATE,
            entity=patch["table"],
            entity_id=patch["id"],
            new_value={
                _AUDIT_KEYS.get((patch["table"], column), column): value
                for column, value in patch["values"].items()
            },
            assignment_id=assignment_id,
        )
        await session.flush()


async def restate_moment(
    session: AsyncSession,
    assignment_id: UUID,
    seq: int,
    keys: Sequence[str],
    *,
    actor: Person | None,
) -> Restated:
    """Take the chosen typed texts out of one moment, and out of its case.

    ``keys`` name texts of the moment (``grip.chronicle.restate.TYPED_TEXTS``).
    A closed dossier is no obstacle: the text should never have been there.
    """
    # One act at a time on the stream: what is read below is what is restated.
    await stream.hold_head(session)
    if await session.get(Assignment, assignment_id, populate_existing=True) is None:
        raise NotFoundError("Opdracht", assignment_id)
    recorded = await ChronicleRepository(session).recorded(assignment_id)
    moment = moment_of(restate.substituted(recorded), seq)
    offered = {
        text.key: value for text, value in restate.removable(moment.fact, moment.fields)
    }
    if not keys:
        raise DomainValidationError("Kies de tekst die je wilt verwijderen.")
    for key in keys:
        if key not in offered:
            label = restate.BY_KEY[key].label.lower() if key in restate.BY_KEY else key
            raise DomainValidationError(f"Dit moment heeft geen tekst bij {label}.")
    texts = restate.wanted(offered[key] for key in keys)
    planned = restate.plan(recorded, texts, assignment_id=str(assignment_id))
    seqs = []
    for _holder, fields in planned:
        established = await establish(
            session,
            restate.RESTATED,
            assignment_id=assignment_id,
            actor=actor,
            fields=fields,
        )
        seqs.append(established.event.seq)
        for patch in fields["patches"]:
            await _audit(session, patch, assignment_id=assignment_id)
    others = await _holding(session, assignment_id, texts)
    erased = await retention.erase_events(
        session,
        [holder.seq for holder, _fields in planned] + others,
        reason=REASON,
        about={"assignment_id": str(assignment_id), "restated_by": seqs},
    )
    contents = await quote_contents(session, assignment_id)
    return Restated(seqs=seqs, kept=kept(contents, texts), erased=erased)
