"""The stand-in corpus as an ASGI app: corpus-context v1 over HTTP.

Run it with ``just corpus-standin`` (port 8040). The app answers the paths
the corpus client sends through the outway: ``/v1/corpus``,
``/v1/woordenlijst``, ``/v1/nodes``, ``/v1/nodes/{nodeId}`` and
``/v1/nodes/{nodeId}/keten``.

Which corpus answers is decided by the ``Fsc-Grant-Hash`` header, as a real
outway routes on the contract. Without the header the first corpus answers,
so the app can be tried with a plain browser or curl.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from grip.dev.corpus_standin import data
from grip.federation.contract_loader import SERVICE_CORPUS_CONTEXT, api_version
from grip.federation.outway import GRANT_HASH_HEADER

PROBLEM = "application/problem+json"
VOCABULARY = (
    Path(__file__).resolve().parents[2]
    / "federation"
    / "contract"
    / "vocabulaire"
    / "kern.json"
)


class _ProblemError(Exception):
    def __init__(self, status: int, title: str, detail: str) -> None:
        self.status = status
        self.title = title
        self.detail = detail


def _corpus(request: Request) -> data.Corpus:
    grant_hash = request.headers.get(GRANT_HASH_HEADER)
    if not grant_hash:
        return data.corpora()[0]
    corpus = data.corpus_by_grant_hash(grant_hash)
    if corpus is None:
        raise _ProblemError(
            403, "Geen toegang", "Voor deze grant hash is geen corpus bekend."
        )
    return corpus


def _peildatum(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _ProblemError(
            400, "Ongeldig verzoek", "De peildatum is een datum (jjjj-mm-dd)."
        ) from exc


def create_app() -> FastAPI:
    version = api_version(SERVICE_CORPUS_CONTEXT)
    app = FastAPI(
        title="Stand-in corpus (lokale ontwikkeling)",
        version=version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.exception_handler(_ProblemError)
    async def _problem(_: Request, exc: _ProblemError) -> JSONResponse:
        return JSONResponse(
            {"title": exc.title, "status": exc.status, "detail": exc.detail},
            status_code=exc.status,
            media_type=PROBLEM,
            headers={"API-Version": version},
        )

    def answer(body: dict[str, Any]) -> JSONResponse:
        return JSONResponse(body, headers={"API-Version": version})

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/corpus")
    async def get_corpus(request: Request) -> JSONResponse:
        return answer(data.corpus_info(_corpus(request), version))

    @app.get("/v1/woordenlijst")
    async def get_vocabulary() -> JSONResponse:
        return answer(json.loads(VOCABULARY.read_text(encoding="utf-8")))

    @app.get("/v1/nodes")
    async def search_nodes(
        request: Request,
        q: str | None = None,
        type: list[str] | None = Query(default=None),
        peildatum: str | None = None,
        page: int = Query(default=1, ge=1),
        pageSize: int = Query(default=20, ge=1, le=100),  # noqa: N803
    ) -> JSONResponse:
        return answer(
            data.search(
                _corpus(request),
                q=q,
                types=type or [],
                peildatum=_peildatum(peildatum),
                page=page,
                page_size=pageSize,
            )
        )

    @app.get("/v1/nodes/{node_id}")
    async def get_node(
        request: Request, node_id: str, peildatum: str | None = None
    ) -> JSONResponse:
        corpus = _corpus(request)
        node = corpus.node_by_id(node_id)
        if node is None:
            raise _ProblemError(404, "Niet gevonden", "Deze node bestaat niet.")
        return answer(data.node_view(corpus, node, _peildatum(peildatum)))

    @app.get("/v1/nodes/{node_id}/keten")
    async def get_chain(
        request: Request,
        node_id: str,
        peildatum: str | None = None,
        maxDiepte: int = Query(default=data.DEFAULT_MAX_DEPTH, ge=1, le=10),  # noqa: N803
    ) -> JSONResponse:
        corpus = _corpus(request)
        found = data.chain(corpus, node_id, _peildatum(peildatum), maxDiepte)
        if found is None:
            raise _ProblemError(404, "Niet gevonden", "Deze node bestaat niet.")
        return answer(found)

    return app


app = create_app()
