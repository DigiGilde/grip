"""A dev outway: what an FSC outway and inway do together, without FSC.

For local development with a real counterpart (a Bouwmeester, a second
grip) but without certificates, managers and contracts. An application
sends a request to "its outway" with a grant hash, exactly as it does with
FSC. This process looks the grant hash up in a routes file, forwards the
request to the service of the other party and sets the peer id of the
caller in the header a real inway would set. So both applications run their
real federation code; only the transport between them is a stand-in.

Run it with ``just dev-outway`` (port 9230). The routes file is JSON::

    {
      "fallback": "http://localhost:8040",
      "routes": {
        "<grant hash>": {
          "target": "http://localhost:9211",
          "caller_peer_id": "01700000000000000001",
          "note": "grip -> corpus-context of the local Bouwmeester"
        }
      }
    }

``target`` is the service behind the other party's inway, without a path.
A route without ``caller_peer_id`` passes the request on unchanged; use it
to send a real FSC grant hash on to a real outway. ``caller_peer_id`` is who
the other party will believe is calling, so the
file is the whole trust model here: never run this anywhere but on your own
machine. A request with a grant hash that is not in the file goes to
``fallback`` unchanged (the stand-in corpus, which routes on the grant hash
itself), or is refused when there is no fallback.

The file is read again when it changes, so a route can be added while the
process runs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

# Not imported from grip.federation: this process has no settings and no
# database, and must start without either.
GRANT_HASH_HEADER = "Fsc-Grant-Hash"
PEER_ID_HEADER = "Fsc-Request-Peer-Id"
ROUTES_ENV = "DEV_OUTWAY_ROUTES"
PROBLEM = "application/problem+json"

# Headers that describe one connection and must not travel to the next.
_HOP_BY_HOP = frozenset(
    {
        "connection",
        "content-length",
        "content-encoding",
        "host",
        "keep-alive",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


class RouteTable:
    """The routes file, reloaded when its modification time changes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._mtime: float | None = None
        self._data: dict[str, Any] = {"routes": {}}

    def _load(self) -> dict[str, Any]:
        try:
            mtime = self._path.stat().st_mtime
        except FileNotFoundError:
            self._mtime = None
            self._data = {"routes": {}}
            return self._data
        if mtime != self._mtime:
            self._data = json.loads(self._path.read_text())
            self._mtime = mtime
        return self._data

    def route(self, grant_hash: str) -> dict[str, Any] | None:
        route = self._load().get("routes", {}).get(grant_hash)
        return route if isinstance(route, dict) else None

    @property
    def fallback(self) -> str:
        return str(self._load().get("fallback") or "")


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        {"title": title, "status": status, "detail": detail},
        status_code=status,
        media_type=PROBLEM,
    )


def create_app(routes_path: Path | None = None) -> FastAPI:
    path = routes_path or Path(os.environ.get(ROUTES_ENV, "dev-outway.json"))
    table = RouteTable(path)
    client = httpx.AsyncClient(timeout=20.0)

    app = FastAPI(
        title="Dev outway (lokale ontwikkeling)",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.api_route(
        "/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
    )
    async def forward(path: str, request: Request) -> Response:
        grant_hash = request.headers.get(GRANT_HASH_HEADER, "")
        route = table.route(grant_hash) if grant_hash else None

        headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() not in _HOP_BY_HOP
            # The caller never gets to say who it is.
            and name.lower() != PEER_ID_HEADER.lower()
        }
        if route is not None:
            target = str(route["target"]).rstrip("/")
            # Without a caller the route passes the request on as it is, to
            # a real outway that knows the grant hash.
            if route.get("caller_peer_id"):
                headers[PEER_ID_HEADER] = str(route["caller_peer_id"])
        elif table.fallback:
            target = table.fallback.rstrip("/")
        else:
            return _problem(
                403,
                "Geen toegang",
                "Voor deze grant hash staat geen route in het routesbestand.",
            )

        try:
            upstream = await client.request(
                request.method,
                f"{target}/{path}",
                params=request.query_params,
                headers=headers,
                content=await request.body(),
            )
        except httpx.HTTPError as exc:
            return _problem(
                502,
                "Dienst niet bereikbaar",
                f"{target} gaf geen antwoord ({type(exc).__name__}).",
            )
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers={
                name: value
                for name, value in upstream.headers.items()
                if name.lower() not in _HOP_BY_HOP
            },
        )

    return app
