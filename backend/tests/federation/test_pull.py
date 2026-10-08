"""Pull operations: the provider registry, the relation and the answers."""

import uuid

import pytest

from grip.federation import signing
from grip.federation.contract_loader import (
    ContractError,
    api_version,
    load_openapi,
    operations,
    validation_errors,
)
from grip.federation.models import PEER_ROLE_CORPUS, PEER_ROLE_PARENT
from grip.federation.problems import PROBLEM_MEDIA_TYPE, FederationProblem
from grip.federation.registry import (
    register_inbound_handler,
    register_provider,
)

from .conftest import CONTRACTOR_PEER_ID, as_peer, code_example, example

ASSIGNMENT_ID = "3f2a8c54-6d1b-4f0e-9a77-1c2b3d4e5f60"

# Every pull operation with a path to call it and the example it returns.
_A = f"/v1/opdrachten/{ASSIGNMENT_ID}"
_MONTH = "maand=2026-05"
PULLS = [
    (
        "listAssignmentsByNode",
        "/v1/opdrachten?nodeUri=https://c.example/id/node/1",
        "assignment-page",
        PEER_ROLE_CORPUS,
    ),
    ("getAssignment", _A, "assignment", "counterpart"),
    ("getProgress", f"{_A}/voortgang", "progress", "counterpart"),
    ("getBudgetUsage", f"{_A}/uitputting?jaar=2026", "budget-usage", "counterpart"),
    ("getBillingData", f"{_A}/factuurgegevens?{_MONTH}", "billing-data", "counterpart"),
    (
        "getHandoverAssignments",
        "/v1/doorgifte/opdrachten",
        "handover-assignments",
        PEER_ROLE_PARENT,
    ),
    (
        "getHandoverBillingData",
        f"/v1/doorgifte/factuurgegevens?{_MONTH}",
        "handover-billing-data",
        PEER_ROLE_PARENT,
    ),
    (
        "getHandoverStaffing",
        f"/v1/doorgifte/bemensing?{_MONTH}",
        "handover-staffing",
        PEER_ROLE_PARENT,
    ),
    (
        "getHandoverCapacity",
        "/v1/doorgifte/capaciteit",
        "handover-capacity",
        PEER_ROLE_PARENT,
    ),
    (
        "getHandoverCosts",
        "/v1/doorgifte/kosten?jaar=2026",
        "handover-costs",
        PEER_ROLE_PARENT,
    ),
]


def test_every_pull_operation_of_the_contract_is_covered():
    pulls = {
        name
        for name, op in operations().items()
        if op.request_schema is None and name not in ("getJwks", "getOpenapi")
    }
    assert pulls == {row[0] for row in PULLS}


def _problem(response, status):
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert validation_errors("problem", response.json()) == []
    return response.json()


@pytest.mark.parametrize("operation,path,schema,role", PULLS)
async def test_without_provider_the_answer_is_501(
    fed_client, make_peer, operation, path, schema, role
):
    await make_peer(role=role)
    _problem(await fed_client.get(path, headers=as_peer(CONTRACTOR_PEER_ID)), 501)


@pytest.mark.parametrize("operation,path,schema,role", PULLS)
async def test_provider_answer_is_returned(
    fed_client, make_peer, operation, path, schema, role
):
    peer = await make_peer(role=role)
    seen = {}

    async def provider(db, caller, parameters):
        seen.update(peer=caller.id, parameters=parameters)
        return code_example(schema)

    register_provider(operation, provider)
    response = await fed_client.get(path, headers=as_peer(CONTRACTOR_PEER_ID))
    assert response.status_code == 200, response.text
    assert response.json() == example(schema)
    assert response.headers["API-Version"] == api_version()
    assert seen["peer"] == peer.id


async def test_provider_gets_parameters_by_their_contract_names(fed_client, make_peer):
    await make_peer(role=PEER_ROLE_CORPUS)
    seen = {}

    async def provider(db, caller, parameters):
        seen.update(parameters)
        return code_example("assignment-page")

    register_provider("listAssignmentsByNode", provider)
    await fed_client.get(
        "/v1/opdrachten",
        params={"nodeUri": "https://c.example/id/node/1", "pageSize": 5},
        headers=as_peer(CONTRACTOR_PEER_ID),
    )
    assert seen == {"nodeUri": "https://c.example/id/node/1", "page": 1, "pageSize": 5}


async def test_provider_gets_the_path_parameter_as_uuid(fed_client, make_peer):
    await make_peer()
    seen = {}

    async def provider(db, caller, parameters):
        seen.update(parameters)
        return code_example("budget-usage")

    register_provider("getBudgetUsage", provider)
    await fed_client.get(
        f"/v1/opdrachten/{ASSIGNMENT_ID}/uitputting",
        headers=as_peer(CONTRACTOR_PEER_ID),
    )
    assert seen == {"assignmentId": uuid.UUID(ASSIGNMENT_ID), "year": None}


