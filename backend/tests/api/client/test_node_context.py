"""The chain of a node turned into "where does this come from"."""

from __future__ import annotations

from grip.services.node_context import nearest_linked, summarise

BASE = "https://corpus.voorbeeldministerie.example/id/node"
INSTRUMENT, GOAL, MOTION, AGREEMENT, MEASURE = (
    f"{BASE}/instrument",
    f"{BASE}/doel",
    f"{BASE}/motie",
    f"{BASE}/akkoord",
    f"{BASE}/maatregel",
)
ELSEWHERE = "https://corpus.anderministerie.example/id/node/doel"


def node(uri: str, kind: str, title: str) -> dict:
    return {"uri": uri, "type": kind, "title": title}


def edge(source: str, target: str, kind: str) -> dict:
    return {"from": source, "to": target, "type": kind}


CHAIN = {
    "start": INSTRUMENT,
    "nodes": [
        node(INSTRUMENT, "instrument", "Opdracht bouwsteen Alfa"),
        node(GOAL, "doel", "Hergebruik van bouwstenen"),
        node(MOTION, "politieke_input", "Motie over hergebruik"),
    ],
    "edges": [
        edge(INSTRUMENT, GOAL, "implementeert"),
        edge(GOAL, MOTION, "vloeit_voort_uit"),
    ],
}


def test_one_political_input_gives_one_path_with_the_relations():
    summary = summarise(CHAIN, INSTRUMENT)
    assert [origin.title for origin in summary.origins] == ["Motie over hergebruik"]
    assert summary.steps_to_origin == 2
    (path,) = summary.paths
    assert [step.type for step in path.steps] == [
        "instrument",
        "doel",
        "politieke_input",
    ]
    # The relation is told on the step it leaves from; the last has none.
    assert [step.edge_type for step in path.steps] == [
        "implementeert",
        "vloeit_voort_uit",
        None,
    ]
    assert summary.passed_uris == {GOAL, MOTION}


def test_a_step_names_who_manages_it():
    chain = {
        **CHAIN,
        "nodes": [
            CHAIN["nodes"][0],
            {
                **CHAIN["nodes"][1],
                "managing_organisation": {"name": "Voorbeeldministerie"},
            },
            {**CHAIN["nodes"][2], "managing_organisation": None},
        ],
    }
    (path,) = summarise(chain, INSTRUMENT).paths
    assert [step.organisation for step in path.steps] == [
        None,
        "Voorbeeldministerie",
        None,
    ]


def test_two_political_inputs_give_two_paths_nearest_first():
    chain = {
        **CHAIN,
        "nodes": [
            *CHAIN["nodes"],
            node(MEASURE, "maatregel", "Een maatregel"),
            node(AGREEMENT, "politieke_input", "Passage in het akkoord"),
        ],
        "edges": [
            *CHAIN["edges"],
            edge(GOAL, MEASURE, "onderdeel_van"),
            # Worded the other way round; a chain connects either way.
            edge(AGREEMENT, MEASURE, "leidt_tot"),
        ],
    }
    summary = summarise(chain, INSTRUMENT)
    assert [origin.title for origin in summary.origins] == [
        "Motie over hergebruik",
        "Passage in het akkoord",
    ]
    assert summary.steps_to_origin == 2
    assert [len(path.steps) for path in summary.paths] == [3, 4]
    assert summary.paths[1].steps[2].edge_type == "leidt_tot"


def test_a_political_input_is_not_walked_through():
    chain = {
        **CHAIN,
        "nodes": [*CHAIN["nodes"], node(AGREEMENT, "politieke_input", "Akkoord")],
        "edges": [*CHAIN["edges"], edge(MOTION, AGREEMENT, "vloeit_voort_uit")],
    }
    summary = summarise(chain, INSTRUMENT)
    assert [origin.uri for origin in summary.origins] == [MOTION]


def test_a_chain_into_another_corpus_ends_there_as_an_external_step():
    chain = {
        "start": INSTRUMENT,
        "nodes": [
            node(INSTRUMENT, "instrument", "Opdracht bouwsteen Alfa"),
            node(GOAL, "doel", "Hergebruik van bouwstenen"),
        ],
        "edges": [
            edge(INSTRUMENT, GOAL, "implementeert"),
            edge(GOAL, ELSEWHERE, "draagt_bij_aan"),
        ],
        "external_node_uris": [ELSEWHERE],
    }
    summary = summarise(chain, INSTRUMENT)
    assert summary.origins == () and summary.steps_to_origin is None
    (path,) = summary.paths
    last = path.steps[-1]
    assert last.uri == ELSEWHERE and last.external is True and last.title is None
    assert path.steps[1].edge_type == "draagt_bij_aan"


def test_no_chain_or_a_node_on_its_own_gives_nothing():
    assert summarise(None, INSTRUMENT).paths == ()
    alone = {"start": GOAL, "nodes": [node(GOAL, "doel", "Een doel")], "edges": []}
    summary = summarise(alone, GOAL)
    assert summary.paths == () and summary.origins == ()


def test_a_political_input_itself_has_no_path():
    chain = {
        "start": MOTION,
        "nodes": [node(MOTION, "politieke_input", "Motie")],
        "edges": [],
    }
    assert summarise(chain, MOTION).origins == ()


def test_nearest_linked_node_on_the_chain():
    summary = summarise(CHAIN, INSTRUMENT)
    assert nearest_linked(summary, INSTRUMENT, [INSTRUMENT, GOAL]) == GOAL
    assert nearest_linked(summary, INSTRUMENT, [INSTRUMENT, MOTION, GOAL]) == GOAL
    assert nearest_linked(summary, INSTRUMENT, [INSTRUMENT, ELSEWHERE]) is None
    # The goal does not fall under the instrument below it.
    goal_chain = {
        "start": GOAL,
        "nodes": CHAIN["nodes"][1:],
        "edges": CHAIN["edges"][1:],
    }
    above = summarise(goal_chain, GOAL)
    assert nearest_linked(above, GOAL, [INSTRUMENT, GOAL]) is None
