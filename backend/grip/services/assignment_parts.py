"""The rows of an opened assignment: which there are, and what each one reports.

A row reports, it does not repeat the figures of the head. Two steps keep every
sentence inside its data class: ``load_facts`` reads only the facts of the
classes the reader may read, and ``parts_of``, a pure function, asks the classes
again before it writes a sentence. Whatever the loader did, a sentence of a
class that is not permitted cannot come out.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence, Set
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access.types import DataClass
from grip.core import clock
from grip.models.assignment import Assignment, BudgetLine
from grip.models.month_close import MonthClose
from grip.models.quote import Quote
from grip.repositories.domain import AssignmentRepository, MonthCloseRepository
from grip.services import (
    assignment_finance,
    billing_deliveries,
    quote_approval,
    quote_views,
    quotes,
    staffing_board,
)
from grip.services import assignment_views as views
from grip.services.client_side import own_organisation_ids
from grip.services.overview_attention import correction_due
from grip.services.phase import (
    Phase,
    allows_billing,
    allows_month_close,
    phase_of,
)
from grip.services.pricing import to_calc_allocation
from grip.services.reports.assignment_report import final_report
from grip.services.reports.labels import day

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING
ROSTER = DataClass.STAFFING_ROSTER
SIGNAL = DataClass.RATE_MISMATCH_SIGNAL

# The classes of which one gives a reader the row, whatever the facts say.
PART_NEEDS: dict[str, tuple[DataClass, ...]] = {
    "close": (B, C),
    "budget": (B,),
    "quote": (B,),
    "team": (C, ROSTER),
    "report": (B,),
}
# The row a destination of a task leads to. The others are the landing or a
# page of their own: assignment.overview, quote.approval, received.quote.
PART_OF_DESTINATION = {
    "assignment.budget": "budget",
    "assignment.quote": "quote",
    "assignment.staffing": "team",
    "assignment.month": "close",
    "assignment.period": "close",
    "assignment.invoice": "close",
    "assignment.report": "report",
}


def reads_part(key: str, classes: Set[DataClass]) -> bool:
    return any(data_class in classes for data_class in PART_NEEDS[key])


EXTERNAL = "external"
_REPORTED = frozenset({"completed", "accounted"})


# -- the facts ----------------------------------------------------------------


@dataclass(frozen=True)
class MonthFacts:
    """Class B or C: a count, without who worked or what it cost."""

    overdue: int = 0
    any_closed: bool = False


@dataclass(frozen=True)
class BudgetFacts:
    """Class B."""

    lines: int = 0
    over_budget: int = 0
    not_priced: int = 0


class QuoteStand(StrEnum):
    NONE = "none"
    MADE = "made"
    AWAITING_APPROVAL = "awaiting_approval"
    SENT_BACK = "sent_back"
    OFFERED = "offered"
    VERBAL = "verbal"
    SIGNED = "signed"
    REJECTED = "rejected"
    # This instance is the client: the quote came in from the contractor.
    RECEIVED = "received"


@dataclass(frozen=True)
class QuoteFacts:
    """Class B."""

    stand: QuoteStand
    on: date | None = None


@dataclass(frozen=True)
class BillingFacts:
    """Class B: the one billing step that is next."""

    kind: Literal["deliver", "record_invoice", "correction"]
    period: str | None = None


@dataclass(frozen=True)
class PartsFacts:
    """What the rows are made from. A fact of a class that was not permitted
    keeps its default."""

    # Class A.
    kind: str
    status: str
    owner_name: str | None = None
    # This instance is the client. Months, budget, team and report are the
    # contractor's work and are in the other instance.
    is_client: bool = False
    # Class B or C.
    months: MonthFacts | None = None
    # Class B.
    budget: BudgetFacts | None = None
    quote: QuoteFacts | None = None
    billing: BillingFacts | None = None
    report_issued: bool | None = None
    # Class C or its roster.
    has_personnel_line: bool = False
    # Class C.
    open_roles: int | None = None
    # The R14 signal: how many people, never which category.
    other_scale: int | None = None


@dataclass(frozen=True)
class Part:
    key: str
    label: str
    notice: str | None = None


# -- the sentences ------------------------------------------------------------


def _count(number: int, one: str, many: str) -> str:
    return f"{number} {one if number == 1 else many}"


def _sentence(pieces: Iterable[str | None]) -> str | None:
    said = ", ".join(piece for piece in pieces if piece)
    return said[:1].upper() + said[1:] if said else None


def _billing_words(billing: BillingFacts) -> str:
    if billing.kind == "correction":
        return "naverrekening aan te leveren"
    if billing.kind == "record_invoice":
        return f"factuur over {billing.period} vast te leggen"
    return f"{billing.period} aan te leveren"


def _close(facts: PartsFacts, classes: Set[DataClass]) -> Part | None:
    if facts.is_client or not reads_part("close", classes):
        return None
    months = facts.months or MonthFacts()
    # The same rule as the task to close a month: a task never leads to a part
    # without a row.
    if not allows_month_close(facts.status) and not months.any_closed:
        return None
    external = facts.kind == EXTERNAL
    pieces: list[str | None] = []
    if months.overdue and allows_month_close(facts.status):
        pieces.append(_count(months.overdue, "maand", "maanden") + " af te sluiten")
    if B in classes and external and facts.billing is not None:
        pieces.append(_billing_words(facts.billing))
    return Part(
        "close",
        "Afsluiten en factureren" if external and B in classes else "Afsluiten",
        _sentence(pieces),
    )


def _budget_notice(facts: PartsFacts) -> str | None:
    budget = facts.budget
    if budget is None or facts.status == "cancelled":
        return None
    if phase_of(facts.status) is Phase.POTENTIAL:
        if not budget.lines:
            return None
        count = _count(budget.lines, "regel", "regels")
        if budget.not_priced:
            return f"{count}, {budget.not_priced} kan niet worden berekend"
        return count
    pieces: list[str | None] = []
    if budget.over_budget:
        pieces.append(
            _count(budget.over_budget, "regel", "regels") + " over de begroting"
        )
    if budget.not_priced == 1:
        pieces.append("1 regel kan niet worden berekend")
    elif budget.not_priced:
        pieces.append(f"{budget.not_priced} regels kunnen niet worden berekend")
    return _sentence(pieces)


def _budget(facts: PartsFacts, classes: Set[DataClass]) -> Part | None:
    if facts.is_client or not reads_part("budget", classes):
        return None
    return Part("budget", "Begroting", _budget_notice(facts))


_QUOTE_WORDS = {
    QuoteStand.MADE: "Gemaakt, nog niet aangeboden",
    QuoteStand.AWAITING_APPROVAL: "Wacht op interne goedkeuring",
    QuoteStand.SENT_BACK: "Teruggestuurd bij de interne goedkeuring",
}
_QUOTE_WORDS_ON = {
    QuoteStand.OFFERED: "Bij de opdrachtgever sinds",
    QuoteStand.VERBAL: "Mondeling akkoord op",
    QuoteStand.SIGNED: "Getekend op",
    QuoteStand.REJECTED: "Afgewezen op",
    QuoteStand.RECEIVED: "Ontvangen op",
}


def _quote_notice(facts: PartsFacts) -> str | None:
    quote = facts.quote
    if quote is None:
        return None
    if quote.stand is QuoteStand.NONE:
        over = phase_of(facts.status) is Phase.CLOSED
        return None if over else "Nog geen offerte"
    if quote.stand in _QUOTE_WORDS:
        return _QUOTE_WORDS[quote.stand]
    words = _QUOTE_WORDS_ON[quote.stand]
    return f"{words} {day(quote.on)}" if quote.on else words.rsplit(" ", 1)[0]


def _quote(facts: PartsFacts, classes: Set[DataClass]) -> Part | None:
    if not reads_part("quote", classes):
        return None
    # The kind of an assignment can change after a quote; its tasks stay.
    has_quote = facts.quote is not None and facts.quote.stand is not QuoteStand.NONE
    if facts.kind != EXTERNAL and not has_quote:
        return None
    return Part("quote", "Offerte", _quote_notice(facts))


def _team(facts: PartsFacts, classes: Set[DataClass]) -> Part | None:
    if (
        facts.is_client
        or not reads_part("team", classes)
        or not facts.has_personnel_line
    ):
        return None
    pieces: list[str | None] = []
    if phase_of(facts.status) is not Phase.CLOSED:
        if C in classes and facts.open_roles:
            pieces.append(_count(facts.open_roles, "rol", "rollen") + " open")
        if SIGNAL in classes and facts.other_scale:
            pieces.append(
                _count(facts.other_scale, "persoon", "mensen") + " in een andere schaal"
            )
    return Part("team", "Team", _sentence(pieces))


def _report(facts: PartsFacts, classes: Set[DataClass]) -> Part | None:
    if facts.is_client or not reads_part("report", classes):
        return None
    if facts.status not in _REPORTED and not facts.report_issued:
        return None
    due = (
        facts.status in _REPORTED
        and facts.kind == EXTERNAL
        and facts.report_issued is False
    )
    return Part("report", "Eindrapport", "Nog niet opgeleverd" if due else None)


def _details(facts: PartsFacts) -> Part:
    return Part(
        "details",
        "Gegevens",
        f"Eigenaar {facts.owner_name}" if facts.owner_name else None,
    )


def parts_of(facts: PartsFacts, classes: Set[DataClass]) -> tuple[Part, ...]:
    """The rows for a reader of these classes, always in the same order."""
    if A not in classes:
        return ()
    rows = (
        _close(facts, classes),
        _budget(facts, classes),
        _quote(facts, classes),
        _team(facts, classes),
        _report(facts, classes),
        _details(facts),
        Part("history", "Geschiedenis"),
    )
    return tuple(row for row in rows if row is not None)


@dataclass(frozen=True)
class OwnInzet:
    role: str
    fte_pct: Decimal
    start_date: date
    end_date: date


def _percentage(value: Decimal) -> str:
    return f"{value.normalize():f}".replace(".", ",") + "%"


def own_line_of(inzet: Iterable[OwnInzet], today: date) -> str | None:
    """The reader's own inzet that has not ended, in one line."""
    lines = []
    for item in sorted(inzet, key=lambda i: (i.start_date, i.end_date, i.role)):
        if item.end_date < today:
            continue
        period = f"tot {day(item.end_date)}"
        if item.start_date > today:
            period = f"van {day(item.start_date)} {period}"
        lines.append(f"{item.role}, {_percentage(item.fte_pct)}, {period}")
    return "; ".join(lines) or None


