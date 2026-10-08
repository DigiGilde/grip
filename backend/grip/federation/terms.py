"""Contract terms at the federation boundary.

The mapping itself is a document format and lives with the domain services
(:mod:`grip.services.terms`), because the canonical form of a quote uses it
too. This module only makes it available under the name the federation code
has always used.
"""

from grip.services.terms import (
    OPAQUE,
    PARAMETERS,
    PROPERTIES,
    SCHEMAS,
    VALUES,
    Verbatim,
    code_parameter,
    code_value,
    contract_parameter,
    contract_value,
    from_contract,
    schema,
    term,
    to_contract,
)

__all__ = [
    "OPAQUE",
    "PARAMETERS",
    "PROPERTIES",
    "SCHEMAS",
    "VALUES",
    "Verbatim",
    "code_parameter",
    "code_value",
    "contract_parameter",
    "contract_value",
    "from_contract",
    "schema",
    "term",
    "to_contract",
]
