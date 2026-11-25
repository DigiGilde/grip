"""How a case stood at a moment: the fold of its chronicle, read as the screens do.

The rows of the case come from the fold. What lies outside the chronicle (the
rate book, the settings, who was on a line) is cut at the end of the act of the
moment. No rule is written here: the facts of a case, the course, the prices
and the state of a quote come from the modules that hold them for the live
screens, over rows that say what the chronicle says.

Known limits: names of persons and organisations, and whether the client is
this instance itself, are read as they are now; an approver whose grant was
deleted later no longer counts, and whether someone may approve their own
request is the setting of now; a pricing error that follows from who is staffed
on a line is not known here.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.chronicle import restate, words
from grip.chronicle.facts import (
    ACCEPTANCE,
    APPROVAL,
    ASSIGNMENT,
    DECRETOGRAM,
    FACTS,
    INVITATION,
    LINE,
    OFFER,
    QUOTE,
    REJECTION,
    ROLE,
    title_of,
)
from grip.chronicle.ledger import Gram, Ledger, diff, fold
from grip.chronicle.rates import NO_CARDS, rate_book_from
from grip.chronicle.writer import MODELS, columns_of, default_of, typed
from grip.core import clock
from grip.core.audit import DELETE
from grip.models.assignment import ROLE_OWNER, line_display_name
from grip.models.quote import APPROVAL_WITHDRAWN, QuoteApproval
from grip.repositories.chronicle import ChronicleRepository
from grip.schema.chronicle import (
    LaterKnownOut,
    MomentOut,
    MomentsOut,
    RemovableTextOut,
    RestatementOut,
    StandAcceptanceOut,
    StandApprovalOut,
    StandAssignmentOut,
    StandBudgetOut,
    StandInvitationOut,
    StandLineOut,
    StandOfferOut,
    StandOut,
    StandQuoteOut,
    StandRejectionOut,
)
from grip.schema.quotes import content_from_snapshot
from grip.schema.tasks import CourseOut, course_out
from grip.services import (
    assignment_views,
    assignments,
    periods,
    pricing,
    quote_approval,
    quote_budget,
    quote_channels,
    quote_views,
    quotes,
    restatements,
)
from grip.services.canonical import read
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.phase import STATUS_LABELS
from grip.services.quote_content import line_source
from grip.tasks import course, engine
from grip.tasks.cases import (
    AssignmentInputs,
    assignment_snapshot,
    is_client_of,
    quote_open,
)
from grip.tasks.plan import plan_for

# The words of the quote screens (frontend/src/features/quotes/api.ts).
QUOTE_STATUS_LABELS = {
    "issued": "Offerte gemaakt",
    "accepted": "Akkoord",
    "rejected": "Afgewezen",
    "superseded": "Vervangen",
}
_UNKNOWN_STATUS = "Onbekend"
_HANGS_FROM_A_QUOTE = (INVITATION, OFFER, APPROVAL, ACCEPTANCE, REJECTION)
_RATES_CHANGED = "De tarieven zijn gewijzigd."


@dataclass(frozen=True)
class Reader:
    """What the route decided about who reads this."""

    # Runs the assignment: the address a signing link went to is theirs to know.
    manages: bool
    # May take a typed text out of a moment (ADR 0057).
    restates: bool = False


def _row(table: str, values: Mapping[str, Any]) -> SimpleNamespace:
    """A row of the fold in the Python types of its columns.

    A fact from before a column existed says nothing about it: the column holds
    what it holds when nothing was said.
    """
    model = MODELS[table]
    return SimpleNamespace(
        **{
            key: typed(
                model, key, values[key] if key in values else default_of(model, key)
            )
            for key in columns_of(model)
        }
    )


def _day_of(gram: Gram) -> date:
    if gram.recorded_on:
        return date.fromisoformat(gram.recorded_on)
    return clock.local_date(gram.occurred_at)


def _lines(ledger: Ledger) -> list[SimpleNamespace]:
    lines = []
    for values in ledger.table(LINE).values():
        line = _row(LINE, values)
        line.description = line_display_name(line.role, line.detail)
        lines.append(line)
    return sorted(lines, key=lambda line: (line.position, line.id))


def _quotes(ledger: Ledger) -> list[SimpleNamespace]:
    """Oldest first. The fold holds quotes in the order they were made."""
    found = []
    for values in ledger.table(QUOTE).values():
        quote = _row(QUOTE, values)
        quote.snapshot = read(quote.canonical)
        found.append(quote)
    return sorted(found, key=lambda quote: quote.issued_at)


def _rows_by_quote(ledger: Ledger, table: str) -> dict[UUID, list[SimpleNamespace]]:
    grouped: dict[UUID, list[SimpleNamespace]] = defaultdict(list)
    for values in ledger.table(table).values():
        row = _row(table, values)
        grouped[row.quote_id].append(row)
    return grouped


def _moment_values(gram: Gram, reader: Reader) -> Mapping[str, Any] | None:
    """The fields of a fact as this reader may hear them in words."""
    fields = gram.fields
    if (
        fields is None
        or reader.manages
        or gram.fact != "quote_offered"
        or fields["offer"].get("channel") != quote_channels.OFFER_SIGNING_LINK
    ):
        return fields
    return {**fields, "offer": {**fields["offer"], "recipient": None}}


def _statement(gram: Gram, reader: Reader, names: Mapping[UUID, str]) -> str:
    actor = names.get(gram.actor_person_id)
    return words.statement(gram.fact, _moment_values(gram, reader), actor=actor)


def _effective_on(gram: Gram) -> date | None:
    return date.fromisoformat(gram.effective_on) if gram.effective_on else None


def _moment(gram: Gram, reader: Reader, names: Mapping[UUID, str]) -> MomentOut:
    return MomentOut(
        seq=gram.seq,
        occurred_at=gram.occurred_at,
        fact=gram.fact,
        title=title_of(gram.fact, gram.fields),
        decision=gram.kind == DECRETOGRAM,
        actor_name=names.get(gram.actor_person_id),
        actor_kind=gram.actor_kind,
        effective_on=_effective_on(gram),
        statement=_statement(gram, reader, names),
        lines=list(words.lines(gram.fact, gram.fields)),
        erased=gram.erased,
    )


def _moments_of(grams: Iterable[Gram]) -> list[Gram]:
    return [gram for gram in grams if FACTS[gram.fact].moment]


async def _actors(session: AsyncSession, grams: Iterable[Gram]) -> dict[UUID, str]:
    return await quote_views.person_names(
        session, {gram.actor_person_id for gram in grams if gram.actor_person_id}
    )


async def moments(
    session: AsyncSession, assignment_id: UUID, reader: Reader
) -> MomentsOut:
    """The moments of an assignment, oldest first."""
    await assignments.get_assignment(session, assignment_id)
    grams = _moments_of(await ChronicleRepository(session).grams(assignment_id))
    names = await _actors(session, grams)
    return MomentsOut(items=[_moment(gram, reader, names) for gram in grams])


# -- what lies outside the chronicle, at a cut ----------------------------------


@dataclass(frozen=True)
class _Outside:
    """The world around a case at the end of the act of one moment."""

    cut: int
    rates: calc.RateBook
    mode: str
    threshold: int
    # The fact that held the book at this cut was erased: what priced is unknown.
    book_erased: bool


def _setting_at(rows: Sequence[Any], key: str, default: Any, cut: int) -> Any:
    value = default
    for row in rows:
        if row.seq > cut:
            break
        # An erased row holds no values.
        if key in (row.new_value or {}):
            value = row.new_value[key]
    return value


def _outside_at(
    rate_grams: Sequence[Gram], setting_rows: Sequence[Any], cut: int
) -> _Outside:
    book = None
    book_erased = False
    for gram in rate_grams:
        if gram.seq > cut:
            break
        if gram.fields is None:
            book_erased = True
        else:
            book, book_erased = gram.fields["book"], False
    return _Outside(
        cut=cut,
        rates=rate_book_from(book or NO_CARDS),
        mode=_setting_at(
            setting_rows, quote_approval.MODE.key, quote_approval.MODE.default, cut
        ),
        threshold=int(
            _setting_at(
                setting_rows,
                quote_approval.THRESHOLD.key,
                quote_approval.THRESHOLD.default,
                cut,
            )
        ),
        book_erased=book_erased,
    )


def _allocations(
    rows: Sequence[Any], lines: Sequence[SimpleNamespace]
) -> tuple[dict[UUID, list[SimpleNamespace]], bool]:
    """Who is on which line, from the change records up to the cut.

    An allocation that follows its line has the dates of the line at this
    moment: a moved line moves them without a record of its own.
    """
    alive: dict[str, dict[str, Any]] = {}
    erased = False
    for row in rows:
        if row.erased_at is not None:
            erased = True
        elif row.action == DELETE:
            alive.pop(row.subject_id, None)
        else:
            alive.setdefault(row.subject_id, {}).update(row.new_value or {})
    by_id = {str(line.id): line for line in lines}
    grouped: dict[UUID, list[SimpleNamespace]] = defaultdict(list)
    for values in alive.values():
        line = by_id.get(str(values.get("budget_line_id")))
        if line is None:
            continue
        follows = values.get("period_source") == periods.FOLLOWS_LINE
        start = line.start_date if follows else _a_date(values.get("start_date"))
        end = line.end_date if follows else _a_date(values.get("end_date"))
        if start is None or end is None:
            continue
        grouped[line.id].append(
            SimpleNamespace(
                start_date=start,
                end_date=end,
                fte_pct=Decimal(str(values.get("fte_pct", 0))),
            )
        )
    return grouped, erased


def _a_date(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


# -- the course ----------------------------------------------------------------


def _budget_moved(
    lines: Sequence[SimpleNamespace],
    own_quotes: Sequence[SimpleNamespace],
    rates: calc.RateBook,
) -> bool:
    in_force = [
        quote for quote in own_quotes if quote.status in quote_budget.COMPARED_STATUSES
    ]
    if not in_force or not lines:
        return False
    quote = max(in_force, key=lambda item: (item.issued_at, item.id))
    try:
        current = quotes.budget_part(
            [line_source(cast(Any, line)) for line in lines],
            rates,
            pricing.DEFAULT_OPTIONS,
        )
    except (calc.CalcError, DomainValidationError):
        return False
    return quote_budget.budget_fingerprint(current) != quote_budget.budget_fingerprint(
        quote.snapshot
    )


async def _approval_state(
    session: AsyncSession,
    quote: SimpleNamespace,
    history: Sequence[SimpleNamespace],
    outside: _Outside,
    *,
    offered: bool,
    today: date,
) -> quote_approval.ApprovalState:
    ordered = sorted(history, key=lambda row: row.requested_at)
    current = quote_approval.current_request(ordered, quote.snapshot_hash)
    return quote_approval.ApprovalState(
        requirement=quote_approval.requirement_from(
            outside.mode, outside.threshold, quote.total_cents
        ),
        current=cast(QuoteApproval | None, current),
        history=tuple(cast(Sequence[QuoteApproval], ordered)),
        approver_available=await quote_approval.approver_available(
            session,
            excluding=await quote_approval.second_person_excluded(
                session, cast(Any, current), cast(Any, quote)
            ),
            on=today,
        ),
        offered=offered,
        quote_hash=quote.snapshot_hash,
    )


async def _course(
    session: AsyncSession,
    repository: ChronicleRepository,
    row: SimpleNamespace,
    gram: Gram,
    ledger: Ledger,
    outside: _Outside,
    *,
    instance_base_uri: str,
) -> tuple[CourseOut | None, bool]:
    """The course of the case at this moment, and whether an input was erased."""
    today = _day_of(gram)
    lines = _lines(ledger)
    own_quotes = _quotes(ledger)
    client = (
        await repository.organisation(row.client_organisation_id)
        if row.client_organisation_id
        else None
    )
    is_client = is_client_of(client.instance_uri if client else None, instance_base_uri)
    offered = {
        quote_id for quote_id, offers in _rows_by_quote(ledger, OFFER).items() if offers
    }
    requests = _rows_by_quote(ledger, APPROVAL)
    references = {quote.id: quote.reference for quote in own_quotes}
    approvals = [
        SimpleNamespace(**vars(request), reference=references.get(quote_id))
        for quote_id, history in requests.items()
        for request in history
        if request.status != APPROVAL_WITHDRAWN
    ]
    open_quote = quote_open(own_quotes)
    approval = (
        await _approval_state(
            session,
            open_quote,
            requests.get(open_quote.id, []),
            outside,
            offered=open_quote.id in offered,
            today=today,
        )
        if open_quote is not None and not is_client
        else None
    )
    allocations, erased = _allocations(
        await repository.changes_of_kind(
            "allocation", outside.cut, assignment_id=row.id
        ),
        lines,
    )
    reported = await repository.changes_of_kind(
        "final_report", outside.cut, subject_id=str(row.id)
    )
    snapshot = assignment_snapshot(
        AssignmentInputs(
            id=row.id,
            kind=row.kind,
            status=row.status,
            is_client=is_client,
            lines=lines,
            role_allocations=allocations,
            quotes=own_quotes,
            approvals=approvals,
            offered=offered,
            approval=approval,
            valid_until=open_quote.snapshot.get("valid_until") if open_quote else None,
            budget_moved=not outside.book_erased
            and _budget_moved(lines, own_quotes, outside.rates),
            final_report_issued=bool(reported),
            dossier_closed=row.dossier_closed_on is not None,
        ),
        today=today,
    )
    plan = plan_for(gram.plan_version)
    views = course.at_moment(snapshot, plan, engine.asked_for(snapshot, plan))
    own = next((view for view in views if view.subject == "case"), None)
    return (course_out(own) if own else None), erased


# -- the budget ----------------------------------------------------------------


def _priced(
    assignment_id: UUID, lines: Sequence[SimpleNamespace], rates: calc.RateBook
) -> assignment_views.PricedLines:
    calc_lines = tuple(pricing.to_calc_line(cast(Any, line)) for line in lines)
    return assignment_views.price_lines(
        assignment_id,
        cast(Any, lines),
        replace(pricing.no_inputs(rates), lines=calc_lines),
        None,
        pricing.DEFAULT_OPTIONS,
    )


def _total(priced: assignment_views.PricedLines) -> int | None:
    return (
        sum(priced.budgeted_by_year.values()) if priced.pricing_error is None else None
    )


def _budget(
    assignment_id: UUID,
    ledger: Ledger,
    before: Ledger | None,
    rates: calc.RateBook,
    previous_rates: calc.RateBook | None,
) -> StandBudgetOut:
    lines = _lines(ledger)
    priced = _priced(assignment_id, lines, rates)
    changes = {
        change.id: change.change
        for change in diff(before or Ledger(), ledger)
        if change.table == LINE
    }
    total = _total(priced)
    previous_total = None
    if before is not None and previous_rates is not None:
        previous_total = _total(_priced(assignment_id, _lines(before), previous_rates))
    out = []
    for line, item in zip(lines, priced.lines, strict=True):
        change = changes.get(str(line.id))
        out.append(
            StandLineOut(
                id=line.id,
                description=line.description,
                kind=line.kind,
                position=line.position,
                role=line.role,
                fte=line.fte,
                start_date=line.start_date,
                end_date=line.end_date,
                rate_category=line.rate_category,
                amount_cents=line.amount_cents,
                year=line.year,
                budgeted_cents=sum(item.budgeted_by_year.values())
                if not item.pricing_error
                else None,
                change="added"
                if change == "added"
                else "changed"
                if change == "changed"
                else None,
            )
        )
    removed = [
        line_display_name(row.get("role"), row.get("detail"))
        for row_id, row in (before or Ledger()).table(LINE).items()
        if changes.get(row_id) == "removed"
    ]
    return StandBudgetOut(
        lines=out,
        removed=removed,
        subtotals_by_year={str(y): c for y, c in priced.budgeted_by_year.items()},
        total_budgeted_cents=total,
        previous_total_cents=previous_total if previous_total != total else None,
        pricing_error=priced.pricing_error,
    )


def _without_amounts(budget: StandBudgetOut) -> StandBudgetOut:
    """On half a story, or without the book of that moment, an amount says more
    than is known."""
    return budget.model_copy(
        update={
            "lines": [
                line.model_copy(update={"budgeted_cents": None})
                for line in budget.lines
            ],
            "subtotals_by_year": {},
            "total_budgeted_cents": None,
            "previous_total_cents": None,
            "pricing_error": None,
        }
    )


# -- the quotes ----------------------------------------------------------------


def _changed_quotes(before: Ledger | None, ledger: Ledger) -> set[str]:
    earlier = before or Ledger()
    changed: set[str] = set()
    for change in diff(earlier, ledger):
        if change.table == QUOTE:
            changed.add(change.id)
        elif change.table in _HANGS_FROM_A_QUOTE:
            # A changed row holds only the columns that differ.
            row = ledger.table(change.table).get(change.id) or earlier.table(
                change.table
            ).get(change.id)
            changed.add(str(cast(Mapping[str, Any], row)["quote_id"]))
    return changed


def _people_named(
    own_quotes: Sequence[SimpleNamespace],
    approvals: Mapping[UUID, Sequence[SimpleNamespace]],
    offers: Mapping[UUID, Sequence[SimpleNamespace]],
    acceptances: Mapping[UUID, Sequence[SimpleNamespace]],
    rejections: Mapping[UUID, Sequence[SimpleNamespace]],
) -> set[UUID]:
    people: set[UUID] = set()
    for quote in own_quotes:
        for row in approvals.get(quote.id, []):
            people.update({row.requested_by_id, row.decided_by_id, row.withdrawn_by_id})
        for row in offers.get(quote.id, []):
            people.add(row.offered_by_id)
        for row in (*acceptances.get(quote.id, []), *rejections.get(quote.id, [])):
            people.add(row.recorded_by_id)
    return {person for person in people if person is not None}


def _quote_out(
    quote: SimpleNamespace,
    *,
    approvals: Sequence[SimpleNamespace],
    offers: Sequence[SimpleNamespace],
    invitations: Mapping[UUID, SimpleNamespace],
    acceptance: SimpleNamespace | None,
    rejection: SimpleNamespace | None,
    changed: bool,
    names: Mapping[UUID, str],
    reader: Reader,
    at: datetime,
) -> StandQuoteOut:
    def recipient_of(offer: SimpleNamespace) -> str | None:
        if offer.channel == quote_channels.OFFER_SIGNING_LINK and not reader.manages:
            return None
        return cast(str | None, offer.recipient)

    def invitation_of(offer: SimpleNamespace) -> StandInvitationOut | None:
        invitation = invitations.get(offer.invitation_id)
        if invitation is None or not reader.manages:
            return None
        return StandInvitationOut(
            state=quote_views.invitation_state(invitation, at),
            expires_at=invitation.expires_at,
            opened_at=invitation.opened_at,
            used_at=invitation.used_at,
            withdrawn_at=invitation.withdrawn_at,
        )

    return StandQuoteOut(
        id=quote.id,
        reference=quote.reference,
        status=quote.status,
        status_label=QUOTE_STATUS_LABELS.get(quote.status, quote.status),
        changed=changed,
        total_cents=quote.total_cents,
        valid_until=quote.snapshot.get("valid_until"),
        issued_at=quote.issued_at,
        snapshot_hash=quote.snapshot_hash,
        document_sha256=quote.document_sha256,
        has_document=quote.document_ref is not None,
        approvals=[
            StandApprovalOut(
                status=row.status,
                requested_by_name=names.get(row.requested_by_id),
                requested_at=row.requested_at,
                decided_by_name=names.get(row.decided_by_id),
                decided_at=row.decided_at,
                withdrawn_by_name=names.get(row.withdrawn_by_id),
                withdrawn_at=row.withdrawn_at,
                request_note=row.request_note,
                decision_note=row.decision_note,
                self_approved=row.self_approved,
            )
            for row in sorted(approvals, key=lambda item: item.requested_at)
        ],
        offers=[
            StandOfferOut(
                channel=row.channel,
                recipient=recipient_of(row),
                offered_at=row.offered_at,
                offered_by_name=names.get(row.offered_by_id),
                invitation=invitation_of(row),
            )
            for row in sorted(offers, key=lambda item: item.offered_at)
        ],
        acceptance=StandAcceptanceOut(
            signer_name=acceptance.signer_name,
            form=acceptance.form,
            signed_at=acceptance.signed_at,
            organisation_name=(acceptance.organisation or {}).get("name"),
            recorded_by_name=names.get(acceptance.recorded_by_id),
        )
        if acceptance is not None
        else None,
        rejection=StandRejectionOut(
            reason=rejection.reason,
            rejected_at=rejection.rejected_at,
            recorded_by_name=names.get(rejection.recorded_by_id),
        )
        if rejection is not None
        else None,
        content=content_from_snapshot(quote.snapshot),
    )


async def _quotes_out(
    session: AsyncSession,
    ledger: Ledger,
    before: Ledger | None,
    reader: Reader,
    at: datetime,
) -> list[StandQuoteOut]:
    """Newest first, as the live list."""
    own_quotes = _quotes(ledger)
    approvals = _rows_by_quote(ledger, APPROVAL)
    offers = _rows_by_quote(ledger, OFFER)
    invitations = {
        UUID(row_id): _row(INVITATION, values)
        for row_id, values in ledger.table(INVITATION).items()
    }
    acceptances = _rows_by_quote(ledger, ACCEPTANCE)
    rejections = _rows_by_quote(ledger, REJECTION)
    names = await quote_views.person_names(
        session, _people_named(own_quotes, approvals, offers, acceptances, rejections)
    )
    changed = _changed_quotes(before, ledger)
    return [
        _quote_out(
            quote,
            approvals=approvals.get(quote.id, []),
            offers=offers.get(quote.id, []),
            invitations=invitations,
            acceptance=next(iter(acceptances.get(quote.id, [])), None),
            rejection=next(iter(rejections.get(quote.id, [])), None),
            changed=str(quote.id) in changed,
            names=names,
            reader=reader,
            at=at,
        )
        for quote in reversed(own_quotes)
    ]


# -- around the moment ----------------------------------------------------------


def _approval_words(mode: str, threshold: int) -> tuple[str, str]:
    """The change of the rule without a value, and with it."""
    if mode == quote_approval.MODE_FROM_AMOUNT:
        return (
            "Interne goedkeuring is nu nodig vanaf een bedrag.",
            f"Interne goedkeuring is nu nodig vanaf {words.euro_words(threshold)}.",
        )
    said = (
        "Interne goedkeuring is nu nodig voor elke offerte."
        if mode == quote_approval.MODE_ALWAYS
        else "Interne goedkeuring is nu niet meer nodig."
    )
    return said, said


def _approval_rule(outside: _Outside) -> tuple[str, int]:
    """What counts of the setting: a threshold says nothing in another mode."""
    threshold = (
        outside.threshold if outside.mode == quote_approval.MODE_FROM_AMOUNT else 0
    )
    return outside.mode, threshold


def _expired_between(
    before: Ledger | None, previous_day: date | None, day: date
) -> tuple[str, str] | None:
    """That the open quote expired since the previous moment, without its day and
    with it."""
    if before is None or previous_day is None:
        return None
    quote = quote_open(_quotes(before))
    valid_until = quote.snapshot.get("valid_until") if quote is not None else None
    if not valid_until or not previous_day.isoformat() <= valid_until < day.isoformat():
        return None
    return (
        "De offerte is verlopen.",
        f"De offerte is verlopen op {words.day_words(valid_until)}.",
    )


def _outside_words(
    rate_grams: Sequence[Gram],
    previous: _Outside | None,
    outside: _Outside,
    expired: tuple[str, str] | None,
) -> tuple[list[str], list[str]]:
    """What changed around the case: without a value, and with the values."""
    if previous is None:
        return [], []
    rate_facts = [gram for gram in rate_grams if previous.cut < gram.seq <= outside.cut]
    causes = [
        f"{gram.fields['cause']}." for gram in rate_facts if gram.fields is not None
    ]
    rates_changed = [_RATES_CHANGED] if rate_facts else []
    told: list[tuple[str, str]] = []
    if _approval_rule(previous) != _approval_rule(outside):
        told.append(_approval_words(outside.mode, outside.threshold))
    if expired:
        told.append(expired)
    return (
        [*rates_changed, *(without for without, _ in told)],
        [*(causes or rates_changed), *(valued for _, valued in told)],
    )


def _corrects_a_day_seen(later: Gram, day: date) -> bool:
    """A correction stands next to what it corrects, wherever the new date falls."""
    was = (later.fields or {}).get("was")
    if later.fact != "acceptance_date_corrected" or not was:
        return False
    return clock.local_date(datetime.fromisoformat(was)) <= day


def _later_known(
    grams: Sequence[Gram], gram: Gram, reader: Reader, names: Mapping[UUID, str]
) -> list[LaterKnownOut]:
    """Facts recorded later that count from a day this moment had already seen.

    A fact that counts from the day it was recorded came to be known when it
    happened, whatever else that day held.
    """
    day = _day_of(gram)
    found = []
    for later in grams:
        counts_from = _effective_on(later)
        if (
            later.seq > gram.seq
            and counts_from is not None
            and (
                (counts_from <= day and counts_from < _day_of(later))
                or _corrects_a_day_seen(later, day)
            )
        ):
            found.append(
                LaterKnownOut(
                    seq=later.seq,
                    title=title_of(later.fact, later.fields),
                    statement=_statement(later, reader, names),
                    effective_on=counts_from,
                )
            )
    return found


def _restatements(grams: Sequence[Gram], gram: Gram) -> list[RestatementOut]:
    """The moments that later took a typed text out of this one, oldest first."""
    by_seq = {item.seq: item for item in grams}
    found = []
    for seq in gram.restated_by:
        herstel = by_seq.get(seq)
        if herstel is None:
            continue
        removed = (herstel.fields or {}).get("removed") or ()
        found.append(
            RestatementOut(
                seq=seq,
                occurred_at=herstel.occurred_at,
                removed=list(dict.fromkeys(item["label"] for item in removed)),
            )
        )
    return found


async def _removable(
    session: AsyncSession, assignment_id: UUID, gram: Gram
) -> list[RemovableTextOut]:
    """The typed texts of this moment that can be taken out, and the quotes that
    keep them all the same."""
    found = restate.removable(gram.fact, gram.fields)
    if not found:
        return []
    contents = await restatements.quote_contents(session, assignment_id)
    return [
        RemovableTextOut(
            key=text.key,
            label=text.label,
            text=value,
            kept=restatements.kept(contents, restate.wanted([value])),
        )
        for text, value in found
    ]


async def _assignment_out(
    session: AsyncSession,
    repository: ChronicleRepository,
    assignment_id: UUID,
    ledger: Ledger,
) -> tuple[StandAssignmentOut, SimpleNamespace | None]:
    values = ledger.table(ASSIGNMENT).get(str(assignment_id))
    if values is None:
        # The fact that made the case was erased: only that it exists is known.
        live = await assignments.get_assignment(session, assignment_id)
        return (
            StandAssignmentOut(
                name=live.name,
                status="",
                status_label=_UNKNOWN_STATUS,
                kind=live.kind,
            ),
            None,
        )
    row = _row(ASSIGNMENT, values)
    owner = next(
        (
            role["person_id"]
            for role in ledger.table(ROLE).values()
            if role["role"] == ROLE_OWNER
        ),
        None,
    )
    names = await quote_views.person_names(session, {UUID(owner)} if owner else set())
    client = (
        await repository.organisation(row.client_organisation_id)
        if row.client_organisation_id
        else None
    )
    return (
        StandAssignmentOut(
            name=row.name,
            status=row.status,
            status_label=STATUS_LABELS.get(row.status, row.status),
            kind=row.kind,
            owner_name=names.get(UUID(owner)) if owner else None,
            client_name=client.name if client is not None else None,
            start_date=row.start_date,
            end_date=row.end_date,
            notes=row.notes,
            quote_date=row.quote_date,
            verbal_agreement_note=row.verbal_agreement_note,
            quoted_amount_cents=row.quoted_amount_cents,
        ),
        row,
    )


async def stand(
    session: AsyncSession,
    assignment_id: UUID,
    seq: int,
    reader: Reader,
    *,
    instance_base_uri: str,
) -> StandOut:
    """How the assignment stood at one of its moments."""
    repository = ChronicleRepository(session)
    grams = await repository.grams(assignment_id)
    shown = _moments_of(grams)
    index = next((i for i, gram in enumerate(shown) if gram.seq == seq), None)
    if index is None:
        raise NotFoundError("Moment", seq)
    gram = shown[index]
    previous = shown[index - 1] if index > 0 else None
    following = shown[index + 1] if index + 1 < len(shown) else None
    ledger = fold(grams, upto=seq)
    before = fold(grams, upto=previous.seq) if previous is not None else None

    rate_grams = await repository.rate_grams()
    cut = await _act_end(repository, grams, gram)
    setting_rows = await repository.changes_of_kind("instance_setting", cut)
    outside = _outside_at(rate_grams, setting_rows, cut)
    previous_outside = (
        _outside_at(
            rate_grams, setting_rows, await _act_end(repository, grams, previous)
        )
        if previous is not None
        else None
    )
    names = await _actors(session, shown)
    assignment, row = await _assignment_out(session, repository, assignment_id, ledger)
    incomplete = bool(ledger.erased) or row is None
    course_at: CourseOut | None = None
    if row is not None and not incomplete:
        course_at, inputs_erased = await _course(
            session,
            repository,
            row,
            gram,
            ledger,
            outside,
            instance_base_uri=instance_base_uri,
        )
        if inputs_erased:
            course_at, incomplete = None, True
    budget = _budget(
        assignment_id,
        ledger,
        before,
        outside.rates,
        previous_outside.rates
        if previous_outside is not None and not previous_outside.book_erased
        else None,
    )
    if incomplete or outside.book_erased:
        budget = _without_amounts(budget)
    if incomplete:
        assignment = assignment.model_copy(
            update={"status": "", "status_label": _UNKNOWN_STATUS}
        )
    expired = _expired_between(
        before,
        _day_of(previous) if previous is not None else None,
        _day_of(gram),
    )
    around, around_values = _outside_words(
        rate_grams, previous_outside, outside, expired
    )
    return StandOut(
        moment=_moment(gram, reader, names),
        previous_seq=previous.seq if previous is not None else None,
        next_seq=following.seq if following is not None else None,
        assignment=assignment,
        course=course_at,
        outside=around,
        outside_values=around_values,
        later_known=_later_known(shown, gram, reader, names),
        restated=_restatements(grams, gram),
        budget=budget,
        quotes=await _quotes_out(session, ledger, before, reader, gram.occurred_at),
        incomplete=incomplete,
        removable_texts=await _removable(session, assignment_id, gram)
        if reader.restates
        else None,
    )


async def _act_end(
    repository: ChronicleRepository, grams: Sequence[Gram], gram: Gram
) -> int:
    following = next((item.seq for item in grams if item.seq > gram.seq), None)
    return await repository.act_end(
        gram.seq, gram.correlation_id, gram.occurred_at, following
    )