async def test_none_from_the_provider_is_404(fed_client, make_peer):
    await make_peer()

    async def provider(db, caller, parameters):
        return None

    register_provider("getProgress", provider)
    response = await fed_client.get(
        f"/v1/opdrachten/{ASSIGNMENT_ID}/voortgang", headers=as_peer(CONTRACTOR_PEER_ID)
    )
    _problem(response, 404)


async def test_provider_can_refuse_inspection_on_request(fed_client, make_peer):
    await make_peer()

    async def provider(db, caller, parameters):
        raise FederationProblem(403, "Geen inzage", "Inzage is niet toegestaan.")

    register_provider("getBudgetUsage", provider)
    response = await fed_client.get(
        f"/v1/opdrachten/{ASSIGNMENT_ID}/uitputting",
        headers=as_peer(CONTRACTOR_PEER_ID),
    )
    assert _problem(response, 403)["detail"] == "Inzage is niet toegestaan."


async def test_answer_that_breaks_the_contract_never_leaves(fed_client, make_peer):
    await make_peer()

    async def provider(db, caller, parameters):
        body = code_example("progress")
        body.pop("status", None)
        body["updated_at"] = "gisteren"
        return body

    register_provider("getProgress", provider)
    response = await fed_client.get(
        f"/v1/opdrachten/{ASSIGNMENT_ID}/voortgang", headers=as_peer(CONTRACTOR_PEER_ID)
    )
    _problem(response, 500)
    assert "gisteren" not in response.text


@pytest.mark.parametrize(
    "path",
    [
        "/v1/doorgifte/factuurgegevens",
        "/v1/doorgifte/factuurgegevens?maand=2026-13",
        "/v1/doorgifte/kosten?jaar=1999",
        "/v1/opdrachten",
        "/v1/opdrachten?nodeUri=x&pageSize=101",
        "/v1/opdrachten/geen-uuid/voortgang",
    ],
)
async def test_invalid_or_missing_parameter_is_a_400_problem(
    fed_client, make_peer, path
):
    await make_peer(role=PEER_ROLE_PARENT)
    await make_peer(
        "00000000000000000009", base_uri="https://c.example", role=PEER_ROLE_CORPUS
    )
    for peer_id in (CONTRACTOR_PEER_ID, "00000000000000000009"):
        response = await fed_client.get(path, headers=as_peer(peer_id))
        if response.status_code == 403:
            continue
        _problem(response, 400)
        return
    raise AssertionError("no peer was allowed to reach the parameter check")


@pytest.mark.parametrize("operation,path,schema,role", PULLS)
async def test_peer_without_the_relation_gets_403_and_no_data(
    fed_client, make_peer, operation, path, schema, role
):
    wrong = PEER_ROLE_CORPUS if role != PEER_ROLE_CORPUS else PEER_ROLE_PARENT
    await make_peer(role=wrong)
    called = []

    async def provider(db, caller, parameters):
        called.append(1)
        return code_example(schema)

    register_provider(operation, provider)
    response = await fed_client.get(path, headers=as_peer(CONTRACTOR_PEER_ID))
    _problem(response, 403)
    assert called == []


async def test_counterpart_is_not_a_parent(fed_client, make_peer):
    await make_peer()
    response = await fed_client.get(
        "/v1/doorgifte/bemensing?maand=2026-05", headers=as_peer(CONTRACTOR_PEER_ID)
    )
    _problem(response, 403)


def test_registries_only_take_operations_of_the_right_kind():
    async def noop(*_args):
        return None

    with pytest.raises(ContractError):
        register_provider("sendQuote", noop)
    with pytest.raises(ContractError):
        register_inbound_handler("getProgress", noop)
    with pytest.raises(ContractError):
        register_provider("bestaatNiet", noop)


async def test_jwks_gives_the_public_keys_of_this_instance(
    fed_client, fed_settings, make_peer
):
    await make_peer()
    response = await fed_client.get("/v1/jwks", headers=as_peer(CONTRACTOR_PEER_ID))
    assert response.status_code == 200
    body = response.json()
    assert validation_errors("jwks", body) == []
    assert body == signing.own_jwks(fed_settings)
    assert all("d" not in key for key in body["keys"])


async def test_the_contract_is_served_on_v1_openapi_json(fed_client, make_peer):
    await make_peer()
    response = await fed_client.get(
        "/v1/openapi.json", headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert response.status_code == 200
    assert response.json() == load_openapi("grip-opdrachtverkeer")
    assert response.headers["API-Version"] == api_version()


async def test_health_needs_no_peer(fed_client):
    assert (await fed_client.get("/healthz")).json() == {"status": "ok"}
