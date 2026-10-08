"""Bootstrap of the first beheerder.

An instance starts empty, and access is pre-provisioned, so somebody has to
exist before anybody can log in. ``BOOTSTRAP_BEHEERDER_EMAILS`` names those
people. At every startup each address gets an active person with the
beheerder function. Removing an address from the variable does not take the
function away; a beheerder does that in the application.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, record_audit
from grip.core.config import Settings
from grip.models.person import Person
from grip.models.role import BEHEERDER, PersonRole
from grip.repositories.person import PersonRepository

logger = logging.getLogger(__name__)

# Stand-in beheerder for local development without an identity provider, so
# a fresh checkout is usable without configuration. The .invalid domain can
# never receive mail or match a real account.
DEV_BEHEERDER_EMAIL = "ontwikkelaar@grip.invalid"
DEV_BEHEERDER_NAME = "Lokale ontwikkelaar"


async def ensure_beheerder(db: AsyncSession, email: str, name: str = "") -> Person:
    """Make sure an active person with this email holds the beheerder function."""
    repo = PersonRepository(db)
    person = await repo.get_by_email(email)
    if person is None:
        # The name is replaced by the one from the identity provider on the
        # first login (see resolve_person_for_login).
        person = Person(name=name or email, email=email)
        db.add(person)
        await db.flush()
        record_audit(
            db,
            actor=None,
            action=CREATE,
            entity="person",
            entity_id=person.id,
            new_value={"email": email, "source": "bootstrap"},
        )
        logger.info("Bootstrap: created person %s", person.id)

    if BEHEERDER not in await repo.active_function_ids(person.id):
        grant = PersonRole(person_id=person.id, role_id=BEHEERDER)
        db.add(grant)
        await db.flush()
        record_audit(
            db,
            actor=None,
            action=CREATE,
            entity="person_role",
            entity_id=grant.id,
            new_value={
                "person_id": str(person.id),
                "role_id": BEHEERDER,
                "source": "bootstrap",
            },
        )
        logger.info("Bootstrap: granted beheerder to person %s", person.id)
    return person


async def bootstrap_beheerders(db: AsyncSession, settings: Settings) -> list[Person]:
    """Ensure the configured beheerders exist. Idempotent."""
    people = [
        await ensure_beheerder(db, email)
        for email in settings.bootstrap_beheerder_emails
    ]
    if not people and settings.DEV_NO_AUTH:
        people.append(
            await ensure_beheerder(db, DEV_BEHEERDER_EMAIL, DEV_BEHEERDER_NAME)
        )
    return people
