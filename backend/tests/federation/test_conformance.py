"""The federation routes against the vendored contract.

Follows docs/conformance.md of the contract repo: every operation, query
parameter and success response of the contract must be present. On top of
that the schemas the routes declare must be the contract's own, and every
route must depend on the peer check.
"""

from typing import Any

from fastapi import routing
from fastapi.routing import APIRoute

from grip.federation.app import HEALTH_PATH, generated_openapi
from grip.federation.contract_loader import (
    PATH_PREFIX,
    SERVICE_OPDRACHTVERKEER,
    load_openapi,
    load_schemas,
)

_METHODS = ("get", "put", "post", "delete", "patch")


def _resolve(document: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    ref = item.get("$ref")
    if not ref:
        return item
    node: Any = document
    for key in ref[2:].split("/"):
        node = node[key]
    return node


def _parameters(document, operation, where):
    return {
        parameter["name"]: parameter
        for parameter in (
            _resolve(document, p) for p in operation.get("parameters", [])
        )
        if parameter["in"] == where
    }


def _body_schema(document, item):
    content = _resolve(document, item).get("content", {})
    return {
        media: spec.get("schema", {}).get("$ref") for media, spec in content.items()
    }


def _differences(contract: dict[str, Any], generated: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for path, item in contract["paths"].items():
        other = generated["paths"].get(PATH_PREFIX + path)
        for method in (m for m in _METHODS if m in item):
            label = f"{method.upper()} {path}"
            wanted = item[method]
            offered = (other or {}).get(method)
            if offered is None:
                problems.append(f"{label}: missing")
                continue
            if offered.get("operationId") != wanted["operationId"]:
                problems.append(f"{label}: operationId {offered.get('operationId')}")
            for where in ("query", "path"):
                wanted_parameters = _parameters(contract, wanted, where)
                offered_parameters = _parameters(generated, offered, where)
                for name, parameter in wanted_parameters.items():
                    if name not in offered_parameters:
                        problems.append(f"{label}: {where} parameter {name} missing")
                    elif bool(parameter.get("required")) != bool(
                        offered_parameters[name].get("required")
                    ):
                        problems.append(f"{label}: {name} required differs")
                extra = set(offered_parameters) - set(wanted_parameters)
                if extra:
                    problems.append(
                        f"{label}: extra {where} parameters {sorted(extra)}"
                    )
            if ("requestBody" in wanted) != ("requestBody" in offered):
                problems.append(f"{label}: request body presence differs")
            elif "requestBody" in wanted and _body_schema(
                contract, wanted["requestBody"]
            ) != _body_schema(generated, offered["requestBody"]):
                problems.append(f"{label}: request schema differs")
            for status, response in wanted["responses"].items():
                if status not in offered["responses"]:
                    problems.append(f"{label}: response {status} missing")
                elif _body_schema(contract, response) != _body_schema(
                    generated, offered["responses"][status]
                ):
                    problems.append(f"{label}: schema of response {status} differs")
            for extension in (
                "x-grip-caller",
                "x-grip-data-class",
                "x-grip-on-request",
            ):
                if wanted.get(extension) != offered.get(extension):
                    problems.append(f"{label}: {extension} differs")
    return problems


def test_generated_openapi_matches_the_contract(fed_app):
    contract = load_openapi(SERVICE_OPDRACHTVERKEER)
    assert _differences(contract, generated_openapi(fed_app)) == []


def test_no_operations_beyond_the_contract(fed_app):
    contract = load_openapi(SERVICE_OPDRACHTVERKEER)
    wanted = {
        (method, PATH_PREFIX + path)
        for path, item in contract["paths"].items()
        for method in _METHODS
        if method in item
    }
    offered = {
        (method, path)
        for path, item in generated_openapi(fed_app)["paths"].items()
        for method in _METHODS
        if method in item
    }
    assert offered == wanted


def test_schemas_in_the_generated_document_are_the_contract_schemas(fed_app):
    generated = generated_openapi(fed_app)["components"]["schemas"]
    contract = load_openapi(SERVICE_OPDRACHTVERKEER)["components"]["schemas"]
    assert {name: generated[name] for name in load_schemas()} == contract


def test_the_comparison_notices_a_difference(fed_app):
    """The guard itself must work."""
    contract = load_openapi(SERVICE_OPDRACHTVERKEER)
    generated = generated_openapi(fed_app)
    del generated["paths"]["/v1/quotes"]
    generated["paths"]["/v1/handover/costs"]["get"]["parameters"] = []
    generated["paths"]["/v1/jwks"]["get"]["responses"]["200"]["content"] = {
        "application/json": {"schema": {"$ref": "#/components/schemas/receipt"}}
    }
    assert _differences(contract, generated) == [
        "POST /quotes: missing",
        "GET /handover/costs: query parameter year missing",
        "GET /jwks: schema of response 200 differs",
    ]


def _routes(app) -> list[tuple[str, Any]]:
    """Path and effective dependant of every route.

    Recent FastAPI versions keep included routers as lazy nodes, so a plain
    loop over ``app.routes`` misses them (see the inventory test of the main
    app, which resolves them the same way).
    """
    iter_contexts = getattr(routing, "iter_route_contexts", None)
    if iter_contexts is None:
        return [(r.path, r.dependant) for r in app.routes if isinstance(r, APIRoute)]
    found = []
    for context in iter_contexts(app.routes):
        if isinstance(context.original_route, APIRoute):
            effective = getattr(context, "_effective_route", context.original_route)
            found.append((context.path, effective.dependant))
    return found


def _has_peer_check(dependant) -> bool:
    names = {"get_current_peer", "_peer_check"}

    def walk(dependencies) -> bool:
        return any(
            getattr(dep.call, "__name__", "") in names or walk(dep.dependencies)
            for dep in dependencies
        )

    return walk(dependant.dependencies)


def test_every_federation_route_depends_on_the_peer_check(fed_app):
    routes = _routes(fed_app)
    assert len(routes) >= 20, "route discovery found too little"
    unprotected = sorted(path for path, dep in routes if not _has_peer_check(dep))
    # The health probe is the one route without a peer.
    assert unprotected == [HEALTH_PATH]


def test_the_peer_check_guard_notices_an_open_route():
    """The guard itself must work."""
    from fastapi import APIRouter, FastAPI

    from grip.federation.peers import CurrentPeer

    router = APIRouter()

    @router.get("/open")
    async def _open() -> dict:
        return {}

    @router.get("/closed")
    async def _closed(_peer: CurrentPeer) -> dict:
        return {}

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    assert {path: _has_peer_check(dep) for path, dep in _routes(app)} == {
        "/v1/open": False,
        "/v1/closed": True,
    }


def test_federation_routes_are_not_part_of_the_main_app(_test_app):
    """The main app is reachable by browsers; these routes trust a header."""
    document = _test_app.openapi()
    assert not [
        path
        for path in document["paths"]
        if "/quotes" in path or "/handover" in path or path.endswith("/jwks")
    ]
