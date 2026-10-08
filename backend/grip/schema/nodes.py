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


class OriginOut(BaseModel):
    """A political input a node follows from, or another linked node."""

    uri: Annotated[str, A]
    title: Annotated[str, A]


class PathStepOut(BaseModel):
    uri: Annotated[str, A]
    title: Annotated[str | None, A] = None
    type: Annotated[str | None, A] = None
    # The step lies in another corpus than the node the path starts at.
    external: Annotated[bool, A] = False
    # Name of the corpus the step lies in, when this instance knows it.
    corpus_name: Annotated[str | None, A] = None
    # Whether this instance can ask the corpus of the step for the node.
    resolvable: Annotated[bool, A] = False
    # Type of the edge between this step and the next; absent on the last.
    edge_type: Annotated[str | None, A] = None


class PathOut(BaseModel):
    """From a node up to one end point, step by step."""

    steps: Annotated[list[PathStepOut], nested()] = Field(default_factory=list)


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
    # Name of the corpus that manages the node, when this instance knows it.
    corpus_name: Annotated[str | None, A] = None
    # The political inputs at the end of the chain, nearest first.
    origins: Annotated[list[OriginOut], nested()] = Field(default_factory=list)
    # Steps from the node to its nearest political input.
    steps_to_origin: Annotated[int | None, A] = None
    # Per end point one path: to a political input, or into another corpus.
    paths: Annotated[list[PathOut], nested()] = Field(default_factory=list)
    # Another linked node this node's chain passes through, so the chain is
    # told once. Only set in the context of an assignment.
    falls_under: Annotated[OriginOut | None, nested()] = None


class ContextOut(BaseModel):
    """The context of an assignment, resolved as of a date."""

    peildatum: Annotated[date, A]
    # The day the quote was accepted, offered as an alternative peildatum.
    acceptance_date: Annotated[date | None, A] = None
    # Why nothing could be resolved at all, when no corpus can be asked.
    # Said once here instead of on every item.
    notice: Annotated[str | None, A] = None
    items: Annotated[list[NodeLookupOut], nested()] = Field(default_factory=list)
