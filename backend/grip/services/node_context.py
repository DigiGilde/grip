"""What a reader needs from the chain of a context node.

A corpus answers with a chain: the nodes and edges between a node and the
political input(s) it follows from. A screen does not want that graph; it
wants the answer to "where does this come from?". This module turns a chain
into that answer: the political inputs at the end, and per end point one
path of steps with the relation between them.

Pure functions over the chain in code names, so they are tested without a
corpus. Nothing here asks a corpus.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

POLITICAL_INPUT = "politieke_input"


@dataclass(frozen=True)
class Step:
    """One node on a path, with the relation to the next step."""

    uri: str
    title: str | None = None
    type: str | None = None
    # The step lies in another corpus than the node the path starts at.
    external: bool = False
    # Type of the edge between this step and the next; None on the last step.
    edge_type: str | None = None


@dataclass(frozen=True)
class Path:
    """From the node up to one end point: a political input or another corpus."""

    steps: tuple[Step, ...]

    @property
    def end(self) -> Step:
        return self.steps[-1]


@dataclass(frozen=True)
class Origin:
    uri: str
    title: str


@dataclass(frozen=True)
class ChainSummary:
    # The political inputs the node follows from, nearest first.
    origins: tuple[Origin, ...] = ()
    # Steps from the node to its nearest political input; None without one.
    steps_to_origin: int | None = None
    paths: tuple[Path, ...] = ()
    # Every node the chain passes, the start excluded.
    passed_uris: frozenset[str] = field(default_factory=frozenset)


def _neighbours(edges: list[dict[str, Any]]) -> dict[str, list[tuple[str, str]]]:
    """Per node the nodes one edge away, with the edge type. Direction is not
    followed: a chain is the set of edges that connect, whichever way each
    relation happens to be worded."""
    found: dict[str, list[tuple[str, str]]] = {}
    for edge in edges:
        source, target, kind = edge.get("from"), edge.get("to"), edge.get("type")
        if not source or not target:
            continue
        found.setdefault(source, []).append((target, kind or ""))
        found.setdefault(target, []).append((source, kind or ""))
    return found


def summarise(chain: dict[str, Any] | None, start_uri: str) -> ChainSummary:
    """The end points of a chain and the shortest path to each.

    A political input ends a path, and so does a node of another corpus
    (the corpus lists those in ``external_node_uris`` and does not follow
    them). A chain without either gives no paths: the node stands alone.
    """
    if not chain:
        return ChainSummary()
    nodes = {node["uri"]: node for node in chain.get("nodes") or [] if node.get("uri")}
    external = [uri for uri in chain.get("external_node_uris") or [] if uri]
    start = chain.get("start") or start_uri
    neighbours = _neighbours(chain.get("edges") or [])

    # Breadth first from the start: the first time a node is reached is by a
    # shortest path. An end point is not walked through.
    previous: dict[str, tuple[str, str] | None] = {start: None}
    order: list[str] = []
    queue = deque([start])
    while queue:
        current = queue.popleft()
        order.append(current)
        is_end = current != start and (
            current in external or nodes.get(current, {}).get("type") == POLITICAL_INPUT
        )
        if is_end:
            continue
        for neighbour, kind in neighbours.get(current, []):
            if neighbour not in previous:
                previous[neighbour] = (current, kind)
                queue.append(neighbour)

    def path_to(end: str) -> Path:
        trail: list[tuple[str, str | None]] = []
        cursor: str | None = end
        edge_after: str | None = None
        while cursor is not None:
            trail.append((cursor, edge_after))
            link = previous[cursor]
            if link is None:
                break
            cursor, edge_after = link
        trail.reverse()
        return Path(
            steps=tuple(
                Step(
                    uri=uri,
                    title=nodes.get(uri, {}).get("title"),
                    type=nodes.get(uri, {}).get("type"),
                    external=uri in external and uri not in nodes,
                    edge_type=edge or None,
                )
                for uri, edge in trail
            )
        )

    ends = [
        uri
        for uri in order
        if uri != start
        and (uri in external or nodes.get(uri, {}).get("type") == POLITICAL_INPUT)
    ]
    paths = tuple(path_to(uri) for uri in ends)
    origin_paths = [path for path in paths if path.end.type == POLITICAL_INPUT]
    return ChainSummary(
        origins=tuple(
            Origin(uri=path.end.uri, title=path.end.title or path.end.uri)
            for path in origin_paths
        ),
        steps_to_origin=min(
            (len(path.steps) - 1 for path in origin_paths), default=None
        ),
        paths=paths,
        passed_uris=frozenset(uri for uri in order if uri != start),
    )


def nearest_linked(
    summary: ChainSummary, own_uri: str, linked_uris: list[str]
) -> str | None:
    """Another linked node that this node's chain passes through, nearest first.

    When an assignment links an instrument and the goal above it, the
    instrument "falls under" the goal: its chain need not be told again.
    """
    others = {uri for uri in linked_uris if uri != own_uri}
    best: tuple[int, str] | None = None
    for path in summary.paths:
        for distance, step in enumerate(path.steps[1:], start=1):
            if step.uri in others and (best is None or distance < best[0]):
                best = (distance, step.uri)
                break
    return best[1] if best else None
