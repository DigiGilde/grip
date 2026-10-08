"""What needs attention on an assignment, as sentences for the start page.

Built from the same read model as the Financieel tab, so the start page and
the tab never disagree. Each point names the tab where it is solved.
"""

from dataclasses import dataclass

from grip.services.assignment_finance import AssignmentFinance


@dataclass(frozen=True)
class Attention:
    kind: str
    text: str
    # The tab of the assignment where the point is solved.
    tab: str
    # Money points are for a reader of the finances; the rate mismatch is a
    # signal a planner sees too, without category or amount.
    about_money: bool


def _euro(cents: int) -> str:
    return "€ " + f"{round(cents / 100):,}".replace(",", ".")


def _count(number: int, one: str, many: str) -> str:
    return f"{number} {one if number == 1 else many}"


def attention_points(data: AssignmentFinance) -> list[Attention]:
    """The points of one assignment, the most pressing first."""
    points: list[Attention] = []
    by_kind = {signal.kind: signal for signal in data.signals}
    if data.totals is not None and data.totals.overrun:
        over = _euro(-data.totals.variance_cents)
        points.append(
            Attention(
                "overrun",
                f"Verwacht totaal {over} boven de begroting.",
                "finance",
                True,
            )
        )
    overdue = by_kind.get("months_not_closed")
    if overdue is not None and overdue.count:
        text = (
            "1 maand met inzet is nog niet afgesloten."
            if overdue.count == 1
            else f"{overdue.count} maanden met inzet zijn nog niet afgesloten."
        )
        points.append(Attention("months_not_closed", text, "monthClose", True))
    unpriced = by_kind.get("not_priced")
    if unpriced is not None and unpriced.count:
        text = (
            "1 begrotingsregel kan niet worden berekend."
            if unpriced.count == 1
            else f"{unpriced.count} begrotingsregels kunnen niet worden berekend."
        )
        points.append(Attention("not_priced", text, "budget", True))
    mismatch = by_kind.get("rate_mismatch")
    if mismatch is not None and mismatch.count:
        who = _count(mismatch.count, "persoon declareert", "mensen declareren")
        points.append(
            Attention(
                "rate_mismatch",
                f"{who} in een andere schaal dan de begrotingsregel aanneemt.",
                "staffing",
                False,
            )
        )
    return points
