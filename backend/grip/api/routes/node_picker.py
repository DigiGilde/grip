"""The node picker and resolved context.

An assignment carries node URIs as context. The nodes live in corpus
systems (one per ministry, for example); this instance asks them through
its outway, under the contract it has with each corpus. A corpus that is
not configured or does not answer never blocks the user: the answer says
why, and a URI stays usable as a bare URI.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from grip.access import Action, DataClass, Resource, build_response
from grip.api.assignment_support import DbSession, RequestAccess
from grip.core.config import Settings, get_settings
from grip.federation.corpus import (
    CorpusClient,
    CorpusContractError,
    CorpusError,
    CorpusUnavailableError,
    NodeNotFoundError,
    UnknownCorpusError,
)
from grip.federation.outway import OutwayClient
from grip.federation.peers import normalize_uri
from grip.federation.routes import get_outway_client
from grip.schema.nodes import (
    ChainOut,
    ContextOut,
    CorporaOut,
    CorpusOut,
    EdgeOut,
    NodeLookupOut,
    NodeOrganisationOut,
    NodeOut,
    NodeSearchOut,
)
from grip.services import client_side
from grip.services.assignments import get_assignment

router = APIRouter(tags=["nodes"])

_A = frozenset({DataClass.ASSIGNMENT_BASIC})

NO_CORPUS = (
    "Er is geen corpus gekoppeld aan deze instantie. Je kunt doorgaan zonder "
    "context, of een node-URI plakken."
)
NO_OUTWAY = (
    "Deze instantie is niet verbonden met andere organisaties, dus een corpus "
    "kan niet worden bevraagd. Je kunt doorgaan zonder context."
)

# One client per outway, so the short cache of resolved nodes is shared by
# the requests of this process. The outway is kept with it: comparing by
# identity is only safe while the object is alive.
_shared: list[tuple[OutwayClient, CorpusClient]] = []


def get_corpus_client(
    outway: OutwayClient = Depends(get_outway_client),
    settings: Settings = Depends(get_settings),
) -> CorpusClient:
    if _shared and _shared[0][0] is outway:
        return _shared[0][1]
    client = CorpusClient(outway, settings)
    _shared[:] = [(outway, client)]
    return client


Corpus = Annotated[CorpusClient, Depends(get_corpus_client)]


def describe_corpus_error(error: CorpusError) -> str:
    """Why a corpus gave no answer, as a sentence for the user."""
    if isinstance(error, UnknownCorpusError):
        return (
            "Voor deze URI is geen corpus gekoppeld aan deze instantie. "
            "De URI blijft bewaard zoals hij is."
        )
    if isinstance(error, NodeNotFoundError):
        return "Het corpus kent deze node niet, of toont hem niet aan deze instantie."
    if isinstance(error, CorpusContractError):
        return "Het corpus gaf een antwoord dat niet aan het contract voldoet."
    if isinstance(error, CorpusUnavailableError):
        return "Het corpus is nu niet bereikbaar. Probeer het later opnieuw."
    return "Het corpus kon niet worden bevraagd."


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def node_out(node: dict[str, Any]) -> NodeOut:
    validity = node.get("validity") or {}
    organisation = node.get("managing_organisation")
    return NodeOut(
        uri=node["uri"],
        type=node["type"],
        title=node["title"],
        description=node.get("description"),
        status=node.get("status"),
        corpus=node.get("corpus"),
        managing_organisation=NodeOrganisationOut(
            name=organisation.get("name"), tooi_uri=organisation.get("tooi_uri")
        )
        if organisation
        else None,
        valid_from=_date(validity.get("start_date")),
        valid_until=_date(validity.get("end_date")),
        peildatum=_date(node.get("peildatum")),
        type_details=node.get("type_details"),
    )


def chain_out(chain: dict[str, Any]) -> ChainOut:
    return ChainOut(
        nodes=[node_out(node) for node in chain.get("nodes") or []],
        edges=[
            EdgeOut(from_uri=edge["from"], to_uri=edge["to"], type=edge["type"])
            for edge in chain.get("edges") or []
        ],
        external_node_uris=list(chain.get("external_node_uris") or []),
        complete=bool(chain.get("complete", True)),
    )


async def resolve(
    db: DbSession, corpus: CorpusClient, uri: str, peildatum: date | None
) -> NodeLookupOut:
    """A node URI with its node and chain, or the reason it stays a bare URI.

    A chain that cannot be fetched does not hide the node: title and type
    are worth showing on their own.
    """
    try:
        node = await corpus.get_node(db, uri, peildatum=peildatum)
    except CorpusError as error:
        return NodeLookupOut(
            uri=uri, resolved=False, problem=describe_corpus_error(error)
        )
    try:
        chain = chain_out(await corpus.get_chain(db, uri, peildatum=peildatum))
    except CorpusError:
        chain = None
    return NodeLookupOut(uri=uri, resolved=True, node=node_out(node), chain=chain)


async def _require_picker(access: RequestAccess) -> None:
    """Whoever may start an assignment, as client or as contractor."""
    for action in (
        Action.REQUEST_ASSIGNMENT,
        Action.CREATE_ASSIGNMENT,
        Action.MANAGE_USERS,
    ):
        if await access.may(action, Resource.instance()):
            return
    raise HTTPException(status_code=403, detail="Je hebt hier geen toegang toe")


@router.get("/nodes/corpora", response_model=None)
async def list_corpora(
    access: RequestAccess,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """The corpora this instance can search."""
    await _require_picker(access)
    peers = await client_side.corpus_peers(db)
    outway = bool(settings.OUTWAY_URL)
    corpora = [
        CorpusOut(
            base_uri=normalize_uri(peer.base_uri),
            name=peer.name,
            searchable=outway
            and client_side.has_grant(peer, client_side.SERVICE_CORPUS_CONTEXT),
        )
        for peer in peers
    ]
    problem = None
    if not corpora:
        problem = NO_CORPUS
    elif not outway:
        problem = NO_OUTWAY
    elif not any(corpus.searchable for corpus in corpora):
        problem = (
            "Met geen van de gekoppelde corpora is een contract voor het "
            "opvragen van nodes vastgelegd. Je kunt doorgaan zonder context."
        )
    return build_response(CorporaOut(corpora=corpora, problem=problem), _A)


@router.get("/nodes/search", response_model=None)
async def search_nodes(
    access: RequestAccess,
    db: DbSession,
    client: Corpus,
    corpus: Annotated[str, Query(min_length=8, max_length=500)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    type: Annotated[list[str] | None, Query()] = None,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict[str, Any]:
    """Search the nodes of one corpus."""
    await _require_picker(access)
    try:
        found = await client.search_nodes(
            db,
            corpus,
            q=(q or "").strip() or None,
            types=type or None,
            page=page,
            page_size=page_size,
        )
    except CorpusError as error:
        return build_response(
            NodeSearchOut(
                page=page, page_size=page_size, problem=describe_corpus_error(error)
            ),
            _A,
        )
    return build_response(
        NodeSearchOut(
            results=[node_out(node) for node in found.get("results") or []],
            page=found.get("page", page),
            page_size=found.get("page_size", page_size),
            total=found.get("total", 0),
        ),
        _A,
    )


@router.get("/nodes/lookup", response_model=None)
async def lookup_node(
    access: RequestAccess,
    db: DbSession,
    client: Corpus,
    uri: Annotated[str, Query(min_length=8, max_length=500)],
    peildatum: date | None = None,
) -> dict[str, Any]:
    """One node by URI, with its chain up to the political input."""
    await _require_picker(access)
    return build_response(await resolve(db, client, uri.strip(), peildatum), _A)


@router.get("/assignments/{assignment_id}/context", response_model=None)
async def assignment_context(
    assignment_id: UUID,
    access: RequestAccess,
    db: DbSession,
    client: Corpus,
    peildatum: Annotated[
        str | None,
        Query(
            description=(
                "A date, 'acceptance' for the day the quote was accepted, "
                "or nothing for today."
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """The context URIs of an assignment resolved to titles and chains."""
    await access.require(
        Action.READ,
        Resource.assignment(assignment_id),
        DataClass.ASSIGNMENT_BASIC,
        hide_existence=True,
    )
    assignment = await get_assignment(db, assignment_id)
    accepted_on = await client_side.acceptance_date(db, assignment.id)
    if peildatum in (None, "", "today"):
        as_of = date.today()
    elif peildatum == "acceptance":
        if accepted_on is None:
            raise HTTPException(
                status_code=422,
                detail="Op deze opdracht is nog geen offerte geaccepteerd.",
            )
        as_of = accepted_on
    else:
        parsed = _date(peildatum)
        if parsed is None:
            raise HTTPException(
                status_code=422,
                detail="De peildatum is een datum (jjjj-mm-dd) of 'acceptance'.",
            )
        as_of = parsed
    items = [
        await resolve(db, client, uri, as_of) for uri in assignment.context_refs or []
    ]
    return build_response(
        ContextOut(peildatum=as_of, acceptance_date=accepted_on, items=items), _A
    )