# -- loading ------------------------------------------------------------------


def chosen_quote(quotes: Sequence[Quote]) -> Quote | None:
    """The quote the rows speak of, from the newest first: the accepted one,
    else the newest, and none when that one is superseded."""
    found = next((q for q in quotes if q.status == "accepted"), None)
    if found is None and quotes:
        found = quotes[0]
    return None if found is None or found.status == "superseded" else found


async def quote_facts(
    session: AsyncSession, assignment: Assignment, *, is_client: bool = False
) -> QuoteFacts:
    bundles = await quote_views.quotes_of_assignment(session, assignment.id)
    chosen = chosen_quote([b.quote for b in bundles])
    bundle = next((b for b in bundles if b.quote is chosen), None)
    if bundle is None:
        return QuoteFacts(QuoteStand.NONE)
    if bundle.quote.status == "accepted":
        signed = bundle.acceptance.signed_at if bundle.acceptance else None
        return QuoteFacts(
            QuoteStand.SIGNED, clock.local_date(signed) if signed else None
        )
    if bundle.quote.status == "rejected":
        rejected = bundle.rejection.rejected_at if bundle.rejection else None
        return QuoteFacts(
            QuoteStand.REJECTED, clock.local_date(rejected) if rejected else None
        )
    if is_client:
        return QuoteFacts(
            QuoteStand.RECEIVED, clock.local_date(bundle.quote.created_at)
        )
    if assignment.status == "verbally_agreed":
        agreed = assignment.verbal_agreement_at
        return QuoteFacts(
            QuoteStand.VERBAL, clock.local_date(agreed) if agreed else None
        )
    offers = await quotes.offers_of(session, bundle.quote.id)
    if offers:
        return QuoteFacts(QuoteStand.OFFERED, clock.local_date(offers[0].offered_at))
    approval = (await quote_approval.state_of(session, bundle.quote)).status
    if approval == quote_approval.APPROVAL_REQUESTED:
        return QuoteFacts(QuoteStand.AWAITING_APPROVAL)
    if approval == quote_approval.APPROVAL_SENT_BACK:
        return QuoteFacts(QuoteStand.SENT_BACK)
    return QuoteFacts(QuoteStand.MADE)


