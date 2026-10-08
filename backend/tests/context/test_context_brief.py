"""The policy context of an assignment as a block for a prompt.

Pure functions; the corpus content is fictional.
"""

from __future__ import annotations

import pytest

from grip.services import context_brief, context_fetch, quote_prose
from grip.services.quote_drafting import (
    CONTEXT_INSTRUCTION,
    SectionInput,
    SectionInputError,
    build_prompt,
    ensure_no_person_names,
)

BASE = "https://corpus.voorbeeld.example/id/node"
OTHER = "https://ander-corpus.voorbeeld.example/id/node/9"


def _node(key: str, kind: str, title: str, description: str = "", **extra) -> dict:
    return {
        "uri": f"{BASE}/{key}",
        "type": kind,
        "title": title,
        "description": description,
        "status": "actief",
        "managing_organisation": {"name": "Voorbeeldministerie"},
        "validity": {"start_date": "2026-01-01", "end_date": None},
        **extra,
    }


INSTRUMENT = _node(
    "i",
    "instrument",
    "Voorlichting over de catalogus",
    "Uitvoerders weten welke bouwstenen er zijn en hoe ze die gebruiken.",
    type_details={"soort": "voorlichting"},
)
GOAL = _node("d1", "doel", "Diensten hergebruiken bouwstenen", "Minder dubbel werk.")
HIGHER = _node(
    "d2", "doel", "In een keer goed", "De burger hoeft iets maar een keer te doen."
)
MOTION = _node(
    "m",
    "politieke_input",
    "Motie over hergebruik",
    "Verzoekt de regering hergebruik de norm te maken.",
    type_details={"soort": "motie", "referentie": "12345-67"},
)
AGREEMENT = _node(
    "c",
    "politieke_input",
    "Passage over dienstverlening",
    "De overheid regelt het in een keer goed.",
    type_details={"soort": "coalitieakkoord", "referentie": None},
)


def _edge(source: dict | str, kind: str, target: dict | str) -> dict:
    uri = lambda n: n if isinstance(n, str) else n["uri"]  # noqa: E731
    return {"from": uri(source), "type": kind, "to": uri(target)}


CHAIN = {
    "start": INSTRUMENT["uri"],
    "nodes": [INSTRUMENT, GOAL, HIGHER, MOTION, AGREEMENT],
    "edges": [
        _edge(INSTRUMENT, "implementeert", GOAL),
        _edge(GOAL, "vloeit_voort_uit", MOTION),
        _edge(GOAL, "draagt_bij_aan", HIGHER),
        _edge(HIGHER, "vloeit_voort_uit", AGREEMENT),
        _edge(INSTRUMENT, "verwijst_naar", OTHER),
    ],
    "external_node_uris": [OTHER],
    "complete": True,
}


def _brief(**kwargs) -> context_brief.ContextBrief:
    return context_brief.build(
        [context_brief.LinkedNode(node=INSTRUMENT, chain=CHAIN)],
        corpus_name=lambda uri: "Ander Ministerie" if uri == OTHER else None,
        **kwargs,
    )


def test_every_level_of_both_branches_is_in_the_block_with_its_relation() -> None:
    text = _brief().text
    assert text.splitlines()[0] == (
        'Contextnode 1: instrument (voorlichting) "Voorlichting over de catalogus"'
    )
    assert "Beheerd door: Voorbeeldministerie. Status: actief." in text
    assert "Geldig vanaf 2026-01-01." in text
    assert "Omschrijving: Uitvoerders weten welke bouwstenen er zijn" in text
    for line in (
        '  - implementeert het doel "Diensten hergebruiken bouwstenen"',
        '    - volgt uit de politieke input (motie, 12345-67) "Motie over hergebruik"',
        '    - draagt bij aan het doel "In een keer goed"',
        "      - volgt uit de politieke input (coalitieakkoord) "
        '"Passage over dienstverlening"',
        "  - verwijst naar een node in het corpus Ander Ministerie",
    ):
        assert line in text.splitlines(), line
    # Deeper levels are indented under what they follow from.
    lines = text.splitlines()
    assert lines.index(
        '    - draagt bij aan het doel "In een keer goed"'
    ) < lines.index(
        "      - volgt uit de politieke input (coalitieakkoord) "
        '"Passage over dienstverlening"'
    )
    assert "Verzoekt de regering hergebruik de norm te maken." in text
    # The other corpus is named, never described: its content is not ours.
    assert OTHER not in text


