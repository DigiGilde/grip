"""FastAPI glue: who is asking, and refuse when the decider says no.

Routes depend on ``CurrentSubject`` and ``AccessDecider`` and call
``require`` (or ``permitted_classes`` for a response with several data
classes). They never look at functions or relations themselves.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access.decider import Decider, LocalDecider, decide
from grip.access.relations import RelationSource
from grip.access.sql import SqlRelationSource
from grip.access.types import Action, Context, DataClass, Decision, Resource, Subject
from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.repositories.person import PersonRepository


async def get_subject(
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
) -> Subject:
    """The logged-in person as a subject, with the functions held today."""
    functions = await PersonRepository(db).active_function_ids(person.id)
    return Subject.for_person(person.id, frozenset(functions))


def get_relation_source(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RelationSource:
    return SqlRelationSource(db, instance_base_uri=settings.INSTANCE_BASE_URI)


def get_decider(relations: RelationSource = Depends(get_relation_source)) -> Decider:
    """The decision point. Swap this dependency to decide somewhere else."""
    return LocalDecider(relations)


CurrentSubject = Annotated[Subject, Depends(get_subject)]
AccessDecider = Annotated[Decider, Depends(get_decider)]


async def require(
    decider: Decider,
    subject: Subject,
    action: Action,
    resource: Resource,
    data_class: DataClass | None = None,
    context: Context | None = None,
    *,
    hide_existence: bool = False,
) -> Decision:
    """Return the decision when allowed; raise otherwise.

    Raises 403, or 404 with ``hide_existence`` when knowing that the resource
    exists is itself something the subject must not learn.
    """
    decision = await decide(decider, subject, action, resource, data_class, context)
    if decision.allowed:
        return decision
    if hide_existence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Niet gevonden"
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Je hebt hier geen toegang toe",
    )
