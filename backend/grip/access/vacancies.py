"""Access rules for vacancies, form templates and the language model.

A vacancy and its request form belong to data class C (staffing): they hold
names of colleagues. Three views exist on a vacancy, each wider one
including the narrower ones:

- ``STAFFING``: everything, including the names of the requester, the
  addressee, the advisers and the approver, their notes, and the request
  form.
- ``STAFFING_COUNTS``: the vacancy without any name: status, type, the steps
  of the procedure, the decisions as yes or no, the text versions.
- ``OPEN_ROLE``: function, scale, FTE, period and the established text of a
  vacancy that is published.

Who gets what:

- Create and edit (``EDIT``): a beheerder, a planner, and the owner or
  manager of the assignment the budget line belongs to. A vacancy without a
  budget line has no assignment, so only beheerder and planner edit it.
  Drafting a text with the language model is editing.
- Read ``STAFFING``: whoever may edit, plus a person named as adviser or
  approver on the vacancy (they have to see the request they decide on).
- Read ``STAFFING_COUNTS``: those, plus a lezer.
- Read ``OPEN_ROLE``: those, plus every person of the instance when the
  vacancy is published and has an established text.
- Read ``MASTER_DATA`` on a vacancy: the value lists (types, steps,
  channels) and whether drafting is available. Every person of the instance.
- Record an advice or the approval (``RECORD_DECISION``): a beheerder, or
  the person named for that decision when that person has an account.
  Putting the name of an adviser on the vacancy without a decision is
  editing.
- Form templates and the configuration of the language model: beheerder
  only, for every action.
- Guests and peers get nothing here. What goes to another instance about a
  vacancy leaves through the federation module, not through these rules.

The rules need three facts about a vacancy that are not relations between a
subject and an object: whether it is an open role, and who is named for
which decision. The caller looks them up and passes them as resource
properties (``vacancy_resource``), so an external decision point receives
them with the request.
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from grip.access.relations import RelationSource
from grip.access.types import (
    AccessRequest,
    Action,
    DataClass,
    Decision,
    Resource,
    ResourceKind,
    SubjectKind,
    allow,
    deny,
)

KINDS = frozenset(
    {ResourceKind.VACANCY, ResourceKind.FORM_TEMPLATE, ResourceKind.LANGUAGE_MODEL}
)

# Function ids, the same as in grip.access.decider (which imports this
# module, so they cannot be imported from there).
_BEHEERDER = "beheerder"
_PLANNER = "planner"
_LEZER = "lezer"

DECISION_KINDS = ("hr_advice", "control_advice", "approval")

_OPEN_ROLE = "open_role"
_DECISION_KIND = "decision_kind"
_NO_GRANT = "no_grant"


def _named_property(kind: str) -> str:
    return f"{kind}_person_id"


def vacancy_resource(
    vacancy_id: UUID | None = None,
    *,
    assignment_id: UUID | None = None,
    open_role: bool = False,
    named: Mapping[str, UUID | None] | None = None,
    decision_kind: str | None = None,
) -> Resource:
    """A vacancy as the resource of a decision.

    ``assignment_id`` is the assignment of the budget line, if there is one.
    ``open_role`` says the vacancy is published with an established text.
    ``named`` maps a decision kind to the person named for it.
    ``decision_kind`` is the decision a ``RECORD_DECISION`` request is about.
    ``vacancy_id=None`` stands for a vacancy that does not exist yet, or for
    the collection.
    """
    properties: list[tuple[str, str]] = []
    if open_role:
        properties.append((_OPEN_ROLE, "true"))
    for kind, person_id in sorted((named or {}).items()):
        if kind in DECISION_KINDS and person_id is not None:
            properties.append((_named_property(kind), str(person_id)))
    if decision_kind is not None:
        properties.append((_DECISION_KIND, decision_kind))
    return Resource(
        ResourceKind.VACANCY,
        id=vacancy_id,
        assignment_id=assignment_id,
        properties=tuple(properties),
    )


def form_template_resource(template_id: UUID | None = None) -> Resource:
    return Resource(ResourceKind.FORM_TEMPLATE, id=template_id)


def language_model_resource() -> Resource:
    return Resource(ResourceKind.LANGUAGE_MODEL)


async def evaluate(relations: RelationSource, req: AccessRequest) -> Decision:
    """Decide a request about a vacancy, a form template or the model."""
    if req.subject.kind is not SubjectKind.PERSON:
        return deny("not_applicable")
    if req.subject.person_id is None:
        return deny("no_identity")
    functions = req.subject.functions

    if req.resource.kind is not ResourceKind.VACANCY:
        if _BEHEERDER in functions:
            return allow("function:beheerder")
        return deny(_NO_GRANT)

    if req.action is Action.EDIT:
        reason = await _editor_reason(relations, req)
        return allow(reason) if reason else deny(_NO_GRANT)
    if req.action is Action.RECORD_DECISION:
        return _records_decision(req)
    if req.action is Action.READ:
        return await _reads(relations, req)
    return deny("not_applicable")


async def _editor_reason(relations: RelationSource, req: AccessRequest) -> str | None:
    functions = req.subject.functions
    if _BEHEERDER in functions:
        return "function:beheerder"
    if _PLANNER in functions:
        return "function:planner"
    assignment_id = req.resource.assignment_id
    person_id = req.subject.person_id
    if assignment_id is None or person_id is None:
        return None
    role = await relations.assignment_role(person_id, assignment_id)
    return f"relation:{role.value}" if role is not None else None


def _is_named(req: AccessRequest, kinds: tuple[str, ...] = DECISION_KINDS) -> bool:
    me = str(req.subject.person_id)
    return any(req.resource.property(_named_property(kind)) == me for kind in kinds)


def _records_decision(req: AccessRequest) -> Decision:
    if _BEHEERDER in req.subject.functions:
        return allow("function:beheerder")
    kind = req.resource.property(_DECISION_KIND)
    if kind in DECISION_KINDS and _is_named(req, (kind,)):
        return allow("relation:named_decider")
    return deny(_NO_GRANT)


async def _reads(relations: RelationSource, req: AccessRequest) -> Decision:
    data_class = req.data_class
    if data_class is None:
        return deny("data_class_required")
    if data_class is DataClass.MASTER_DATA:
        # The value lists and whether drafting is available: nothing about
        # any vacancy, so every person of the instance may read it.
        return allow("active_person")
    if data_class not in (
        DataClass.STAFFING,
        DataClass.STAFFING_COUNTS,
        DataClass.OPEN_ROLE,
    ):
        return deny("not_applicable")

    reason = await _editor_reason(relations, req)
    if reason:
        return allow(reason)
    if req.resource.id is not None and _is_named(req):
        return allow("relation:named_decider")
    if data_class is DataClass.STAFFING:
        return deny(_NO_GRANT)

    if _LEZER in req.subject.functions:
        return allow("function:lezer")
    if data_class is DataClass.STAFFING_COUNTS:
        return deny(_NO_GRANT)

    if req.resource.property(_OPEN_ROLE) == "true":
        return allow("active_person")
    return deny(_NO_GRANT)
