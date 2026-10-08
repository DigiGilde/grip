"""Carrying out a decision in the domain, with the values of its statement.

One function per channel and action. Each gets the values read from the
signed statement (``grip.proof.statement.columns``) and passes exactly those
on, so the record in the domain cannot say something the statement does not.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grip.federation.bridge.acceptance import (
    accept_received_quote,
    reject_received_quote,
)
from grip.models.decision_proof import DecisionEvidence, SigningIntent
from grip.models.person import Person
from grip.models.quote import Quote
from grip.services import quote_approval, quotes
from grip.services.errors import DomainValidationError


async def execute(
    db: AsyncSession,
    intent: SigningIntent,
    quote: Quote,
    person: Person | None,
    values: dict[str, Any],
    evidence: DecisionEvidence,
) -> None:
    proof = {"evidence_id": evidence.id, "statement_hash": evidence.statement_hash}
    kind = (values["channel"], values["action"])

    if kind == ("signing_link", "accept"):
        await quotes.accept_quote(
            db,
            quote.id,
            quote_hash=values["quote_hash"],
            signer_name=values["signer_name"],
            signer_email=values["signer_email"],
            signer_function=values["signer_function"],
            signer_person_id=person.id if person is not None else None,
            organisation=values["organisation"] or {},
            form="signing_link",
            actor=person,
            signed_at=values["decided_at"],
            **proof,
        )
    elif kind == ("signing_link", "reject"):
        await quotes.reject_quote(
            db,
            quote.id,
            quote_hash=values["quote_hash"],
            actor=person,
            reason=values["note"],
            organisation=values["organisation"],
            rejected_at=values["decided_at"],
            **proof,
        )
    elif person is None:
        raise DomainValidationError(
            "Dit besluit kan alleen een persoon van deze instantie nemen."
        )
    elif kind == ("own_instance", "accept"):
        await accept_received_quote(
            db,
            quote.id,
            actor=person,
            signer_function=values["signer_function"],
            signed_at=values["decided_at"],
            **proof,
        )
    elif kind == ("own_instance", "reject"):
        await reject_received_quote(
            db,
            quote.id,
            actor=person,
            reason=values["note"],
            rejected_at=values["decided_at"],
            **proof,
        )
    elif kind in (("internal", "approve"), ("internal", "send_back")):
        await quote_approval.decide(
            db,
            quote.id,
            approve=values["action"] == "approve",
            actor=person,
            quote_hash=values["quote_hash"],
            note=values["note"],
            decided_at=values["decided_at"],
            **proof,
        )
    else:
        raise DomainValidationError(f"Onbekend besluit: {kind}")
