"""The stand-in corpus: its answers follow the vendored contract."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import get_settings
from grip.dev import corpus_standin
from grip.dev.corpus_standin.app import create_app
from grip.dev.seed import CONTEXT, extend, seed
from grip.federation.contract_loader import (
    SERVICE_CORPUS_CONTEXT,
    api_version,
    validation_errors,
)
from grip.federation.corpus import CorpusClient
from grip.federation.models import PEER_ROLE_CORPUS, Peer
from grip.federation.outway import GRANT_HASH_HEADER, OutwayClient
from grip.models.assignment import Assignment
from grip.services import events

MAIN = corpus_standin.corpus_by_key("voorbeeldministerie")
OTHER = corpus_standin.corpus_by_key("anderministerie")
BASE = "http://standin.test"


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


@pytest.fixture
async def standin():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
        yield client


def _grant(corpus) -> dict[str, str]:
    return {GRANT_HASH_HEADER: corpus.grant_hash}


def _id(corpus, key: str) -> str:
    return corpus.node_by_key(key)["id"]


def _valid(schema: str, body) -> None:
    assert validation_errors(schema, body) == []


async def test_corpus_and_vocabulary_follow_the_contract(standin):
    for corpus in corpus_standin.corpora():
        response = await standin.get("/v1/corpus", headers=_grant(corpus))
        assert response.status_code == 200
        assert response.headers["API-Version"] == api_version(SERVICE_CORPUS_CONTEXT)
        _valid("corpus-info", response.json())
        assert response.json()["corpus"] == corpus.base
    vocabulary = (await standin.get("/v1/woordenlijst", headers=_grant(MAIN))).json()
    _valid("woordenlijst", vocabulary)


async def test_every_node_and_chain_follows_the_contract(standin):
    for corpus in corpus_standin.corpora():
        for node in corpus.nodes:
            path = f"/v1/nodes/{node['id']}"
            body = (await standin.get(path, headers=_grant(corpus))).json()
            _valid("node", body)
            assert body["uri"] == corpus.uri(node["id"])
            chain = (await standin.get(f"{path}/keten", headers=_grant(corpus))).json()
            _valid("keten", chain)
            assert chain["start"] == body["uri"]


async def test_search_follows_the_contract_and_filters(standin):
    page = (await standin.get("/v1/nodes", headers=_grant(MAIN))).json()
    _valid("node-pagina", page)
    assert page["totaal"] == len(MAIN.nodes) == 15
    found = (
        await standin.get(
            "/v1/nodes",
            params={"q": "bouwste", "type": ["instrument"], "pageSize": 2},
            headers=_grant(MAIN),
        )
    ).json()
    _valid("node-pagina", found)
    assert found["totaal"] >= 3
    assert len(found["resultaten"]) == 2
    assert {n["type"] for n in found["resultaten"]} == {"instrument"}


async def test_the_corpus_has_the_shapes_of_policy():
    kinds = [n["type"] for n in MAIN.nodes]
    assert kinds.count("politieke_input") == 2
    assert "beleidskader" in kinds
    assert {"wetgeving", "subsidie", "overig"} <= {
        n["type_details"]["soort"] for n in MAIN.nodes if n["type"] == "instrument"
    }
    for corpus in corpus_standin.corpora():
        assert ".example" in corpus.base
        assert "(fictief)" in corpus.name


async def test_chains_of_two_and_three_steps(standin):
    """Shortest paths to every political input that can be reached."""

    async def chain_of(key: str) -> dict:
        path = f"/v1/nodes/{_id(MAIN, key)}/keten"
        return (await standin.get(path, headers=_grant(MAIN))).json()

    def steps(chain: dict, target_key: str) -> int:
        # Nodes come ordered by distance from the start; count the hops.
        target = MAIN.uri(_id(MAIN, target_key))
        hops = {chain["start"]: 0}
        changed = True
        while changed:
            changed = False
            for edge in chain["edges"]:
                for a, b in ((edge["van"], edge["naar"]), (edge["naar"], edge["van"])):
                    if a in hops and hops.get(b, 99) > hops[a] + 1:
                        hops[b] = hops[a] + 1
                        changed = True
        return hops[target]

    alfa = await chain_of("opdracht_alfa")
    assert alfa["nodes"][0]["titel"].startswith(
        "Opdracht aan het Voorbeeldgilde: bouwsteen Alfa"
    )
    # Instrument, its goal and the motion: two steps. The coalition
    # agreement is reachable through the wider goal, in three.
    assert steps(alfa, "pi_motie") == 2
    assert steps(alfa, "pi_akkoord") == 3
    assert len(alfa["nodes"]) == 5
    assert alfa["volledig"] is True
    # The goal refers to a goal of another corpus: listed, not followed.
    assert alfa["externe_node_uris"] == [OTHER.uri(_id(OTHER, "doel_europa"))]

    beta = await chain_of("opdracht_beta")
    assert steps(beta, "pi_motie") == 3
    assert [n["type"] for n in beta["nodes"]][:3] == ["instrument", "doel", "doel"]
    # Nodes off the shortest paths (the subsidy, the source) stay out.
    titles = {n["titel"] for n in beta["nodes"]}
    assert "Subsidieregeling hergebruik bouwstenen" not in titles


async def test_a_political_input_is_its_own_chain(standin):
    chain = (
        await standin.get(
            f"/v1/nodes/{_id(MAIN, 'pi_motie')}/keten", headers=_grant(MAIN)
        )
    ).json()
    assert len(chain["nodes"]) == 1
    assert chain["edges"] == []


async def test_max_depth_cuts_the_chain(standin):
    chain = (
        await standin.get(
            f"/v1/nodes/{_id(MAIN, 'opdracht_beta')}/keten",
            params={"maxDiepte": 1},
            headers=_grant(MAIN),
        )
    ).json()
    _valid("keten", chain)
    assert chain["volledig"] is False
    assert len(chain["nodes"]) == 1


async def test_the_peildatum_shows_the_earlier_title(standin):
    path = f"/v1/nodes/{_id(MAIN, 'doel_dienstverlening')}"
    before = (
        await standin.get(
            path, params={"peildatum": "2026-01-15"}, headers=_grant(MAIN)
        )
    ).json()
    after = (
        await standin.get(
            path, params={"peildatum": "2026-06-01"}, headers=_grant(MAIN)
        )
    ).json()
    assert before["titel"] == "Betere digitale dienstverlening aan burgers"
    assert after["titel"] == "Elke burger regelt overheidszaken in een keer goed"
    assert before["peildatum"] == "2026-01-15"


async def test_errors_are_problem_documents(standin):
    missing = await standin.get(
        "/v1/nodes/a0000000-0000-4000-8000-000000009999", headers=_grant(MAIN)
    )
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")
    _valid("problem", missing.json())
    # A node of the other corpus is not served under this grant.
    other = await standin.get(
        f"/v1/nodes/{_id(OTHER, 'doel_europa')}", headers=_grant(MAIN)
    )
    assert other.status_code == 404
    unknown = await standin.get("/v1/corpus", headers={GRANT_HASH_HEADER: "onbekend"})
    assert unknown.status_code == 403
    bad = await standin.get(
        f"/v1/nodes/{_id(MAIN, 'wet')}", params={"peildatum": "gisteren"}
    )
    assert bad.status_code == 400


async def test_the_corpus_client_reaches_it_as_outway(db_session: AsyncSession):
    """The real client, with the stand-in as outway: path and headers fit."""
    await seed(db_session)
    settings = get_settings().model_copy(update={"OUTWAY_URL": BASE})
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport) as http:
        client = CorpusClient(OutwayClient(settings, http), settings)
        uri = corpus_standin.node_uri("voorbeeldministerie", "opdracht_alfa")
        node = await client.get_node(db_session, uri)
        assert node["title"].startswith("Opdracht aan het Voorbeeldgilde")
        chain = await client.get_chain(db_session, uri, peildatum=date(2026, 7, 1))
        assert len(chain["nodes"]) == 5
        assert chain["external_node_uris"]
        other = await client.get_node(
            db_session, corpus_standin.node_uri("anderministerie", "opdracht_delta")
        )
        assert other["corpus"] == OTHER.base
        found = await client.search_nodes(db_session, MAIN.base, q="subsidie")
        assert found["total"] == 1


async def test_seed_registers_the_corpora_and_links_context(db_session: AsyncSession):
    await seed(db_session)
    peers = (
        (await db_session.execute(select(Peer).where(Peer.role == PEER_ROLE_CORPUS)))
        .scalars()
        .all()
    )
    assert {p.base_uri for p in peers} == {MAIN.base, OTHER.base}
    refs = dict(
        (
            await db_session.execute(select(Assignment.name, Assignment.context_refs))
        ).all()
    )
    assert len(refs["Opdracht Alfa 2026"]) == 2
    assert len(refs["Opdracht Beta 2026"]) == 1
    assert len(refs["Opdracht Epsilon 2027"]) == 1
    delta = refs["Opdracht Delta 2026-2027"]
    assert {uri.split("/id/node/")[0] for uri in delta} == {MAIN.base, OTHER.base}
    assert refs["Interne opdracht Kennisdeling 2026"] == []
    assert set(CONTEXT) <= set(refs)


async def test_extend_is_idempotent_and_removes_the_stray_draft(
    db_session: AsyncSession,
):
    await seed(db_session)
    from grip.services import assignments

    await assignments.create_assignment(db_session, name="s", actor=None)
    first = await extend(db_session)
    assert first["removed"] == 1
    second = await extend(db_session)
    assert second["changed"] == 0
    names = (await db_session.execute(select(Assignment.name))).scalars().all()
    assert "s" not in names and len(names) == 6
