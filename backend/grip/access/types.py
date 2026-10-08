"""The vocabulary of an access decision: who, which action, what, in which context.

The shape follows an AuthZEN evaluation request (subject, action, resource,
context), so an external decision point can take over later without the
callers changing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID


class DataClass(StrEnum):
    """The class a piece of data belongs to. Every response field has one.

    The first six are the classes A to F of the access model. The others are
    narrower views that exist so a subject can get less than a whole class:
    they are implied by a broader class (see ``IMPLIED_BY``) and never grant
    anything beyond it.
    """

    # A: name, parties, status, period, context URIs, progress.
    ASSIGNMENT_BASIC = "assignment_basic"
    # B: budget, used, available, quoted amount, billing data, costs, coverage.
    ASSIGNMENT_FINANCIAL = "assignment_financial"
    # C: who, role, percentage, period.
    STAFFING = "staffing"
    # D: billing scale, rate category, allocation amount per person.
    PERSON_RATE = "person_rate"
    # E: cost rate of hired staff, margin.
    PERSON_COST = "person_cost"
    # F: billability target and realisation.
    PERSON_KPI = "person_kpi"

    # Part of C: only who is on the team and in which role, without
    # percentage or period. What a member of an assignment sees.
    STAFFING_ROSTER = "staffing_roster"
    # Derived from C: head counts per role and period, without names. What a
    # parent instance gets by default.
    STAFFING_COUNTS = "staffing_counts"
    # Derived from D: the boolean "this person bills in another category than
    # the budget line assumes" (rule R14), without the category itself. What
    # a planner sees.
    RATE_MISMATCH_SIGNAL = "rate_mismatch_signal"

    # Not personal and not tied to an assignment: rate cards.
    MASTER_DATA = "master_data"

    # Derived from C: a published open role with an established text
    # (function, scale, FTE, period and the text), without any name. What
    # every person of the instance sees of a vacancy. The rules for it live
    # in ``grip.access.vacancies``.
    OPEN_ROLE = "open_role"


CORE_DATA_CLASSES: tuple[DataClass, ...] = (
    DataClass.ASSIGNMENT_BASIC,
    DataClass.ASSIGNMENT_FINANCIAL,
    DataClass.STAFFING,
    DataClass.PERSON_RATE,
    DataClass.PERSON_COST,
    DataClass.PERSON_KPI,
)

# A narrower view is readable by whoever may read the class it is cut from.
IMPLIED_BY: dict[DataClass, DataClass] = {
    DataClass.STAFFING_ROSTER: DataClass.STAFFING,
    DataClass.STAFFING_COUNTS: DataClass.STAFFING,
    DataClass.RATE_MISMATCH_SIGNAL: DataClass.PERSON_RATE,
}


class Action(StrEnum):
    READ = "read"
    EDIT = "edit"
    # Start a new assignment as contractor.
    CREATE_ASSIGNMENT = "create_assignment"
    # Ask a contractor for a quote, as client.
    REQUEST_ASSIGNMENT = "request_assignment"
    ISSUE_QUOTE = "issue_quote"
    # Accept or reject a quote.
    ACCEPT_QUOTE = "accept_quote"
    DELIVER_REPORT = "deliver_report"
    CLOSE_MONTH = "close_month"
    REOPEN_MONTH = "reopen_month"
    # Record, correct or withdraw the fact that an invoice was sent.
    RECORD_INVOICE = "record_invoice"
    # Rate cards, including changes in a closed year.
    MANAGE_RATES = "manage_rates"
    # Persons, their scale history and targets, and who holds which function.
    MANAGE_USERS = "manage_users"
    # Name or remove the owner and the managers of an assignment. Its own
    # action: it never implies editing the content of the assignment.
    MANAGE_ROLES = "manage_roles"
    # Record an advice or the approval on a vacancy request.
    RECORD_DECISION = "record_decision"
    # Ask for internal approval of a made quote, and give or refuse it.
    REQUEST_QUOTE_APPROVAL = "request_quote_approval"
    DECIDE_QUOTE_APPROVAL = "decide_quote_approval"


class SubjectKind(StrEnum):
    PERSON = "person"
    # Someone from another organisation who was invited to sign one quote.
    GUEST = "guest"
    # Another instance or a corpus system, identified by its FSC peer id.
    PEER = "peer"


class ResourceKind(StrEnum):
    ASSIGNMENT = "assignment"
    # One person in the context of one assignment.
    ALLOCATION = "allocation"
    PERSON = "person"
    QUOTE = "quote"
    COST_ITEM = "cost_item"
    RATE_CARD = "rate_card"
    INSTANCE = "instance"
    # The three kinds below are decided in ``grip.access.vacancies``.
    VACANCY = "vacancy"
    # The blank request form of the instance and its field mapping.
    FORM_TEMPLATE = "form_template"
    # The configuration of the language model that drafts texts.
    LANGUAGE_MODEL = "language_model"
    # The function families and groups of the Functiegebouw Rijk.
    FUNCTION_FRAMEWORK = "function_framework"


class PeerRole(StrEnum):
    COUNTERPART = "counterpart"
    PARENT = "parent"
    CHILD = "child"
    CORPUS = "corpus"


class AssignmentRole(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"


@dataclass(frozen=True)
class Subject:
    kind: SubjectKind
    person_id: UUID | None = None
    functions: frozenset[str] = frozenset()
    peer_id: str | None = None
    invitation_id: UUID | None = None
    # Verified email of a guest; an invitation is matched on it.
    email: str | None = None

    @classmethod
    def for_person(
        cls, person_id: UUID, functions: frozenset[str] | set[str] = frozenset()
    ) -> Subject:
        return cls(
            SubjectKind.PERSON, person_id=person_id, functions=frozenset(functions)
        )

    @classmethod
    def for_guest(
        cls, *, email: str | None = None, invitation_id: UUID | None = None
    ) -> Subject:
        return cls(SubjectKind.GUEST, email=email, invitation_id=invitation_id)

    @classmethod
    def for_peer(cls, peer_id: str) -> Subject:
        return cls(SubjectKind.PEER, peer_id=peer_id)

    @property
    def identifier(self) -> str:
        if self.kind is SubjectKind.PERSON:
            return str(self.person_id)
        if self.kind is SubjectKind.PEER:
            return self.peer_id or ""
        return str(self.invitation_id or self.email or "")


@dataclass(frozen=True)
class Resource:
    """What the decision is about.

    ``id`` is the id of the thing itself; ``None`` means the kind as such (a
    collection, or something that does not exist yet). ``assignment_id`` and
    ``person_id`` say which assignment and which person the data is about,
    because most relations hang on one of those two.
    """

    kind: ResourceKind
    id: UUID | None = None
    assignment_id: UUID | None = None
    person_id: UUID | None = None
    # Facts about the resource that the caller looked up and that a rule
    # needs, as (name, value) pairs. They travel as resource properties in
    # an AuthZEN request. Empty for every kind that does not need them.
    properties: tuple[tuple[str, str], ...] = ()

    def property(self, name: str) -> str | None:
        for key, value in self.properties:
            if key == name:
                return value
        return None

    @classmethod
    def assignment(cls, assignment_id: UUID | None = None) -> Resource:
        return cls(
            ResourceKind.ASSIGNMENT, id=assignment_id, assignment_id=assignment_id
        )

    @classmethod
    def allocation(cls, assignment_id: UUID, person_id: UUID) -> Resource:
        return cls(
            ResourceKind.ALLOCATION, assignment_id=assignment_id, person_id=person_id
        )

    @classmethod
    def person(cls, person_id: UUID | None = None) -> Resource:
        return cls(ResourceKind.PERSON, id=person_id, person_id=person_id)

    @classmethod
    def quote(cls, quote_id: UUID | None, assignment_id: UUID | None) -> Resource:
        return cls(ResourceKind.QUOTE, id=quote_id, assignment_id=assignment_id)

    @classmethod
    def cost_item(cls, cost_item_id: UUID | None = None) -> Resource:
        return cls(ResourceKind.COST_ITEM, id=cost_item_id)

    @classmethod
    def rate_card(cls) -> Resource:
        return cls(ResourceKind.RATE_CARD)

    @classmethod
    def instance(cls) -> Resource:
        return cls(ResourceKind.INSTANCE)


@dataclass(frozen=True)
class Context:
    """Facts about the request that are not about the subject or the resource."""

    # The counterparty explicitly pulled this data (it is never pushed).
    on_request: bool = False
    # The FSC contract with the counterparty covers financial data.
    contract_allows_financial: bool = False
    # Instance setting: staffing goes to the parent instance with names.
    parent_may_see_names: bool = False
    # The period on screen, inclusive. Bounds who counts as "on the assignment".
    period: tuple[date, date] | None = None
    today: date | None = None

    def effective_today(self) -> date:
        return self.today or date.today()

    def effective_period(self) -> tuple[date, date]:
        if self.period is not None:
            return self.period
        today = self.effective_today()
        return (today, today)


@dataclass(frozen=True)
class AccessRequest:
    subject: Subject
    action: Action
    resource: Resource
    data_class: DataClass | None = None
    context: Context = field(default_factory=Context)

    def to_authzen(self) -> dict[str, Any]:
        """The request as an AuthZEN access evaluation request body."""
        s, r, c = self.subject, self.resource, self.context
        subject_props: dict[str, Any] = {}
        if s.functions:
            subject_props["functions"] = sorted(s.functions)
        if s.kind is SubjectKind.GUEST:
            if s.email:
                subject_props["email"] = s.email
            if s.invitation_id:
                subject_props["invitation_id"] = str(s.invitation_id)
        resource_props: dict[str, Any] = {}
        if self.data_class is not None:
            resource_props["data_class"] = self.data_class.value
        if r.assignment_id is not None:
            resource_props["assignment_id"] = str(r.assignment_id)
        if r.person_id is not None:
            resource_props["person_id"] = str(r.person_id)
        for name, value in r.properties:
            resource_props.setdefault(name, value)
        period = c.period
        return {
            "subject": {
                "type": s.kind.value,
                "id": s.identifier,
                "properties": subject_props,
            },
            "action": {"name": self.action.value},
            "resource": {
                "type": r.kind.value,
                "id": str(r.id) if r.id is not None else "",
                "properties": resource_props,
            },
            "context": {
                "on_request": c.on_request,
                "contract_allows_financial": c.contract_allows_financial,
                "parent_may_see_names": c.parent_may_see_names,
                "period": [period[0].isoformat(), period[1].isoformat()]
                if period
                else None,
                "today": c.today.isoformat() if c.today else None,
            },
        }


@dataclass(frozen=True)
class Decision:
    allowed: bool
    # Machine-readable code: which function or relation granted it, or why not.
    reason: str

    def __bool__(self) -> bool:
        return self.allowed

    def to_authzen(self) -> dict[str, Any]:
        return {"decision": self.allowed, "context": {"reason": self.reason}}

    @classmethod
    def from_authzen(cls, body: dict[str, Any]) -> Decision:
        """Read an AuthZEN response. Anything but an explicit ``true`` denies."""
        allowed = body.get("decision") is True
        context = body.get("context")
        reason = context.get("reason") if isinstance(context, dict) else None
        return cls(
            allowed,
            str(reason)
            if reason
            else ("external_allow" if allowed else "external_deny"),
        )


def allow(reason: str) -> Decision:
    return Decision(True, reason)


def deny(reason: str) -> Decision:
    return Decision(False, reason)
