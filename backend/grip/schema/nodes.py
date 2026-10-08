"""Shapes of the node picker and of resolved context.

A node comes from a corpus system, under the contract this instance has
with that corpus. What the picker shows is context of an assignment, so
every field is class A (assignment basics).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

A = in_class(DataClass.ASSIGNMENT_BASIC)


class NodeOrganisationOut(BaseModel):
    name: Annotated[str | None, A] = None
    tooi_uri: Annotated[str | None, A] = None


class NodeOut(BaseModel):
    uri: Annotated[str, A]
    type: Annotated[str, A]
    title: Annotated[str, A]
    description: Annotated[str | None, A] = None
    status: Annotated[str | None, A] = None
    # Base URI of the corpus that manages the node.
    corpus: Annotated[str | None, A] = None
    managing_organisation: Annotated[NodeOrganisationOut | None, nested()] = None
    valid_from: Annotated[date | None, A] = None
    valid_until: Annotated[date | None, A] = None
    # Title and status are as of this date.
    peildatum: Annotated[date | None, A] = None
    # Per-type details as the corpus gives them (kind of instrument, reference
    # of a political input). Domain vocabulary of the corpus, shown as is.
    type_details: Annotated[dict[str, Any] | None, A] = None


class EdgeOut(BaseModel):
    from_uri: Annotated[str, A]
    to_uri: Annotated[str, A]
    type: Annotated[str, A]


class ChainOut(BaseModel):
    """The way from a node up to the political input it follows from."""

    nodes: Annotated[list[NodeOut], nested()] = Field(default_factory=list)
    edges: Annotated[list[EdgeOut], nested()] = Field(default_factory=list)
    # Nodes of another corpus the chain runs into; not followed.
    external_node_uris: Annotated[list[str], A] = Field(default_factory=list)
    complete: Annotated[bool, A] = True


class CorpusOut(BaseModel):
    base_uri: Annotated[str, A]
    name: Annotated[str, A]
    # Whether a search can be sent: a contract and an outway are in place.
    searchable: Annotated[bool, A]


class CorporaOut(BaseModel):
    corpora: Annotated[list[CorpusOut], nested()] = Field(default_factory=list)
    # Why no corpus can be searched, when that is so.
    problem: Annotated[str | None, A] = None


class NodeSearchOut(BaseModel):
    results: Annotated[list[NodeOut], nested()] = Field(default_factory=list)
    page: Annotated[int, A] = 1
    page_size: Annotated[int, A] = 20
    total: Annotated[int, A] = 0
    # Why there is no answer, when the corpus could not be asked.
    problem: Annotated[str | None, A] = None


class NodeLookupOut(BaseModel):
    uri: Annotated[str, A]
    resolved: Annotated[bool, A]
    # Why the URI stays a bare URI, when it could not be resolved.
    problem: Annotated[str | None, A] = None
    node: Annotated[NodeOut | None, nested()] = None
    chain: Annotated[ChainOut | None, nested()] = None


class ContextOut(BaseModel):
    """The context of an assignment, resolved as of a date."""

    peildatum: Annotated[date, A]
    # The day the quote was accepted, offered as an alternative peildatum.
    acceptance_date: Annotated[date | None, A] = None
    items: Annotated[list[NodeLookupOut], nested()] = Field(default_factory=list)
