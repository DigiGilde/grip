"""The decision function.

Every access decision in grip goes through a ``Decider``. ``LocalDecider``
implements the matrix from the access model on relations derived from the
instance's own data. An external decision point can replace it by
implementing the same protocol; callers only know the protocol.

Functions and relations add up: a subject is allowed when any one of them
grants the request.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from grip.access import quote_approval, vacancies
from grip.access.relations import RelationSource
from grip.access.types import (
    IMPLIED_BY,
    AccessRequest,
    Action,
    Context,
    DataClass,
    Decision,
    PeerRole,
    Resource,
    ResourceKind,
    Subject,
    SubjectKind,
    allow,
    deny,
)

# The functions a person can hold. Same ids as the seeded ``role`` rows.
BEHEERDER = "beheerder"
PLANNER = "planner"
LEZER = "lezer"
AANVRAGER = "aanvrager"
TEKENBEVOEGDE = "tekenbevoegde"

_ASSIGNMENT_CLASSES = {DataClass.ASSIGNMENT_BASIC, DataClass.ASSIGNMENT_FINANCIAL}
_STAFFING_CLASSES = {
    DataClass.STAFFING,
    DataClass.STAFFING_ROSTER,
    DataClass.STAFFING_COUNTS,
}
_PERSON_CLASSES = {
    DataClass.PERSON_RATE,
    DataClass.PERSON_COST,
    DataClass.PERSON_KPI,
    DataClass.RATE_MISMATCH_SIGNAL,
}

_NO_GRANT = "no_grant"


class Decider(Protocol):
    async def evaluate(self, request: AccessRequest) -> Decision: ...


async def decide(
    decider: Decider,
    subject: Subject,
    action: Action,
    resource: Resource,
    data_class: DataClass | None = None,
    context: Context | None = None,
) -> Decision:
    """Ask the decider whether the subject may do this."""
    return await decider.evaluate(
        AccessRequest(subject, action, resource, data_class, context or Context())
    )


async def permitted_classes(
    decider: Decider,
    subject: Subject,
    resource: Resource,
    data_classes: Iterable[DataClass],
    context: Context | None = None,
    action: Action = Action.READ,
) -> frozenset[DataClass]:
    """The subset of ``data_classes`` the subject may read (or edit) on the resource."""
    permitted: set[DataClass] = set()
    for data_class in dict.fromkeys(data_classes):
        if await decide(decider, subject, action, resource, data_class, context):
            permitted.add(data_class)
    return frozenset(permitted)


class LocalDecider:
    """Decides on the instance's own data."""

    def __init__(self, relations: RelationSource) -> None:
        self._relations = relations

    async def evaluate(self, request: AccessRequest) -> Decision:
        # Vacancies, form templates and the language model have their own
        # rules in a separate module.
        if request.resource.kind in vacancies.KINDS:
            return await vacancies.evaluate(self._relations, request)
        # Internal approval of a quote: its own module answers the questions
        # it has a rule for and leaves every other one to the matrix.
        approval = await quote_approval.evaluate(self._relations, request)
        if approval is not None:
            return approval
        kind = request.subject.kind
        if kind is SubjectKind.PERSON:
            if request.subject.person_id is None:
                return deny("no_identity")
            return await self._person(request)
        if kind is SubjectKind.GUEST:
            return await self._guest(request)
        if kind is SubjectKind.PEER:
            if not request.subject.peer_id:
                return deny("no_identity")
            return await self._peer(request)
        return deny(_NO_GRANT)

    # ------------------------------------------------------------------
    # Persons
    # ------------------------------------------------------------------

    async def _person(self, req: AccessRequest) -> Decision:
        action = req.action
        functions = req.subject.functions
        person_id = req.subject.person_id
        assert person_id is not None

        if action is Action.MANAGE_RATES or action is Action.MANAGE_USERS:
            return (
                allow("function:beheerder")
                if BEHEERDER in functions
                else deny(_NO_GRANT)
            )
        if action is Action.REOPEN_MONTH:
            return (
                allow("function:beheerder")
                if BEHEERDER in functions
                else deny(_NO_GRANT)
            )
        if action is Action.MANAGE_ROLES:
            # Who owns or manages an assignment is decided by whoever already
            # does, and by the beheerder on any assignment: an owner may have
            # left. The relation is checked first, so the reason says when the
            # beheerder acted on the function alone.
            if (
                req.resource.kind is not ResourceKind.ASSIGNMENT
                or req.resource.assignment_id is None
            ):
                return deny("not_applicable")
            reason = await self._manager_reason(req)
            if reason:
                return allow(reason)
            if BEHEERDER in functions:
                return allow("function:beheerder")
            return deny(_NO_GRANT)
        if action is Action.RECORD_INVOICE:
            # Whoever manages the assignment, and the beheerder.
            if BEHEERDER in functions:
                return allow("function:beheerder")
            return await self._as_manager(req)
        if action is Action.REQUEST_ASSIGNMENT:
            return (
                allow("function:aanvrager")
                if AANVRAGER in functions
                else deny(_NO_GRANT)
            )
        if action is Action.CREATE_ASSIGNMENT:
            if BEHEERDER in functions:
                return allow("function:beheerder")
            if PLANNER in functions:
                return allow("function:planner")
            if await self._relations.manages_any_assignment(person_id):
                return allow("relation:manager")
            return deny(_NO_GRANT)
        if action in (Action.ISSUE_QUOTE, Action.CLOSE_MONTH, Action.DELIVER_REPORT):
            return await self._as_manager(req)
        if action is Action.ACCEPT_QUOTE:
            return await self._person_accepts_quote(req)
        if action is Action.READ:
            return await self._person_reads(req)
        if action is Action.EDIT:
            return await self._person_edits(req)
        return deny(_NO_GRANT)

    async def _manager_reason(self, req: AccessRequest) -> str | None:
        """``relation:owner`` or ``relation:manager`` on the resource's assignment."""
        assignment_id = req.resource.assignment_id
        if assignment_id is None or req.subject.person_id is None:
            return None
        role = await self._relations.assignment_role(
            req.subject.person_id, assignment_id
        )
        return f"relation:{role.value}" if role is not None else None

    async def _as_manager(self, req: AccessRequest) -> Decision:
        reason = await self._manager_reason(req)
        return allow(reason) if reason else deny(_NO_GRANT)

    async def _person_accepts_quote(self, req: AccessRequest) -> Decision:
        res = req.resource
        if res.kind is not ResourceKind.QUOTE or res.id is None:
            return deny("not_applicable")
        if (
            TEKENBEVOEGDE in req.subject.functions
            and res.assignment_id is not None
            and await self._relations.instance_is_client(res.assignment_id)
        ):
            return allow("function:tekenbevoegde")
        if await self._relations.is_invited_signer(
            res.id, person_id=req.subject.person_id
        ):
            return allow("relation:guest_signer")
        return deny(_NO_GRANT)

    async def _person_reads(self, req: AccessRequest) -> Decision:
        res, data_class = req.resource, req.data_class
        if data_class is None:
            return deny("data_class_required")

        if data_class is DataClass.MASTER_DATA:
            # Rate cards are not personal; every active person may read them.
            return (
                allow("active_person")
                if res.kind is ResourceKind.RATE_CARD
                else deny("not_applicable")
            )

        decision = await self._person_reads_exact(req, data_class)
        if decision.allowed:
            return decision
        broader = IMPLIED_BY.get(data_class)
        if broader is not None:
            implied = await self._person_reads_exact(req, broader)
            if implied.allowed:
                return implied
        return decision

    async def _person_reads_exact(
        self, req: AccessRequest, data_class: DataClass
    ) -> Decision:
        if data_class in _ASSIGNMENT_CLASSES:
            return await self._person_reads_assignment(req, data_class)
        if data_class in _STAFFING_CLASSES:
            return await self._person_reads_staffing(req, data_class)
        if data_class in _PERSON_CLASSES:
            return await self._person_reads_person_data(req, data_class)
        return deny("not_applicable")

    async def _person_reads_assignment(
        self, req: AccessRequest, data_class: DataClass
    ) -> Decision:
        res, functions = req.resource, req.subject.functions
        person_id = req.subject.person_id
        assert person_id is not None
        financial = data_class is DataClass.ASSIGNMENT_FINANCIAL

        if res.kind is ResourceKind.COST_ITEM:
            # A cost item is not tied to one assignment; all of it is class B.
            if not financial:
                return deny("not_applicable")
            if BEHEERDER in functions:
                return allow("function:beheerder")
            if LEZER in functions:
                return allow("function:lezer")
            if res.id is not None and await self._relations.manages_cost_item(
                person_id, res.id
            ):
                return allow("relation:manager")
            if res.id is None and await self._relations.manages_any_assignment(
                person_id
            ):
                return allow("relation:manager")
            return deny(_NO_GRANT)

        if res.kind not in (ResourceKind.ASSIGNMENT, ResourceKind.QUOTE):
            return deny("not_applicable")

        if BEHEERDER in functions:
            return allow("function:beheerder")
        if LEZER in functions:
            return allow("function:lezer")
        if not financial and PLANNER in functions:
            return allow("function:planner")

        reason = await self._manager_reason(req)
        if reason:
            return allow(reason)

        assignment_id = res.assignment_id
        if (
            not financial
            and res.kind is ResourceKind.ASSIGNMENT
            and assignment_id is not None
            and await self._relations.is_member(
                person_id, assignment_id, req.context.effective_today()
            )
        ):
            return allow("relation:member")

        if res.kind is ResourceKind.QUOTE:
            # A quote is read in full by whoever must sign it.
            if (
                TEKENBEVOEGDE in functions
                and assignment_id is not None
                and await self._relations.instance_is_client(assignment_id)
            ):
                return allow("function:tekenbevoegde")
            if res.id is not None and await self._relations.is_invited_signer(
                res.id, person_id=person_id
            ):
                return allow("relation:guest_signer")
        return deny(_NO_GRANT)

    async def _person_reads_staffing(
        self, req: AccessRequest, data_class: DataClass
    ) -> Decision:
        res, functions = req.resource, req.subject.functions
        person_id = req.subject.person_id
        assert person_id is not None
        if res.kind not in (
            ResourceKind.ASSIGNMENT,
            ResourceKind.ALLOCATION,
            ResourceKind.PERSON,
        ):
            return deny("not_applicable")

        if BEHEERDER in functions:
            return allow("function:beheerder")
        if PLANNER in functions:
            return allow("function:planner")

        if res.kind is not ResourceKind.PERSON:
            reason = await self._manager_reason(req)
            if reason:
                return allow(reason)

        about = res.person_id
        if about is not None:
            if about == person_id:
                return allow("relation:self")
            if await self._relations.is_line_manager(person_id, about):
                return allow("relation:line_manager")

        if data_class is DataClass.STAFFING_ROSTER:
            # Names and roles only: for the team itself, and for whoever has to
            # pick a person to staff.
            if (
                res.kind is not ResourceKind.PERSON
                and res.assignment_id is not None
                and await self._relations.is_member(
                    person_id, res.assignment_id, req.context.effective_today()
                )
            ):
                return allow("relation:member")
            if (
                res.kind is ResourceKind.PERSON
                and await self._relations.manages_any_assignment(person_id)
            ):
                return allow("relation:manager")
        return deny(_NO_GRANT)

    async def _person_reads_person_data(
        self, req: AccessRequest, data_class: DataClass
    ) -> Decision:
        res, functions = req.resource, req.subject.functions
        person_id = req.subject.person_id
        assert person_id is not None
        if res.kind not in (
            ResourceKind.ASSIGNMENT,
            ResourceKind.ALLOCATION,
            ResourceKind.PERSON,
        ):
            return deny("not_applicable")

        if BEHEERDER in functions:
            return allow("function:beheerder")
        if data_class is DataClass.RATE_MISMATCH_SIGNAL and PLANNER in functions:
            return allow("function:planner")

        about = res.person_id
        personal = data_class in (
            DataClass.PERSON_RATE,
            DataClass.PERSON_KPI,
            DataClass.RATE_MISMATCH_SIGNAL,
        )
        if personal and about is not None:
            if about == person_id:
                return allow("relation:self")
            if await self._relations.is_line_manager(person_id, about):
                return allow("relation:line_manager")

        if data_class is DataClass.PERSON_KPI or res.kind is ResourceKind.PERSON:
            # The KPI never follows from an assignment, and neither does
            # anything asked about a person outside the context of one.
            return deny(_NO_GRANT)

        reason = await self._manager_reason(req)
        if reason is None:
            return deny(_NO_GRANT)
        assignment_id = res.assignment_id
        assert assignment_id is not None

        if data_class is DataClass.PERSON_COST:
            # Cost and margin hang on a person, so the manager only gets them
            # for people staffed on the own assignment in the period shown.
            if about is None:
                return deny("person_required")
            if not await self._relations.is_allocated(
                about, assignment_id, req.context.effective_period()
            ):
                return deny("not_allocated_in_period")
            return allow(reason)

        if about is not None and not await self._relations.is_allocated(
            about, assignment_id, None
        ):
            return deny("not_allocated")
        return allow(reason)

    async def _person_edits(self, req: AccessRequest) -> Decision:
        res, data_class, functions = req.resource, req.data_class, req.subject.functions
        person_id = req.subject.person_id
        assert person_id is not None
        if data_class is None:
            return deny("data_class_required")

        if data_class in _ASSIGNMENT_CLASSES:
            if res.kind is ResourceKind.COST_ITEM:
                if data_class is not DataClass.ASSIGNMENT_FINANCIAL:
                    return deny("not_applicable")
                # Cost items are shared between assignments, so the beheerder
                # may add and change them. Otherwise: whoever manages an
                # assignment may add one, and an existing one is changed by
                # the managers of an assignment whose budget covers it, or by
                # its creator while nothing covers it yet.
                if BEHEERDER in functions:
                    return allow("function:beheerder")
                if res.id is None:
                    managed = await self._relations.manages_any_assignment(person_id)
                else:
                    managed = await self._relations.manages_cost_item(person_id, res.id)
                return allow("relation:manager") if managed else deny(_NO_GRANT)
            if res.kind not in (ResourceKind.ASSIGNMENT, ResourceKind.QUOTE):
                return deny("not_applicable")
            return await self._as_manager(req)

        if data_class is DataClass.STAFFING:
            if res.kind not in (ResourceKind.ASSIGNMENT, ResourceKind.ALLOCATION):
                return deny("not_applicable")
            if PLANNER in functions:
                return allow("function:planner")
            return await self._as_manager(req)

        if data_class in (
            DataClass.PERSON_RATE,
            DataClass.PERSON_COST,
            DataClass.PERSON_KPI,
        ):
            # Scale history, cost rates and targets are master data of a
            # person: changed with ``manage_users``, never with ``edit``.
            return deny("use_manage_users")
        if data_class is DataClass.MASTER_DATA:
            return deny("use_manage_rates")
        # The narrower views are derived; there is nothing to edit.
        return deny("not_applicable")

    # ------------------------------------------------------------------
    # Guests
    # ------------------------------------------------------------------

    async def _guest(self, req: AccessRequest) -> Decision:
        """A guest signer sees and signs exactly one quote."""
        res, subject = req.resource, req.subject
        if res.kind is not ResourceKind.QUOTE or res.id is None:
            return deny(_NO_GRANT)
        if subject.invitation_id is None and not subject.email:
            return deny("no_identity")
        if req.action is Action.READ:
            if req.data_class not in _ASSIGNMENT_CLASSES:
                return deny(_NO_GRANT)
        elif req.action is not Action.ACCEPT_QUOTE:
            return deny(_NO_GRANT)
        invited = await self._relations.is_invited_signer(
            res.id, invitation_id=subject.invitation_id, email=subject.email
        )
        return allow("relation:guest_signer") if invited else deny(_NO_GRANT)

    # ------------------------------------------------------------------
    # Peers
    # ------------------------------------------------------------------

    async def _peer(self, req: AccessRequest) -> Decision:
        peer_id = req.subject.peer_id
        assert peer_id is not None
        roles = await self._relations.peer_roles(peer_id)
        if not roles:
            return deny("unknown_peer")

        res, action, data_class = req.resource, req.action, req.data_class
        assignment_id = res.assignment_id

        if action is Action.REQUEST_ASSIGNMENT:
            return (
                allow("relation:counterparty")
                if PeerRole.COUNTERPART in roles
                else deny(_NO_GRANT)
            )

        if action in (Action.ISSUE_QUOTE, Action.DELIVER_REPORT):
            if PeerRole.COUNTERPART not in roles:
                return deny(_NO_GRANT)
            if assignment_id is None:
                # A quote on the contractor's own initiative has no assignment
                # on this side yet. A report always belongs to one.
                return (
                    allow("relation:counterparty")
                    if action is Action.ISSUE_QUOTE
                    else deny(_NO_GRANT)
                )
            if await self._relations.peer_is_contractor_of(peer_id, assignment_id):
                return allow("relation:contractor")
            return deny(_NO_GRANT)

        if action is Action.ACCEPT_QUOTE:
            if (
                res.kind is ResourceKind.QUOTE
                and assignment_id is not None
                and PeerRole.COUNTERPART in roles
                and await self._relations.peer_is_client_of(peer_id, assignment_id)
            ):
                return allow("relation:counterparty")
            return deny(_NO_GRANT)

        if action is not Action.READ:
            return deny(_NO_GRANT)
        if data_class is None:
            return deny("data_class_required")

        decision = deny(_NO_GRANT)
        if PeerRole.PARENT in roles:
            decision = self._parent_reads(req, data_class)
            if decision.allowed:
                return decision

        if (
            res.kind not in (ResourceKind.ASSIGNMENT, ResourceKind.QUOTE)
            or assignment_id is None
        ):
            return decision

        if PeerRole.COUNTERPART in roles and await self._relations.peer_is_client_of(
            peer_id, assignment_id
        ):
            if data_class is DataClass.ASSIGNMENT_BASIC:
                return allow("relation:counterparty")
            if data_class is DataClass.ASSIGNMENT_FINANCIAL:
                # Financial data is never pushed and never a default.
                if not req.context.on_request:
                    return deny("not_on_request")
                if not req.context.contract_allows_financial:
                    return deny("contract_excludes_financial")
                return allow("relation:counterparty")
            return deny("class_never_shared")

        if (
            PeerRole.CORPUS in roles
            and res.kind is ResourceKind.ASSIGNMENT
            and data_class is DataClass.ASSIGNMENT_BASIC
            and await self._relations.assignment_references_corpus(
                peer_id, assignment_id
            )
        ):
            return allow("relation:corpus")
        return decision

    @staticmethod
    def _parent_reads(req: AccessRequest, data_class: DataClass) -> Decision:
        """The parent instance reads A, B and staffing of the whole child instance."""
        kind = req.resource.kind
        if data_class is DataClass.ASSIGNMENT_BASIC:
            ok = kind in (ResourceKind.ASSIGNMENT, ResourceKind.QUOTE)
        elif data_class is DataClass.ASSIGNMENT_FINANCIAL:
            ok = kind in (
                ResourceKind.ASSIGNMENT,
                ResourceKind.QUOTE,
                ResourceKind.COST_ITEM,
            )
        elif data_class is DataClass.STAFFING_COUNTS:
            ok = kind in (ResourceKind.ASSIGNMENT, ResourceKind.INSTANCE)
        elif data_class in (DataClass.STAFFING, DataClass.STAFFING_ROSTER):
            if kind not in (ResourceKind.ASSIGNMENT, ResourceKind.ALLOCATION):
                return deny("not_applicable")
            if not req.context.parent_may_see_names:
                return deny("names_not_shared")
            ok = True
        else:
            return deny("class_never_shared")
        return allow("relation:parent") if ok else deny("not_applicable")
