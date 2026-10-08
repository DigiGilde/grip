"""The corpus client: which corpus to ask, and what comes back."""

from datetime import date

import httpx
import pytest

from grip.federation.corpus import (
    CorpusClient,
    CorpusContractError,
    CorpusUnavailableError,
    NodeNotFoundError,
    UnknownCorpusError,
    node_id_from_uri,
)
from grip.federation.models import PEER_ROLE_CORPUS

from .conftest import example

CORPUS = "https://corpus.voorbeeldministerie.example"
NODE_URI = example("node")["uri"]
NODE_ID = NODE_URI.rsplit("/", 1)[-1]


@pytest.fixture
async def corpus_peer(make_peer):
    return await make_peer(
        "00000000000000000007", base_uri=CORPUS, role=PEER_ROLE_CORPUS
    )


@pytest.fixture
def corpus(outway, fed_settings) -> CorpusClient:
    return CorpusClient(outway, fed_settings)


def _answers(fake_outway, body, status=200):
    fake_outway.handler = lambda _request: httpx.Response(status, json=body)


async def test_node_is_fetched_from_the_corpus_of_its_uri(
    db_session, corpus_peer, corpus, fake_outway
):
    _answers(fake_outway, example("node"))
    node = await corpus.get_node(db_session, NODE_URI)
    assert node == example("node")
    (request,) = fake_outway.requests
    assert str(request.url) == f"http://outway.test/v1/nodes/{NODE_ID}"
    assert (
        request.headers["Fsc-Grant-Hash"] == corpus_peer.grant_hashes["corpus-context"]
    )


async def test_peildatum_is_passed_on(db_session, corpus_peer, corpus, fake_outway):
    _answers(fake_outway, example("node"))
    await corpus.get_node(db_session, NODE_URI, peildatum=date(2026, 3, 1))
    assert fake_outway.requests[0].url.params["peildatum"] == "2026-03-01"


async def test_chain_is_fetched_with_depth(
    db_session, corpus_peer, corpus, fake_outway
):
    _answers(fake_outway, example("chain"))
    chain = await corpus.get_chain(
        db_session, NODE_URI, peildatum=date(2026, 3, 1), max_depth=4
    )
    assert chain == example("chain")
    url = fake_outway.requests[0].url
    assert url.path == f"/v1/nodes/{NODE_ID}/chain"
    assert dict(url.params) == {"peildatum": "2026-03-01", "maxDepth": "4"}


async def test_answers_are_cached_per_uri_and_peildatum(
    db_session, corpus_peer, corpus, fake_outway
):
    _answers(fake_outway, example("node"))
    await corpus.get_node(db_session, NODE_URI)
    await corpus.get_node(db_session, NODE_URI + "/")
    assert len(fake_outway.requests) == 1
    await corpus.get_node(db_session, NODE_URI, peildatum=date(2026, 3, 1))
    assert len(fake_outway.requests) == 2
    corpus.clear_cache()
    await corpus.get_node(db_session, NODE_URI)
    assert len(fake_outway.requests) == 3


async def test_cache_expires(
    db_session, corpus_peer, outway, fed_settings, fake_outway
):
    corpus = CorpusClient(
        outway, fed_settings.model_copy(update={"CORPUS_CACHE_TTL_SECONDS": 0})
    )
    _answers(fake_outway, example("node"))
    await corpus.get_node(db_session, NODE_URI)
    await corpus.get_node(db_session, NODE_URI)
    assert len(fake_outway.requests) == 2


async def test_uri_of_an_unknown_corpus_is_a_clear_error(
    db_session, corpus_peer, corpus, fake_outway
):
    with pytest.raises(UnknownCorpusError, match="No corpus system is registered"):
        await corpus.get_node(
            db_session, "https://corpus.ander-ministerie.example/id/node/" + NODE_ID
        )
    assert fake_outway.requests == []


@pytest.mark.parametrize(
    "uri",
    ["geen uri", CORPUS, CORPUS + "/id/node/", CORPUS + "/id/doel/" + NODE_ID, ""],
)
async def test_something_that_is_not_a_node_uri_is_refused(db_session, corpus, uri):
    with pytest.raises(UnknownCorpusError):
        await corpus.get_node(db_session, uri)


