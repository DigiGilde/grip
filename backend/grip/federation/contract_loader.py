"""Read access to the vendored contract.

Everything grip knows about the shapes that cross an organisation boundary
comes from the files under ``contract/``: the schemas for validation, the
OpenAPI documents for the operation table and for serving the contract.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACT_DIR = Path(__file__).parent / "contract"

SERVICE_OPDRACHTVERKEER = "grip-opdrachtverkeer"
SERVICE_CORPUS_CONTEXT = "corpus-context"

_OPENAPI_FILES = {
    SERVICE_OPDRACHTVERKEER: "opdrachtverkeer/v1/openapi.yaml",
    SERVICE_CORPUS_CONTEXT: "corpus-context/v1/openapi.yaml",
}

# The version segment every contract path is served under.
PATH_PREFIX = "/v1"

_SCHEMA_SUFFIX = ".schema.json"
_METHODS = ("get", "put", "post", "delete", "patch")


class ContractError(Exception):
    """The vendored contract is missing something the code relies on."""


@cache
def contract_version() -> dict[str, Any]:
    """The commit and versions the vendored copy was taken from."""
    return json.loads((CONTRACT_DIR / "CONTRACT_VERSION.json").read_text())


def api_version(service: str = SERVICE_OPDRACHTVERKEER) -> str:
    return contract_version()["versions"][service]


@cache
def load_schemas() -> dict[str, dict[str, Any]]:
    """All schemas, keyed by name without the ``.schema.json`` suffix."""
    return {
        path.name.removesuffix(_SCHEMA_SUFFIX): json.loads(path.read_text())
        for path in sorted((CONTRACT_DIR / "schemas").glob(f"*{_SCHEMA_SUFFIX}"))
    }


# --- format checks ---------------------------------------------------------
#
# jsonschema only checks ``date-time`` and ``uri`` when optional packages are
# installed, and silently accepts anything otherwise. The contract leans on
# both formats, so they are checked here explicitly.

_format_checker = FormatChecker(formats=())

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@_format_checker.checks("uuid", raises=ValueError)
def _is_uuid(value: object) -> bool:
    if isinstance(value, str):
        UUID(value)
    return True


@_format_checker.checks("date", raises=ValueError)
def _is_date(value: object) -> bool:
    if isinstance(value, str):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return False
        date.fromisoformat(value)
    return True


@_format_checker.checks("date-time", raises=ValueError)
def _is_date_time(value: object) -> bool:
    if isinstance(value, str):
        if "T" not in value.upper():
            return False
        # RFC 3339 requires an offset; a naive timestamp is ambiguous
        # between organisations.
        return datetime.fromisoformat(value).tzinfo is not None
    return True


@_format_checker.checks("uri")
def _is_uri(value: object) -> bool:
    if isinstance(value, str):
        parts = urlsplit(value)
        return bool(parts.scheme) and bool(parts.netloc or parts.path)
    return True


@_format_checker.checks("email")
def _is_email(value: object) -> bool:
    return not isinstance(value, str) or bool(_EMAIL.fullmatch(value))


@cache
def _registry() -> Registry:
    # The schemas refer to each other by file name ("money.schema.json").
    resources = [
        (
            f"{name}{_SCHEMA_SUFFIX}",
            Resource.from_contents(schema, default_specification=DRAFT202012),
        )
        for name, schema in load_schemas().items()
    ]
    return Registry().with_resources(resources)


@cache
def validator_for(schema_name: str) -> Draft202012Validator:
    schemas = load_schemas()
    if schema_name not in schemas:
        raise ContractError(f"No schema named {schema_name!r} in the contract")
    return Draft202012Validator(
        {"$ref": f"{schema_name}{_SCHEMA_SUFFIX}"},
        registry=_registry(),
        format_checker=_format_checker,
    )


def validation_errors(schema_name: str, instance: Any) -> list[str]:
    """Human-readable violations of ``instance`` against a contract schema."""
    errors = sorted(
        validator_for(schema_name).iter_errors(instance),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '(root)'}: "
        f"{error.message}"
        for error in errors
    ]


# --- OpenAPI ---------------------------------------------------------------


def _schema_name_from_ref(ref: str) -> str | None:
    name = ref.rsplit("/", 1)[-1]
    if name.endswith(_SCHEMA_SUFFIX):
        return name.removesuffix(_SCHEMA_SUFFIX)
    return None


def _rewrite_refs(node: Any) -> Any:
    """Point file references at ``#/components/schemas`` instead."""
    if isinstance(node, dict):
        rewritten = {key: _rewrite_refs(value) for key, value in node.items()}
        ref = rewritten.get("$ref")
        if isinstance(ref, str):
            name = _schema_name_from_ref(ref)
            if name is not None:
                rewritten["$ref"] = f"#/components/schemas/{name}"
        return rewritten
    if isinstance(node, list):
        return [_rewrite_refs(item) for item in node]
    return node