async def _billing_facts(
    session: AsyncSession, assignment_id: UUID, today: date
) -> BillingFacts | None:
    overview = await billing_deliveries.overview(session, assignment_id, today=today)
    step = overview.next_step
    labels = {view.period.key: view.period.label for view in overview.periods}
    if step.kind == "deliver" and not step.correction:
        return BillingFacts("deliver", labels[step.period_key])
    if step.kind == "record_invoice":
        return BillingFacts("record_invoice", labels[step.period_key])
    # The notice names neither a cause nor an amount, so no differences to find.
    if await correction_due(session, assignment_id, ()):
        return BillingFacts("correction")
    return None


async def load_facts(
    session: AsyncSession,
    assignment_id: UUID,
    classes: Set[DataClass],
    *,
    today: date | None = None,
) -> PartsFacts:
    """Read the facts of the classes in ``classes``, and no others."""
    day_now = today or clock.today()
    row = await views.assignment_row(session, assignment_id)
    assignment = row.assignment
    external = assignment.kind == EXTERNAL
    money = B in classes
    owner_name = row.owner.person_name if row.owner else None

    if assignment.client_organisation_id in await own_organisation_ids(session):
        return PartsFacts(
            kind=assignment.kind,
            status=assignment.status,
            owner_name=owner_name,
            is_client=True,
            quote=await quote_facts(session, assignment, is_client=True)
            if money
            else None,
        )

    months = budget = quote = billing = report_issued = None
    has_personnel_line = False
    open_roles = other_scale = None

    repo = AssignmentRepository(session)
    lines = (
        await repo.budget_lines([assignment_id])
        if classes & {B, C, ROSTER, SIGNAL}
        else []
    )
    if classes & {B, C}:
        allocations = await repo.allocations_on_lines([line.id for line in lines])
        closed = await MonthCloseRepository(session).closed_months(assignment_id)
        months = MonthFacts(
            overdue=len(
                assignment_finance.overdue_months(
                    [to_calc_allocation(a) for a in allocations], closed, day_now
                )
            ),
            any_closed=bool(closed),
        )
    if classes & {C, ROSTER, SIGNAL}:
        has_personnel_line = any(line.kind == "personnel" for line in lines)
    if money:
        finance = await assignment_finance.assignment_finance(
            session, assignment_id, year=None, today=day_now
        )
        budget = BudgetFacts(
            lines=len(finance.lines),
            over_budget=sum(
                1 for item in finance.lines if item.figures and item.figures.overrun
            ),
            not_priced=sum(1 for item in finance.lines if item.figures is None),
        )
        quote = await quote_facts(session, assignment)
        if external and allows_billing(assignment.status):
            billing = await _billing_facts(session, assignment_id, day_now)
        if assignment.status in _REPORTED or assignment.status == "cancelled":
            report_issued = await final_report(session, assignment_id) is not None
    if has_personnel_line and classes & {C, SIGNAL}:
        staffing = await staffing_board.assignment_staffing(
            session, assignment_id, today=day_now
        )
        if C in classes:
            open_roles = sum(1 for role in staffing.roles if role.gaps)
        if SIGNAL in classes:
            other_scale = len(
                {
                    item.bar.person_id
                    for role in staffing.roles
                    for item in role.bars
                    if item.bar.category_mismatch
                }
            )

    return PartsFacts(
        kind=assignment.kind,
        status=assignment.status,
        owner_name=owner_name,
        months=months,
        budget=budget,
        quote=quote,
        billing=billing,
        report_issued=report_issued,
        has_personnel_line=has_personnel_line,
        open_roles=open_roles,
        other_scale=other_scale,
    )


