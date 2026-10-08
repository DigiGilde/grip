"""Why an assignment exists, as text a language model can use.

An assignment refers to nodes in a corpus. Behind each node lies a chain up
to the political input it follows from. A person reads that chain in the
context sheet; this module writes the same content down for a prompt: per
referenced node what it is, and then the chain upward, level by level, with
the relation in words and every branch kept.

Pure functions over nodes and chains in code names, as the corpus client
returns them. Nothing here asks a corpus; ``grip.services.context_fetch``
does that.

The text has a budget in characters. Titles, kinds and relations always go
in. Descriptions are added nearest level first, after the descriptions of
the political inputs, which always go in. What does not fit is left out
and named in ``dropped``.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

POLITICAL_INPUT = "politieke_input"

DEFAULT_BUDGET = 6000
NODE_DESCRIPTION_CHARS = 900
CHAIN_DESCRIPTION_CHARS = 450
# A chain deeper than this is cut: it would no longer say why this assignment.
MAX_DEPTH = 8

_NODE_KINDS = {
    "politieke_input": ("de", "politieke input"),
    "dossier": ("het", "dossier"),
    "doel": ("het", "doel"),
    "instrument": ("het", "instrument"),
    "beleidskader": ("het", "beleidskader"),
    "maatregel": ("de", "maatregel"),
    "probleem": ("het", "probleem"),
    "effect": ("het", "effect"),
    "beleidsoptie": ("de", "beleidsoptie"),
    "bron": ("de", "bron"),
}

# The relation as the lower node has it to the higher one ...
_FORWARD = {
    "implementeert": "implementeert",
    "draagt_bij_aan": "draagt bij aan",
    "vloeit_voort_uit": "volgt uit",
    "vereist": "vereist",
    "evalueert": "evalueert",
    "vervangt": "vervangt",
    "onderdeel_van": "is onderdeel van",
    "leidt_tot": "leidt tot",
    "adresseert": "adresseert",
    "meet": "meet",
    "verwijst_naar": "verwijst naar",
    "conflicteert_met": "conflicteert met",
}
# ... and when the corpus recorded it the other way round.
_BACKWARD = {
    "implementeert": "wordt uitgevoerd door",
    "draagt_bij_aan": "krijgt een bijdrage van",
    "vloeit_voort_uit": "is de oorsprong van",
    "vereist": "is een voorwaarde voor",
    "evalueert": "wordt geëvalueerd door",
    "vervangt": "is vervangen door",
    "onderdeel_van": "omvat",
    "leidt_tot": "is een gevolg van",
    "adresseert": "wordt aangepakt door",
    "meet": "wordt gemeten door",
    "verwijst_naar": "wordt genoemd in",
    "conflicteert_met": "conflicteert met",
}


@dataclass(frozen=True)
class LinkedNode:
    """A node an assignment refers to, with the chain behind it."""

    node: dict[str, Any]
    chain: dict[str, Any] | None = None


@dataclass(frozen=True)
class ContextBrief:
    # The block, line by line, ready to put in a prompt. Empty without context.
    lines: tuple[str, ...] = ()
    # How many referenced nodes the block describes.
    node_count: int = 0
    # What was left out to stay within the budget, in words.
    dropped: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass
class _Entry:
    """One printed item: a head line that always goes in, a description
    that goes in when there is room."""

    indent: int
    head: str
    description: str = ""
    depth: int = 0
    political: bool = False
    facts: str = ""
    include_description: bool = False
    children: list[_Entry] = field(default_factory=list)


def _own_name(kind: str) -> str:
    tail = kind.rstrip("/#").replace("#", "/").split("/")[-1]
    return tail.replace("_", " ").replace("-", " ")


def kind_words(node: dict[str, Any]) -> tuple[str, str]:
    """Article and kind of a node, with what its type details add:
    ("de", "politieke input (motie, 12345)")."""
    kind = str(node.get("type") or "")
    article, name = _NODE_KINDS.get(kind, ("de", _own_name(kind) or "node"))
    details = node.get("type_details") or {}
    extra = [
        str(details[key]).replace("_", " ")
        for key in ("soort", "referentie")
        if details.get(key)
    ]
    if details.get("datum"):
        extra.append(str(details["datum"])[:10])
    if extra:
        name = f"{name} ({', '.join(extra)})"
    return article, name


def _trim(text: Any, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + " […]"


def _facts(node: dict[str, Any]) -> str:
    parts: list[str] = []
    organisation = (node.get("managing_organisation") or {}).get("name")
    if organisation:
        parts.append(f"Beheerd door: {organisation}.")
    if node.get("status"):
        parts.append(f"Status: {str(node['status']).replace('_', ' ')}.")
    validity = node.get("validity") or {}
    start, end = validity.get("start_date"), validity.get("end_date")
    if start and end:
        parts.append(f"Geldig van {str(start)[:10]} tot en met {str(end)[:10]}.")
    elif start:
        parts.append(f"Geldig vanaf {str(start)[:10]}.")
    elif end:
        parts.append(f"Geldig tot en met {str(end)[:10]}.")
    return " ".join(parts)


def _relation(edge_type: str, forward: bool) -> str:
    table = _FORWARD if forward else _BACKWARD
    if edge_type in table:
        return table[edge_type]
    name = _own_name(edge_type) or "hangt samen met"
    return name if forward else f"hangt samen ({name}) met"


def _chain_entries(
    linked: LinkedNode, corpus_name: Callable[[str], str | None]
) -> list[_Entry]:
    """The chain above a node as a tree of entries, every branch kept."""
    chain = linked.chain or {}
    nodes = {n["uri"]: n for n in chain.get("nodes") or [] if n.get("uri")}
    external = {uri for uri in chain.get("external_node_uris") or [] if uri}
    start = chain.get("start") or linked.node.get("uri")
    # Per node its neighbours, with the edge type and whether the edge runs
    # from this node (forward) or towards it.
    neighbours: dict[str, list[tuple[str, str, bool]]] = {}
    for edge in chain.get("edges") or []:
        source, target = edge.get("from"), edge.get("to")
        if not source or not target:
            continue
        kind = str(edge.get("type") or "")
        neighbours.setdefault(source, []).append((target, kind, True))
        neighbours.setdefault(target, []).append((source, kind, False))

    roots: list[_Entry] = []
    seen = {start}
    queue: deque[tuple[str, _Entry | None, int]] = deque([(start, None, 0)])
    while queue:
        current, parent, depth = queue.popleft()
        if depth >= MAX_DEPTH:
            continue
        for neighbour, kind, forward in neighbours.get(current, []):
            if neighbour in seen:
                continue
            seen.add(neighbour)
            relation = _relation(kind, forward)
            node = nodes.get(neighbour)
            if node is None:
                # A node the corpus does not hold: a link into another corpus.
                name = corpus_name(neighbour) if neighbour in external else None
                where = f"het corpus {name}" if name else "een ander corpus"
                entry = _Entry(
                    indent=depth,
                    depth=depth + 1,
                    head=f"{relation} een node in {where}",
                )
            else:
                article, words = kind_words(node)
                entry = _Entry(
                    indent=depth,
                    depth=depth + 1,
                    head=f'{relation} {article} {words} "{node.get("title") or ""}"',
                    description=_trim(node.get("description"), CHAIN_DESCRIPTION_CHARS),
                    political=node.get("type") == POLITICAL_INPUT,
                )
            (parent.children if parent is not None else roots).append(entry)
            is_end = node is None or node.get("type") == POLITICAL_INPUT
            if not is_end:
                queue.append((neighbour, entry, depth + 1))
    return roots


def _flatten(entries: list[_Entry]) -> list[_Entry]:
    flat: list[_Entry] = []
    for entry in entries:
        flat.append(entry)
        flat.extend(_flatten(entry.children))
    return flat


def _render(entries: list[_Entry]) -> list[str]:
    lines: list[str] = []
    for entry in entries:
        pad = "  " * (entry.indent + 1)
        lines.append(f"{pad}- {entry.head}")
        if entry.include_description and entry.description:
            lines.append(f"{pad}  Omschrijving: {entry.description}")
        lines.extend(_render(entry.children))
    return lines


def build(
    linked_nodes: list[LinkedNode],
    *,
    corpus_name: Callable[[str], str | None] = lambda uri: None,
    budget: int = DEFAULT_BUDGET,
) -> ContextBrief:
    """The context of an assignment as a block of text within the budget."""
    if not linked_nodes:
        return ContextBrief()

    blocks: list[tuple[_Entry, list[_Entry]]] = []
    for number, linked in enumerate(linked_nodes, start=1):
        _article, words = kind_words(linked.node)
        top = _Entry(
            indent=0,
            depth=0,
            head=f'Contextnode {number}: {words} "{linked.node.get("title") or ""}"',
            description=_trim(linked.node.get("description"), NODE_DESCRIPTION_CHARS),
            political=linked.node.get("type") == POLITICAL_INPUT,
            facts=_facts(linked.node),
        )
        blocks.append((top, _chain_entries(linked, corpus_name)))

    everything = [entry for top, chain in blocks for entry in (top, *_flatten(chain))]
    used = sum(len(entry.head) + len(entry.facts) + 8 for entry in everything)
    # The political origin first, then the node itself, then level by level.
    order = sorted(
        (entry for entry in everything if entry.description),
        key=lambda entry: (not entry.political, entry.depth),
    )
    left_out = 0
    for entry in order:
        cost = len(entry.description) + 16
        if entry.political or used + cost <= budget:
            entry.include_description = True
            used += cost
        else:
            left_out += 1

    lines: list[str] = []
    for top, chain in blocks:
        lines.append(top.head)
        if top.facts:
            lines.append(f"  {top.facts}")
        if top.include_description and top.description:
            lines.append(f"  Omschrijving: {top.description}")
        if chain:
            lines.append("  Waar dit uit voortkomt:")
            lines.extend(_render(chain))
    dropped: list[str] = []
    if left_out:
        dropped.append(
            f"De omschrijving van {left_out} "
            f"{'node' if left_out == 1 else 'nodes'} verder in de keten is "
            "weggelaten om de context beknopt te houden."
        )
    return ContextBrief(
        lines=tuple(lines), node_count=len(linked_nodes), dropped=tuple(dropped)
    )