async def test_several_corpora_longest_base_wins(
    db_session, corpus, fake_outway, make_peer
):
    await make_peer(
        "00000000000000000007", base_uri="https://corpus.example", role=PEER_ROLE_CORPUS
    )
    nested = await make_peer(
        "00000000000000000008",
        base_uri="https://corpus.example/ezk",
        role=PEER_ROLE_CORPUS,
    )
    other = await make_peer(
        "00000000000000000009",
        base_uri="https://corpus.example-other",
        role=PEER_ROLE_CORPUS,
    )
    body = example("node")
    _answers(fake_outway, body)
    await corpus.get_node(db_session, f"https://corpus.example/ezk/id/node/{NODE_ID}")
    await corpus.get_node(db_session, f"https://corpus.example-other/id/node/{NODE_ID}")
    hashes = [request.headers["Fsc-Grant-Hash"] for request in fake_outway.requests]
    assert hashes == [
        nested.grant_hashes["corpus-context"],
        other.grant_hashes["corpus-context"],
    ]


async def test_instance_peer_is_not_a_corpus(db_session, corpus, make_peer):
    await make_peer(base_uri=CORPUS)
    with pytest.raises(UnknownCorpusError):
        await corpus.get_node(db_session, NODE_URI)


async def test_inactive_corpus_is_not_asked(db_session, corpus, make_peer):
    await make_peer(base_uri=CORPUS, role=PEER_ROLE_CORPUS, is_active=False)
    with pytest.raises(UnknownCorpusError):
        await corpus.get_node(db_session, NODE_URI)


async def test_404_is_node_not_found(db_session, corpus_peer, corpus, fake_outway):
    _answers(fake_outway, {"title": "Niet gevonden", "status": 404, "detail": "x"}, 404)
    with pytest.raises(NodeNotFoundError):
        await corpus.get_node(db_session, NODE_URI)


@pytest.mark.parametrize("status", [403, 500, 503])
async def test_other_errors_are_unavailable(
    db_session, corpus_peer, corpus, fake_outway, status
):
    _answers(fake_outway, {"title": "x", "status": status, "detail": "x"}, status)
    with pytest.raises(CorpusUnavailableError):
        await corpus.get_node(db_session, NODE_URI)


async def test_network_error_is_unavailable(
    db_session, corpus_peer, corpus, fake_outway
):
    def unreachable(request):
        raise httpx.ConnectError("down", request=request)

    fake_outway.handler = unreachable
    with pytest.raises(CorpusUnavailableError):
        await corpus.get_node(db_session, NODE_URI)


async def test_missing_grant_is_unavailable(db_session, corpus, make_peer, fake_outway):
    await make_peer(base_uri=CORPUS, role=PEER_ROLE_CORPUS, grant_hashes={})
    with pytest.raises(CorpusUnavailableError):
        await corpus.get_node(db_session, NODE_URI)
    assert fake_outway.requests == []


@pytest.mark.parametrize(
    "name", ["node.onbekend-type", "node.politieke-input-zonder-soort"]
)
async def test_answer_outside_the_contract_is_refused_and_not_cached(
    db_session, corpus_peer, corpus, fake_outway, name
):
    _answers(fake_outway, example(name, "invalid"))
    with pytest.raises(CorpusContractError):
        await corpus.get_node(db_session, NODE_URI)
    _answers(fake_outway, example("node"))
    assert await corpus.get_node(db_session, NODE_URI) == example("node")


async def test_node_of_a_custom_type_and_another_corpus_edge_are_accepted(
    db_session, corpus_peer, corpus, fake_outway
):
    _answers(fake_outway, example("node.eigen-type"))
    assert await corpus.get_node(db_session, NODE_URI)


async def test_search_goes_to_the_named_corpus(
    db_session, corpus_peer, corpus, fake_outway
):
    _answers(fake_outway, example("node-page"))
    page = await corpus.search_nodes(
        db_session, CORPUS, q="digitale", types=["doel", "instrument"], page_size=5
    )
    assert page == example("node-page")
    url = fake_outway.requests[0].url
    assert url.path == "/v1/nodes"
    assert url.params.get_list("type") == ["doel", "instrument"]
    assert url.params["q"] == "digitale" and url.params["pageSize"] == "5"


def test_node_id_from_uri():
    assert node_id_from_uri(NODE_URI) == NODE_ID
    assert node_id_from_uri(NODE_URI + "/") == NODE_ID
