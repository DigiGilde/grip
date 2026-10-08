"""Who is signing: the subject behind a signing link.

A signing link is opened by someone the manager of an assignment invited by
email. That person is a guest: they see one quote and may accept or reject
it, nothing else. The decider treats them as ``Subject.for_guest`` and
matches the invitation on the verified email.

Two kinds of people arrive here:

- Someone with a person record in this instance. They are resolved by the
  normal login and get a guest subject built from the email of that record.
- Someone without a person record, who only exists as an invitation. The
  login gives them a guest session (see ``grip.core.auth.GUEST_SESSION_KEY``)
  when the identity provider vouches for their email and an invitation that
  has not expired is waiting for it. The middleware lets such a session
  through to the signing routes only.

``get_signer`` takes both; the signing routes do not tell them apart.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access.types import Subject
from grip.core.auth import GUEST_SESSION_KEY, resolve_guest, resolve_person
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.events import context as event_context
from grip.models.quote import QuoteInvitation

__all__ = [
    "GUEST_SESSION_KEY",
    "CurrentSigner",
    "Signer",
    "get_signer",
    "has_open_invitation",
    "signer_for",
    "signer_from_guest_session",
]


@dataclass(frozen=True)
class Signer:
    """The person behind a signing request, as a guest subject."""

    subject: Subject
    name: str
    email: str
    # Set when the signer has a person record in this instance.
    person_id: UUID | None = None


def signer_for(name: str, email: str, person_id: UUID | None = None) -> Signer:
    normalised = email.strip().lower()
    return Signer(
        subject=Subject.for_guest(email=normalised),
        name=name,
        email=normalised,
        person_id=person_id,
    )


def signer_from_guest_session(session: Mapping[str, Any]) -> Signer | None:
    """The signer from a guest identity in the session, or ``None``.

    Only an identity whose email the identity provider vouches for counts:
    the invitation is matched on that address, so an unverified one would
    let anyone claim an invitation.
    """
    guest = session.get(GUEST_SESSION_KEY)
    if not isinstance(guest, Mapping):
        return None
    email = guest.get("email")
    if not isinstance(email, str) or not email.strip():
        return None
    if guest.get("email_verified") is not True:
        return None
    name = guest.get("name")
    return signer_for(name if isinstance(name, str) and name else email, email)


async def has_open_invitation(
    db: AsyncSession, email: str, *, now: datetime | None = None
) -> bool:
    """Whether an invitation that has not expired is waiting for this address."""
    address = email.strip().lower()
    if not address:
        return False
    moment = now or datetime.now(UTC)
    query = select(
        exists().where(
            func.lower(QuoteInvitation.email) == address,
            or_(
                QuoteInvitation.expires_at.is_(None),
                QuoteInvitation.expires_at > moment,
            ),
        )
    )
    return bool((await db.execute(query)).scalar())


async def get_signer(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Signer:
    """Dependency: the signer behind this request. Raises 401 otherwise.

    A person of this instance signs under the email of the person record. A
    guest signs under the identity stored at login. In both cases the access
    model still decides per quote: the guest subject only matches a quote
    that address was invited for.
    """
    person = await resolve_person(request, db, settings)
    if person is not None:
        event_context.set_person(person.id)
        return signer_for(person.name, person.email or "", person.id)
    guest = await resolve_guest(request, settings)
    signer = signer_from_guest_session({GUEST_SESSION_KEY: guest}) if guest else None
    if signer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Niet ingelogd",
        )
    # Events of this request are a guest's doing. Who the guest is stays in
    # the evidence of the decision, not in the stream.
    event_context.set_guest(None)
    return signer


CurrentSigner = Annotated[Signer, Depends(get_signer)]
