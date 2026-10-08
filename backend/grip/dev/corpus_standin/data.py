"""The fictional corpus and the answers of corpus-context v1 built from it.

Pure functions over the data file; the ASGI app in ``app.py`` only does HTTP.
The field names of the answers are those of the contract (Dutch).
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).with_name("corpus.json")
NODE_SEGMENT = "/id/node/"
POLITICAL_INPUT = "politieke_input"
# Edge types that do not count when building a chain (see the contract).
IGNORED_IN_CHAIN = frozenset({"verwijst_naar", "conflicteert_met"})
DEFAULT_MAX_DEPTH = 6


@dataclass(frozen=True)
class Corpus:
    key: str
    base: str
    name: str
    peer_id: str
    grant_hash: str
    organisation: dict[str, Any]
    nodes: tuple[dict[str, Any], ...]
    # (from uri, to uri, type, description)
    edges: tuple[tuple[str, str, str, str | None], ...]

    def uri(self, node_id: str) -> str:
        return f"{self.base}{NODE_SEGMENT}{node_id}"

    def node_by_id(self, node_id: str) -> dict[str, Any] | None:
        return next((n for n in self.nodes if n["id"] == node_id), None)

    def node_by_key(self, key: str) -> dict[str, Any]:
        return next(n for n in self.nodes if n["key"] == key)

    def owns(self, uri: str) -> bool:
        return uri.startswith(self.base + NODE_SEGMENT)


def _load() -> list[Corpus]:
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    found = []
    for item in raw["corpora"]:
        base = item["corpus"].rstrip("/")
        by_key = {n["key"]: f"{base}{NODE_SEGMENT}{n['id']}" for n in item["nodes"]}
        edges = []
        for edge in item["edges"]:
            source, target, kind, *rest = edge
            edges.append(
                (
                    by_key.get(source, source),
                    by_key.get(target, target),
                    kind,
                    rest[0] if rest else None,
                )
            )
        found.append(
            Corpus(
                key=item["key"],
                base=base,
                name=item["naam"],
                peer_id=item["peer_id"],
                grant_hash=item["grant_hash"],
                organisation=item["beherende_organisatie"],
                nodes=tuple(item["nodes"]),
                edges=tuple(edges),
            )
        )
    return found


@cache
def corpora() -> tuple[Corpus, ...]:
    return tuple(_load())


def corpus_by_key(key: str) -> Corpus:
    return next(c for c in corpora() if c.key == key)


def corpus_by_grant_hash(grant_hash: str) -> Corpus | None:
    return next((c for c in corpora() if c.grant_hash == grant_hash), None)


def node_uri(corpus_key: str, node_key: str) -> str:
    """The URI of a node of the fictional corpus, by its keys in the data file."""
    corpus = corpus_by_key(corpus_key)
    return corpus.uri(corpus.node_by_key(node_key)["id"])


def _title_on(node: dict[str, Any], peildatum: date) -> str:
    """The title as of a date; before the first version, the first title."""
    history = sorted(node.get("titel_historie") or [], key=lambda v: v["vanaf"])
    if not history:
        return str(node["titel"])
    current = history[0]["titel"]
    for version in history:
        if date.fromisoformat(version["vanaf"]) <= peildatum:
            current = version["titel"]
    return str(current)


def node_view(corpus: Corpus, node: dict[str, Any], peildatum: date) -> dict[str, Any]:
    view: dict[str, Any] = {
        "uri": corpus.uri(node["id"]),
        "type": node["type"],
        "titel": _title_on(node, peildatum),
        "omschrijving": node.get("omschrijving"),
        "status": node.get("status", "actief"),
        "geldigheid": {"begindatum": node["geldig_vanaf"], "einddatum": None},
        "beherende_organisatie": corpus.organisation,
        "corpus": corpus.base,
        "peildatum": peildatum.isoformat(),
    }
    if node.get("type_details"):
        view["type_details"] = node["type_details"]
    return view


def corpus_info(corpus: Corpus, contract_version: str) -> dict[str, Any]:
    return {
        "corpus": corpus.base,
        "naam": corpus.name,
        "beherende_organisatie": corpus.organisation,
        "contractversie": contract_version,
    }


def search(
    corpus: Corpus,
    *,
    q: str | None,
    types: list[str],
    peildatum: date,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    needle = (q or "").strip().lower()
    matches = []
    for node in corpus.nodes:
        if types and node["type"] not in types:
            continue
        view = node_view(corpus, node, peildatum)
        haystack = f"{view['titel']} {view['omschrijving'] or ''}".lower()
        if needle and needle not in haystack:
            continue
        matches.append(view)
    start = (page - 1) * page_size
    return {
        "resultaten": matches[start : start + page_size],
        "page": page,
        "page_size": page_size,
        "totaal": len(matches),
    }


def chain(
    corpus: Corpus, node_id: str, peildatum: date, max_depth: int = DEFAULT_MAX_DEPTH
) -> dict[str, Any] | None:
    """The shortest paths from a node to every reachable political input.

    Edges are followed in both directions. A political input is an end
    point. An edge to a node of another corpus is listed with its URI under
    ``externe_node_uris`` and is not followed.
    """
    start_node = corpus.node_by_id(node_id)
    if start_node is None:
        return None
    start = corpus.uri(node_id)
    by_uri = {corpus.uri(n["id"]): n for n in corpus.nodes}

    neighbours: dict[str, list[tuple[str, int]]] = {}
    for index, (source, target, kind, _) in enumerate(corpus.edges):
        if kind in IGNORED_IN_CHAIN:
            continue
        neighbours.setdefault(source, []).append((target, index))
        neighbours.setdefault(target, []).append((source, index))

    depth = {start: 0}
    # Every predecessor on a shortest path, with the edge that leads there.
    previous: dict[str, list[tuple[str, int]]] = {}
    queue = deque([start])
    complete = True
    while queue:
        current = queue.popleft()
        if current not in by_uri:
            continue  # a node of another corpus: not followed
        if by_uri[current]["type"] == POLITICAL_INPUT:
            continue  # an end point, also when it is the start
        if depth[current] >= max_depth:
            if neighbours.get(current):
                complete = False
            continue
        for other, index in neighbours.get(current, []):
            if other not in depth:
                depth[other] = depth[current] + 1
                previous[other] = [(current, index)]
                queue.append(other)
            elif depth[other] == depth[current] + 1:
                previous[other].append((current, index))

    on_path = {start}
    edge_indexes: set[int] = set()
    stack = [
        uri
        for uri in depth
        if uri in by_uri and by_uri[uri]["type"] == POLITICAL_INPUT and uri != start
    ]
    while stack:
        uri = stack.pop()
        if uri in on_path and uri != start:
            continue
        on_path.add(uri)
        for parent, index in previous.get(uri, []):
            edge_indexes.add(index)
            stack.append(parent)

    external: list[str] = []
    for index, (source, target, kind, _) in enumerate(corpus.edges):
        if kind in IGNORED_IN_CHAIN:
            continue
        for inside, outside in ((source, target), (target, source)):
            if inside in on_path and outside not in by_uri:
                edge_indexes.add(index)
                if outside not in external:
                    external.append(outside)

    ordered = sorted(on_path, key=lambda uri: (depth[uri], uri))
    return {
        "start": start,
        "peildatum": peildatum.isoformat(),
        "nodes": [node_view(corpus, by_uri[uri], peildatum) for uri in ordered],
        "edges": [
            {
                "van": corpus.edges[i][0],
                "naar": corpus.edges[i][1],
                "type": corpus.edges[i][2],
                "omschrijving": corpus.edges[i][3],
            }
            for i in sorted(edge_indexes)
        ],
        "externe_node_uris": external,
        "volledig": complete,
    }
