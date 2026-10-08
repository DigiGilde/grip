"""The phase of an assignment, and what each status allows.

An assignment starts as a potential one: something that may become work. It
turns active when the client agrees, and closed when it ends, is rejected or
is cancelled. The phase is derived from the status and never stored.

Everything that needs to know "is this still potential?" or "may this be
billed?" asks here. No other module tests lists of statuses for that.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class Phase(StrEnum):
    POTENTIAL = "potential"
    ACTIVE = "active"
    CLOSED = "closed"


class Commitment(StrEnum):
    """How firm the expected revenue of an assignment is, for forecasts."""

    # Formally accepted: counts as committed.
    COMMITTED = "committed"
    # Verbally agreed: counts in the forecast, shown as "mondeling".
    VERBAL = "verbal"
    # Not agreed yet: pipeline.
    PIPELINE = "pipeline"
    # Rejected or cancelled before acceptance: counts for nothing.
    NONE = "none"


VERBALLY_AGREED = "verbally_agreed"

_PHASES: dict[str, Phase] = {
    "draft": Phase.POTENTIAL,
    "requested": Phase.POTENTIAL,
    "quoted": Phase.POTENTIAL,
    VERBALLY_AGREED: Phase.POTENTIAL,
    "accepted": Phase.ACTIVE,
    "in_progress": Phase.ACTIVE,
    "completed": Phase.CLOSED,
    "accounted": Phase.CLOSED,
    "rejected": Phase.CLOSED,
    "cancelled": Phase.CLOSED,
}

_COMMITMENTS: dict[str, Commitment] = {
    "draft": Commitment.PIPELINE,
    "requested": Commitment.PIPELINE,
    "quoted": Commitment.PIPELINE,
    VERBALLY_AGREED: Commitment.VERBAL,
    "accepted": Commitment.COMMITTED,
    "in_progress": Commitment.COMMITTED,
    "completed": Commitment.COMMITTED,
    "accounted": Commitment.COMMITTED,
    "rejected": Commitment.NONE,
    "cancelled": Commitment.NONE,
}

# Dutch labels of the statuses, as shown to users. "draft" is what the old
# administration called "interne afstemming".
STATUS_LABELS: dict[str, str] = {
    "draft": "In voorbereiding",
    "requested": "Aangevraagd",
    "quoted": "Offerte uitgegeven",
    VERBALLY_AGREED: "Mondeling akkoord",
    "accepted": "Akkoord",
    "in_progress": "In uitvoering",
    "completed": "Afgerond",
    "accounted": "Verantwoord",
    "rejected": "Afgewezen",
    "cancelled": "Geannuleerd",
}

PHASE_LABELS: dict[Phase, str] = {
    Phase.POTENTIAL: "Potentieel",
    Phase.ACTIVE: "Lopend",
    Phase.CLOSED: "Afgesloten",
}

# Statuses in which the months of an assignment can be closed: work has
# started, or has just ended.
_MONTH_CLOSE_STATUSES = frozenset(
    {VERBALLY_AGREED, "accepted", "in_progress", "completed"}
)


class _HasStatus(Protocol):
    status: str


def phase_of(status: str) -> Phase:
    """The phase a status belongs to."""
    try:
        return _PHASES[status]
    except KeyError:
        raise ValueError(f"unknown assignment status: {status}") from None


def assignment_phase(assignment: _HasStatus) -> Phase:
    return phase_of(assignment.status)


def statuses_in_phase(*phases: Phase) -> frozenset[str]:
    """The statuses of one or more phases, for a filter in a query."""
    return frozenset(s for s, p in _PHASES.items() if p in phases)


def commitment_of(status: str) -> Commitment:
    """How an assignment in this status counts in a forecast."""
    try:
        return _COMMITMENTS[status]
    except KeyError:
        raise ValueError(f"unknown assignment status: {status}") from None


def statuses_with_commitment(*commitments: Commitment) -> frozenset[str]:
    return frozenset(s for s, c in _COMMITMENTS.items() if c in commitments)


def is_tentative(status: str) -> bool:
    """Whether inzet on an assignment in this status is tentative.

    Staffing a potential assignment is planning ahead: it may not happen.
    Occupancy shows it apart from firm inzet.
    """
    return phase_of(status) is Phase.POTENTIAL


def counterparty_status(status: str) -> str:
    """The status as another instance should see it.

    A verbal agreement is knowledge of the contractor only. Towards the
    client, and towards a parent instance, the assignment is still quoted
    until the quote is formally accepted.
    """
    return "quoted" if status == VERBALLY_AGREED else status


def allows_month_close(status: str) -> bool:
    """Whether a month of an assignment in this status can be closed."""
    return status in _MONTH_CLOSE_STATUSES


def allows_billing(status: str) -> bool:
    """Whether billing data may be produced for an assignment in this status.

    Only once the quote is formally accepted. A verbal agreement is no
    ground to bill on, and neither is an assignment that was rejected or
    cancelled.
    """
    return commitment_of(status) is Commitment.COMMITTED


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)
