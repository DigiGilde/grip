"""The mapping between contract terms and code names."""

import json

import pytest

from grip.federation import terms
from grip.federation.contract_loader import example_files, load_schemas
from grip.services.terms import PENDING_CONTRACT_TERMS

# Contract terms that are the same in code: from standards, technical, or
# already domain vocabulary on both sides.
SAME_ON_BOTH_SIDES = {
    "id",
    "uri",
    "type",
    "status",
    "jws",
    "sha256",
    "email",
    "fte",
    "fte_pct",
    "pct",
    "page",
    "page_size",
    "peildatum",
    "corpus",
    "nodes",
    "edges",
    "start",
    "document",
    "document_sha256",
    "label_nl",
    "tooi_uri",
    "type_details",
    "contact_email",
    "errors",
    "keys",
    # Members of a problem document (RFC 9457).
    "title",
    "detail",
    "instance",
}
UNTRANSLATED_SCHEMAS = {"problem", "jwks"}


def _properties(node, found, opaque=False):
    if isinstance(node, dict):
        for name, sub in (node.get("properties") or {}).items():
            if not opaque:
                found.add(name)
            _properties(sub, found, opaque or name in terms.OPAQUE)
        for key, sub in node.items():
            if key != "properties":
                _properties(sub, found, opaque)
    elif isinstance(node, list):
        for sub in node:
            _properties(sub, found, opaque)


def test_every_contract_property_has_a_code_name():
    """A term added to the contract and forgotten in the mapping fails here."""
    found: set[str] = set()
    for name, schema in load_schemas().items():
        if name not in UNTRANSLATED_SCHEMAS:
            _properties(schema, found)
    known = set(terms.PROPERTIES.values()) | SAME_ON_BOTH_SIDES
    assert found - known == set()
    # And the other way around: no mapping for a term the contract dropped.
    # Except what grip uses ahead of the contract, which is listed as such.
    assert set(terms.PROPERTIES.values()) - found == set(PENDING_CONTRACT_TERMS)


def test_no_code_name_leaks_into_the_contract():
    found: set[str] = set()
    for name, schema in load_schemas().items():
        if name not in UNTRANSLATED_SCHEMAS:
            _properties(schema, found)
    assert found & (set(terms.PROPERTIES) - SAME_ON_BOTH_SIDES) == set()


def test_every_schema_name_is_mapped():
    assert set(terms.SCHEMAS.values()) == set(load_schemas())


@pytest.mark.parametrize("path", example_files("valid"), ids=lambda p: p.name)
def test_translation_is_reversible(path):
    """What crosses the boundary survives a round trip through code names."""
    message = json.loads(path.read_text())
    if path.name.split(".")[0] in UNTRANSLATED_SCHEMAS:
        return
    assert terms.to_contract(terms.from_contract(message)) == message


def test_values_of_code_lists_are_translated_both_ways():
    code = {
        "kind": "external",
        "status": "in_progress",
        "lines": [{"kind": "personnel"}],
        "form": "own_instance",
        "outcome": "duplicate",
    }
    contract = terms.to_contract(code)
    assert contract == {
        "soort": "extern",
        "status": "in_uitvoering",
        "regels": [{"soort": "personeel"}],
        "vorm": "eigen_instantie",
        "uitkomst": "duplicaat",
    }
    assert terms.from_contract(contract) == code


def test_node_details_and_keys_are_left_alone():
    node = {"titel": "Doel", "type_details": {"soort": "wetgeving", "datum": None}}
    assert terms.from_contract(node) == {
        "title": "Doel",
        "type_details": {"soort": "wetgeving", "datum": None},
    }
    jwks = {"keys": [{"kty": "EC", "kid": "a", "use": "sig"}]}
    assert terms.to_contract(jwks) == jwks


def test_a_value_outside_the_code_list_passes_unchanged():
    # A node status is free text; only the listed statuses are translated.
    assert terms.from_contract({"status": "actief"}) == {"status": "actief"}


def test_parameters():
    assert terms.contract_parameter("quoteId") == "offerteId"
    assert terms.code_parameter("maand") == "month"
    assert terms.contract_parameter("page") == "page"
