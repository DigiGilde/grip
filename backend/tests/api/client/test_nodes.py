"""The node picker and resolved context, against a stand-in corpus."""

from __future__ import annotations

import httpx
import pytest

from grip.federation.models import Peer

from .conftest import CORPUS_BASE, CORPUS_GRANT, NODE_URI, OTHER_NODE_URI, example

NODE_ID = NODE_URI.rsplit("/", 1)[-1]


def corpus(request: httpx.Request) -> httpx.Response:
    """A corpus that answers in the shapes of the contract."""
    assert request.headers["Fsc-Grant-Hash"] == CORPUS_GRANT
    path = request.url.path
    if path == "/v1/nodes":
        return httpx.Response(200, json=example("node-pagina"))
    if path == f"/v1/nodes/{NODE_ID}":
        return httpx.Response(200, json=example("node.instrument"))
    if path == f"/v1/nodes/{NODE_ID}/keten":
        return httpx.Response(200, json=example("keten"))
    return httpx.Response(
        404, json={"type": "about:blank", "title": "Niet gevonden", "status": 404}
    )


async def test_corpora_and_who_may_use_the_picker(client, cast, act_as, outway):
    act_as(cast.requester)
    body = (await client.get("/api/nodes/corpora")).json()
    assert body["problem"] is None
    assert body["corpora"] == [
        {
            "base_uri": CORPUS_BASE,
            "name": "Corpus Voorbeeldministerie",
            "searchable": True,
        }
    ]
    # Who starts assignments as contractor uses the same picker.
    act_as(cast.planner)
    assert (await client.get("/api/nodes/corpora")).status_code == 200
    for person in (cast.lezer, cast.signer, cast.outsider):
        act_as(person)
        assert (await client.get("/api/nodes/corpora")).status_code == 403
        search = await client.get("/api/nodes/search", params={"corpus": CORPUS_BASE})
        assert search.status_code == 403
        lookup = await client.get("/api/nodes/lookup", params={"uri": NODE_URI})
        assert lookup.status_code == 403


async def test_without_a_corpus_the_picker_says_so(
    client, db_session, cast, act_as, outway
):
    peer = await db_session.get(Peer, cast.corpus_peer.id)
    peer.is_active = False
    await db_session.flush()
    act_as(cast.requester)
    body = (await client.get("/api/nodes/corpora")).json()
    assert body.get("corpora", []) == []
    assert "geen corpus" in body["problem"] and "zonder context" in body["problem"]


async def test_search_returns_nodes_of_the_corpus(client, cast, act_as, outway):
    outway.handler = corpus
    act_as(cast.requester)
    response = await client.get(
        "/api/nodes/search",
        params={"corpus": CORPUS_BASE, "q": "bouwsteen", "type": "doel"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["problem"] is None and body["total"] == 2
    first = body["results"][0]
    assert first["type"] == "doel"
    assert first["title"] == "Overheidsdiensten hergebruiken gedeelde bouwstenen"
    assert first["managing_organisation"]["name"] == "Voorbeeldministerie"
    assert first["valid_from"] == "2026-01-01"
    sent = outway.requests[-1]
    assert sent.url.params["q"] == "bouwsteen" and sent.url.params["type"] == "doel"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (httpx.Response(503, text="down"), "niet bereikbaar"),
        (httpx.Response(200, json={"iets": "anders"}), "niet aan het contract"),
    ],
)
async def test_a_corpus_that_fails_does_not_block(
    client, cast, act_as, outway, answer, expected
):
    outway.handler = lambda _request: answer
    act_as(cast.requester)
    body = (
        await client.get("/api/nodes/search", params={"corpus": CORPUS_BASE})
    ).json()
    assert body.get("results", []) == [] and expected in body["problem"]


async def test_search_in_an_unknown_corpus(client, cast, act_as, outway):
    act_as(cast.requester)
    body = (
        await client.get(
            "/api/nodes/search",
            params={"corpus": "https://corpus.anderministerie.example"},
        )
    ).json()
    assert "geen corpus gekoppeld" in body["problem"]
    assert outway.requests == []


async def test_lookup_gives_the_node_and_its_chain(client, cast, act_as, outway):
    outway.handler = corpus
    act_as(cast.requester)
    body = (
        await client.get(
            "/api/nodes/lookup", params={"uri": NODE_URI, "peildatum": "2026-07-01"}
        )
    ).json()
    assert body["resolved"] is True and body["problem"] is None
    assert body["node"]["type"] == "instrument"
    assert body["node"]["title"] == "Opdracht bouwsteen Alfa"
    chain = body["chain"]
    assert [node["type"] for node in chain["nodes"]] == [
        "instrument",
        "doel",
        "politieke_input",
    ]
    assert chain["edges"][0]["from_uri"] == NODE_URI
    assert chain["nodes"][-1]["type_details"]["soort"] == "motie"
    assert {r.url.params.get("peildatum") for r in outway.requests} == {"2026-07-01"}


async def test_a_pasted_uri_of_another_corpus_stays_a_uri(client, cast, act_as, outway):
    outway.handler = corpus
    act_as(cast.requester)
    body = (
        await client.get("/api/nodes/lookup", params={"uri": OTHER_NODE_URI})
    ).json()
    assert body["uri"] == OTHER_NODE_URI and body["resolved"] is False
    assert "geen corpus gekoppeld" in body["problem"]
    assert "node" not in body or body["node"] is None


async def test_context_of_an_assignment_is_resolved_as_of_a_date(
    client, db_session, cast, act_as, outway, received
):
    outway.handler = corpus
    received.assignment.context_refs = [NODE_URI, OTHER_NODE_URI]
    await db_session.flush()

    act_as(cast.requester)
    response = await client.get(f"/api/assignments/{received.assignment.id}/context")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["acceptance_date"] is None
    resolved, bare = body["items"]
    assert resolved["resolved"] is True
    assert resolved["node"]["title"] == "Opdracht bouwsteen Alfa"
    assert resolved["chain"]["nodes"][-1]["type"] == "politieke_input"
    # A URI nobody answers for stays visible as a URI.
    assert bare["uri"] == OTHER_NODE_URI and bare["resolved"] is False
    assert bare["problem"] and not bare.get("node") and not bare.get("chain")

    dated = await client.get(
        f"/api/assignments/{received.assignment.id}/context",
        params={"peildatum": "2026-03-01"},
    )
    assert dated.json()["peildatum"] == "2026-03-01"
    assert outway.requests[-1].url.params["peildatum"] == "2026-03-01"

    no_acceptance = await client.get(
        f"/api/assignments/{received.assignment.id}/context",
        params={"peildatum": "acceptance"},
    )
    assert no_acceptance.status_code == 422
    nonsense = await client.get(
        f"/api/assignments/{received.assignment.id}/context",
        params={"peildatum": "gisteren"},
    )
    assert nonsense.status_code == 422

    # The planner reads assignment basics, so also the context.
    act_as(cast.planner)
    allowed = await client.get(f"/api/assignments/{received.assignment.id}/context")
    assert allowed.status_code == 200
    act_as(cast.outsider)
    hidden = await client.get(f"/api/assignments/{received.assignment.id}/context")
    assert hidden.status_code == 404


async def test_resolved_nodes_are_cached_briefly(
    client, cast, act_as, outway, received
):
    outway.handler = corpus
    act_as(cast.requester)
    await client.get(f"/api/assignments/{received.assignment.id}/context")
    asked = len(outway.requests)
    await client.get(f"/api/assignments/{received.assignment.id}/context")
    assert len(outway.requests) == asked