@cache
def load_openapi(service: str) -> dict[str, Any]:
    """The OpenAPI document of a service as one self-contained document.

    The source files refer to the schemas by relative path; here those
    schemas are placed under ``components.schemas``. This is the document an
    implementation serves on ``/v1/openapi.json``.
    """
    document = yaml.safe_load((CONTRACT_DIR / _OPENAPI_FILES[service]).read_text())
    document = _rewrite_refs(document)
    components = document.setdefault("components", {})
    components["schemas"] = {
        name: _rewrite_refs(
            {key: value for key, value in schema.items() if key != "$schema"}
        )
        for name, schema in load_schemas().items()
    }
    return document


def _resolve(document: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    ref = item.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return item
    node: Any = document
    for key in ref[2:].split("/"):
        node = node[key]
    return node


def _content_schema(document: dict[str, Any], item: dict[str, Any]) -> str | None:
    """Name of the schema of the first content type of a body or response."""
    for media in _resolve(document, item).get("content", {}).values():
        ref = media.get("schema", {}).get("$ref")
        if isinstance(ref, str):
            return ref.rsplit("/", 1)[-1]
    return None


@dataclass(frozen=True)
class Operation:
    """One operation of a contract service."""

    service: str
    operation_id: str
    method: str
    # Path as in the contract, without the version prefix.
    path: str
    # The relation the caller must have: client, contractor, parent, corpus, peer.
    caller: str | None
    data_classes: tuple[str, ...]
    on_request: bool
    request_schema: str | None
    # Status code to schema name, for every response that has a body.
    response_schemas: dict[str, str]
    query_parameters: tuple[str, ...]
    required_query_parameters: tuple[str, ...]
    path_parameters: tuple[str, ...]

    @property
    def success_schema(self) -> str | None:
        for status, schema in self.response_schemas.items():
            if status.startswith("2"):
                return schema
        return None

    def url_path(self, **path_parameters: str) -> str:
        """The path to call, with the version prefix and parameters filled in."""
        return PATH_PREFIX + self.path.format(**path_parameters)


@cache
def operations(service: str = SERVICE_OPDRACHTVERKEER) -> dict[str, Operation]:
    """The operations of a service, keyed by operationId."""
    document = load_openapi(service)
    found: dict[str, Operation] = {}
    for path, item in document["paths"].items():
        for method in _METHODS:
            spec = item.get(method)
            if spec is None:
                continue
            parameters = [
                _resolve(document, parameter)
                for parameter in spec.get("parameters", [])
            ]
            query = [p for p in parameters if p["in"] == "query"]
            body = spec.get("requestBody")
            responses = {
                status: schema
                for status, response in spec["responses"].items()
                if (schema := _content_schema(document, response)) is not None
            }
            found[spec["operationId"]] = Operation(
                service=service,
                operation_id=spec["operationId"],
                method=method.upper(),
                path=path,
                caller=spec.get("x-grip-caller"),
                data_classes=tuple(spec.get("x-grip-data-class", ())),
                on_request=bool(spec.get("x-grip-on-request", False)),
                request_schema=_content_schema(document, body) if body else None,
                response_schemas=responses,
                query_parameters=tuple(p["name"] for p in query),
                required_query_parameters=tuple(
                    p["name"] for p in query if p.get("required")
                ),
                path_parameters=tuple(
                    p["name"] for p in parameters if p["in"] == "path"
                ),
            )
    return found


def operation(operation_id: str, service: str = SERVICE_OPDRACHTVERKEER) -> Operation:
    try:
        return operations(service)[operation_id]
    except KeyError:
        raise ContractError(
            f"The contract of {service} has no operation {operation_id!r}"
        ) from None


def example_files(kind: str) -> list[Path]:
    """The contract's example files; ``kind`` is ``valid`` or ``invalid``."""
    return sorted((CONTRACT_DIR / "examples" / kind).glob("*.json"))


def schema_of_example(path: Path) -> str:
    """Examples are named ``<schema>[.<variant>].json``."""
    return path.name.split(".")[0]