def test_an_edge_recorded_the_other_way_round_reads_the_other_way() -> None:
    chain = {
        "start": GOAL["uri"],
        "nodes": [GOAL, INSTRUMENT],
        "edges": [_edge(INSTRUMENT, "implementeert", GOAL)],
    }
    brief = context_brief.build([context_brief.LinkedNode(node=GOAL, chain=chain)])
    assert (
        "  - wordt uitgevoerd door het instrument (voorlichting) "
        '"Voorlichting over de catalogus"'
    ) in brief.lines


def test_the_budget_drops_descriptions_far_away_first_and_says_so() -> None:
    full = _brief()
    assert full.dropped == ()
    tight = _brief(budget=520)
    text = tight.text
    # Titles, kinds and relations of every level stay.
    assert '"In een keer goed"' in text and '"Motie over hergebruik"' in text
    # The political origin always keeps its description.
    assert "Verzoekt de regering hergebruik de norm te maken." in text
    assert "De overheid regelt het in een keer goed." in text
    # The nearest goes before the furthest.
    assert "Minder dubbel werk." not in text or "een keer te doen" not in text
    assert "een keer te doen" not in text
    assert len(tight.dropped) == 1 and "weggelaten" in tight.dropped[0]
    assert len(text) < len(full.text)


def test_a_long_description_is_trimmed_at_a_word() -> None:
    long = _node("x", "doel", "Lang doel", "woord " * 400)
    brief = context_brief.build([context_brief.LinkedNode(node=long)])
    line = next(line for line in brief.lines if "Omschrijving" in line)
    assert (
        line.endswith("[…]") and len(line) < context_brief.NODE_DESCRIPTION_CHARS + 40
    )


def test_nothing_without_context() -> None:
    assert context_brief.build([]) == context_brief.ContextBrief()
    _system, user = build_prompt(SectionInput(heading="Inleiding"))
    assert CONTEXT_INSTRUCTION not in user
    assert "Contextnode" not in user


def test_the_prompt_carries_the_block_and_how_to_use_it() -> None:
    system, user = build_prompt(
        SectionInput(heading="Inleiding", context=_brief().lines)
    )
    assert CONTEXT_INSTRUCTION in user
    assert "Verzin geen beleid dat hier niet staat." in user
    assert "    - draagt bij aan het doel" in user  # the indentation survives
    assert "Krijg je geen beleidscontext" in system


def test_a_name_in_corpus_text_stops_the_request() -> None:
    named = _node("n", "doel", "Doel", "Afgesproken met Vera Voorbeeld van het team.")
    lines = context_brief.build([context_brief.LinkedNode(node=named)]).lines
    assert quote_prose.find_names("\n".join(lines), ["Vera Voorbeeld"])
    with pytest.raises(SectionInputError, match="naam van een persoon"):
        ensure_no_person_names(
            SectionInput(heading="Inleiding", context=lines), ["Vera Voorbeeld"]
        )


class _Assignment:
    def __init__(self, refs: list[str]) -> None:
        self.context_refs = refs


class _Corpus:
    def __init__(self, *, fail: bool = False, fail_chain: bool = False) -> None:
        self.fail, self.fail_chain = fail, fail_chain

    async def get_node(self, db, uri, *, peildatum=None):
        if self.fail:
            raise RuntimeError("corpus weg")
        return INSTRUMENT

    async def get_chain(self, db, uri, *, peildatum=None):
        if self.fail_chain:
            raise RuntimeError("keten weg")
        return CHAIN


async def test_fetching_says_what_became_of_asking() -> None:
    assignment = _Assignment([INSTRUMENT["uri"]])
    used = await context_fetch.for_assignment(
        None, assignment, corpus=_Corpus(), reachable=True
    )
    assert used.state == "used" and used.lines[0].startswith("Contextnode 1")

    none = await context_fetch.for_assignment(
        None, _Assignment([]), corpus=_Corpus(), reachable=True
    )
    assert none.state == "none" and none.lines == ()

    for corpus, reachable in ((_Corpus(), False), (_Corpus(fail=True), True)):
        gone = await context_fetch.for_assignment(
            None, assignment, corpus=corpus, reachable=reachable
        )
        assert gone.state == "unreachable" and gone.lines == ()

    # The node without its chain is still worth having.
    alone = await context_fetch.for_assignment(
        None, assignment, corpus=_Corpus(fail_chain=True), reachable=True
    )
    assert alone.state == "used" and "Waar dit uit voortkomt" not in "\n".join(
        alone.lines
    )
