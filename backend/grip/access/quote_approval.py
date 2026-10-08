"""Access rules for the internal approval of a quote.

Internal approval is a step inside the organisation that made the quote:
someone with the right to do so approves a quote before it is offered. The
rules, as an addition to the matrix:

- Ask for approval (``REQUEST_QUOTE_APPROVAL``): the owner or a manager of
  the assignment the quote belongs to. Taking back an open request is part
  of asking.
- Approve or send back (``DECIDE_QUOTE_APPROVAL``): a person who holds the
  right ``offertegoedkeurder``. Taking back an approval is part of deciding.
  Whether the same person who asked may also decide is not an access rule
  but a rule of the procedure; the service that records the decision
  enforces it.
- Read a quote in full to decide on it: the holder of that right reads
  classes A and B of a quote for which approval was asked, even without any
  other relation to the assignment. Exactly as a tekenbevoegde or an invited
  signer reads the quote they sign. Nothing else of the assignment opens up:
  no budget lines, no staffing, no other quotes.
- Reading where a quote stands with approval is class A of that quote, for
  whoever may read the quote; that needs no rule here.
- Guests and peers get nothing here. Internal approval is knowledge of this
  organisation and never leaves it.

The rule about reading needs one fact that is not a relation between the
subject and the quote: whether approval was asked for this quote. The caller
looks it up and passes it as a resource property (``quote_resource``), so an
external decision point receives it with the request.

``evaluate`` answers only the questions these rules are about and returns
``None`` for every other, which then goes to the matrix as before.
"""

from __future__ import annotations

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

# The right to approve quotes internally. A right is a function in code.
OFFERTEGOEDKEURDER = "offertegoedkeurder"

APPROVAL_REQUESTED = "approval_requested"

_NO_GRANT = "no_grant"
_READS_IN_FULL = (DataClass.ASSIGNMENT_BASIC, DataClass.ASSIGNMENT_FINANCIAL)


def quote_resource(
    quote_id: UUID, assignment_id: UUID, *, approval_requested: bool
) -> Resource:
    """A quote as a resource, with the fact the reading rule needs."""
    properties = ((APPROVAL_REQUESTED, "true"),) if approval_requested else ()
    return Resource(
        ResourceKind.QUOTE,
        id=quote_id,
        assignment_id=assignment_id,
        properties=properties,
    )


def _approval_was_requested(resource: Resource) -> bool:
    return (APPROVAL_REQUESTED, "true") in resource.properties


async def evaluate(
    relations: RelationSource, request: AccessRequest
) -> Decision | None:
    """The decision when one of these rules applies; ``None`` otherwise."""
    action, resource, subject = request.action, request.resource, request.subject
    approval_action = action in (
        Action.REQUEST_QUOTE_APPROVAL,
        Action.DECIDE_QUOTE_APPROVAL,
    )
    if subject.kind is not SubjectKind.PERSON or subject.person_id is None:
        # Not for guests, not for peers.
        return deny(_NO_GRANT) if approval_action else None

    if action is Action.DECIDE_QUOTE_APPROVAL:
        if resource.kind is not ResourceKind.QUOTE:
            return deny("not_applicable")
        if OFFERTEGOEDKEURDER in subject.functions:
            return allow(f"function:{OFFERTEGOEDKEURDER}")
        return deny(_NO_GRANT)

    if action is Action.REQUEST_QUOTE_APPROVAL:
        if resource.kind is not ResourceKind.QUOTE or resource.assignment_id is None:
            return deny("not_applicable")
        role = await relations.assignment_role(
            subject.person_id, resource.assignment_id
        )
        return allow(f"relation:{role.value}") if role is not None else deny(_NO_GRANT)

    if (
        action is Action.READ
        and resource.kind is ResourceKind.QUOTE
        and resource.id is not None
        and request.data_class in _READS_IN_FULL
        and OFFERTEGOEDKEURDER in subject.functions
        and _approval_was_requested(resource)
    ):
        return allow(f"function:{OFFERTEGOEDKEURDER}")
    return None
