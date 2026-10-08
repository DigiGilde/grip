"""Fetch the context of an assignment from its corpus, for a prompt.

One function for every caller that drafts text about an assignment (a
section of a quote, a vacancy text). The corpus is a help, never a
condition: when it cannot be asked, the answer says so and the draft is
made without it.

This module does not know how a corpus is reached. The caller hands it a
client with ``get_node`` and ``get_chain`` (the one the context sheet uses,
so the model gets what a person sees).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.assignment import Assignment
from grip.services import context_brief

logger = logging.getLogger(__name__)

# More references than this say little more about why, and cost a call each.
MAX_LINKED_NODES = 5

CONTEXT_USED = "used"
CONTEXT_NONE = "none"
CONTEXT_UNREACHABLE = "unreachable"


class Corpus(Protocol):
    async def get_node(
        self, db: AsyncSession, uri: str, *, peildatum: date | None = None
    ) -> dict[str, Any]: ...

    async def get_chain(
        self, db: AsyncSession, uri: str, *, peildatum: date | None = None
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class FetchedContext:
    lines: tuple[str, ...] = ()
    # "used", "none" (the assignment refers to nothing) or "unreachable"
    # (it does, and no corpus could be asked).
    state: str = CONTEXT_NONE
    dropped: tuple[str, ...] = ()


async def for_assignment(
    db: AsyncSession,
    assignment: Assignment | None,
    *,
    corpus: Corpus,
    reachable: bool,
    corpus_name: Callable[[str], str | None] = lambda uri: None,
    budget: int = context_brief.DEFAULT_BUDGET,
) -> FetchedContext:
    """The context block for this assignment and what became of asking."""
    linked = list(assignment.context_refs or []) if assignment is not None else []
    if not linked:
        return FetchedContext()
    if not reachable:
        return FetchedContext(state=CONTEXT_UNREACHABLE)
    found: list[context_brief.LinkedNode] = []
    for uri in linked[:MAX_LINKED_NODES]:
        try:
            node = await corpus.get_node(db, uri)
        except Exception:  # whatever the reason, the draft goes on without it
            logger.info("Context node %s could not be fetched", uri, exc_info=True)
            continue
        try:
            chain = await corpus.get_chain(db, uri)
        except Exception:
            logger.info("Chain of %s could not be fetched", uri, exc_info=True)
            chain = None
        found.append(context_brief.LinkedNode(node=node, chain=chain))
    if not found:
        return FetchedContext(state=CONTEXT_UNREACHABLE)
    brief = context_brief.build(found, corpus_name=corpus_name, budget=budget)
    return FetchedContext(lines=brief.lines, state=CONTEXT_USED, dropped=brief.dropped)