async def own_line(
    session: AsyncSession,
    assignment_id: UUID,
    person_id: UUID,
    *,
    today: date | None = None,
) -> str | None:
    """The inzet of this person here, as "Developer, 100%, tot 31 dec 2026"."""
    repo = AssignmentRepository(session)
    lines = {line.id: line for line in await repo.budget_lines([assignment_id])}
    inzet = [
        OwnInzet(
            role=lines[a.budget_line_id].role or lines[a.budget_line_id].description,
            fte_pct=a.fte_pct,
            start_date=a.start_date,
            end_date=a.end_date,
        )
        for a in await repo.allocations_on_lines(list(lines))
        if a.person_id == person_id
    ]
    return own_line_of(inzet, today or clock.today())


async def part_keys_of(
    session: AsyncSession, classes: Mapping[UUID, Set[DataClass]]
) -> dict[UUID, set[str]]:
    """The keys of the rows each assignment has for its reader, without what
    the rows report. ``parts_of`` decides, from only the facts it reads for
    existence: a fixed number of statements however many assignments."""
    if not classes:
        return {}
    ids = list(classes)
    assignments = {
        a.id: a
        for a in await session.scalars(select(Assignment).where(Assignment.id.in_(ids)))
    }
    own = await own_organisation_ids(session)
    cared = [i for i in ids if A in classes[i] and i in assignments]

    def wanting(wanted: Set[DataClass]) -> list[UUID]:
        return [i for i in cared if classes[i] & wanted]

    team_ids = wanting({C, ROSTER})
    personnel = set(
        await session.scalars(
            select(BudgetLine.assignment_id)
            .where(
                BudgetLine.assignment_id.in_(team_ids), BudgetLine.kind == "personnel"
            )
            .distinct()
        )
        if team_ids
        else ()
    )
    close_ids = wanting({B, C})
    closed = set(
        await session.scalars(
            select(MonthClose.assignment_id)
            .where(
                MonthClose.assignment_id.in_(close_ids),
                MonthClose.reopened_at.is_(None),
            )
            .distinct()
        )
        if close_ids
        else ()
    )
    quote_ids = [i for i in wanting({B}) if assignments[i].kind != EXTERNAL]
    by_assignment: dict[UUID, list[Quote]] = {}
    if quote_ids:
        for quote in await session.scalars(
            select(Quote)
            .where(Quote.assignment_id.in_(quote_ids))
            .order_by(Quote.issued_at.desc(), Quote.created_at.desc())
        ):
            by_assignment.setdefault(quote.assignment_id, []).append(quote)

    found: dict[UUID, set[str]] = {i: set() for i in ids}
    for i in cared:
        assignment = assignments[i]
        has_quote = chosen_quote(by_assignment.get(i, [])) is not None
        facts = PartsFacts(
            kind=assignment.kind,
            status=assignment.status,
            is_client=assignment.client_organisation_id in own,
            months=MonthFacts(any_closed=i in closed),
            quote=QuoteFacts(QuoteStand.MADE if has_quote else QuoteStand.NONE)
            if B in classes[i]
            else None,
            has_personnel_line=i in personnel,
        )
        found[i] = {part.key for part in parts_of(facts, classes[i])}
    return found
