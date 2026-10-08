"""The vendored contract: examples, hashes and the operation table."""

import json

import pytest

from grip.federation import signing
from grip.federation.contract_loader import (
    SERVICE_CORPUS_CONTEXT,
    api_version,
    contract_version,
    example_files,
    load_openapi,
    load_schemas,
    operation,
    operations,
    schema_of_example,
    validation_errors,
)

from .conftest import example


@pytest.mark.parametrize("path", example_files("valid"), ids=lambda p: p.name)
def test_valid_example_is_accepted(path):
    assert (
        validation_errors(schema_of_example(path), json.loads(path.read_text())) == []
    )


@pytest.mark.parametrize("path", example_files("invalid"), ids=lambda p: p.name)
def test_invalid_example_is_rejected(path):
    assert validation_errors(schema_of_example(path), json.loads(path.read_text()))


def test_there_are_examples():
    assert len(example_files("valid")) >= 30
    assert len(example_files("invalid")) >= 10


def test_version_record_names_commit_and_versions():
    record = contract_version()
    assert len(record["commit"]) == 40
    assert record["modified"] is False
    assert api_version() == load_openapi("grip-opdrachtverkeer")["info"]["version"]


@pytest.mark.parametrize("name", ["quote", "quote.eigen-initiatief"])
def test_quote_example_hash_is_sha256_of_canonical_snapshot(name):
    quote = example(name)
    assert signing.snapshot_hash(quote["snapshot"]) == quote["snapshot_hash"]


def test_acceptance_example_verifies_against_example_keys():
    signing.verify_acceptance(example("acceptance"), example("jwks"))


def test_format_checks_are_real():
    # jsonschema skips date-time and uri without optional packages; the
    # loader checks them itself.
    quote = example("quote")
    assert validation_errors("quote", {**quote, "issued_at": "2026-06-01 10:00"})
    assert validation_errors("quote", {**quote, "issued_at": "2026-06-01T10:00:00"})
    assert validation_errors("quote", {**quote, "uri": "geen uri"})
    assert validation_errors("quote", {**quote, "id": "geen-uuid"})


def test_operation_table():
    ops = operations()
    assert len(ops) == 18
    quote = operation("sendQuote")
    assert (quote.method, quote.path, quote.caller) == ("POST", "/quotes", "contractor")
    assert quote.request_schema == "quote"
    assert quote.response_schemas["201"] == "receipt"
    assert operation("getBudgetUsage").on_request is True
    assert operation("getBillingData").required_query_parameters == ("month",)
    assert (
        operation("sendAcceptance").url_path(quoteId="x") == "/v1/quotes/x/acceptances"
    )
    assert set(operations(SERVICE_CORPUS_CONTEXT)) == {
        "getCorpus",
        "getVocabulary",
        "searchNodes",
        "getNode",
        "getNodeChain",
    }


def test_bundled_openapi_has_no_file_references():
    for service in ("grip-opdrachtverkeer", SERVICE_CORPUS_CONTEXT):
        text = json.dumps(load_openapi(service))
        assert ".schema.json" not in text
        assert set(load_openapi(service)["components"]["schemas"]) == set(
            load_schemas()
        )
