from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._engine._mixin_base import _MixinBase
from .errors import DiffEntry, DiffResult

if TYPE_CHECKING:
    from ._engine._compat import Self

__tracebackhide__ = True


def _ensure_jsonpath_ng():
    try:
        import jsonpath_ng.ext  # optional dependency
    except ImportError:
        raise ImportError(
            "jsonpath-ng is required for JSON path assertions. Install it with: pip install assertpy2[json]"
        ) from None
    return jsonpath_ng.ext


def _ensure_jsonschema():
    try:
        import jsonschema  # optional dependency
    except ImportError:
        raise ImportError(
            "jsonschema is required for JSON schema assertions. Install it with: pip install assertpy2[json]"
        ) from None
    return jsonschema


def _openapi_nullable_to_null(node: Any) -> Any:
    """Rewrite OpenAPI 3.0 ``nullable: true`` into standard JSON Schema (jsonschema ignores it).

    For the common scalar-typed field, ``"null"`` is added to ``type`` (and to ``enum`` if present),
    which keeps per-keyword error paths precise - a bad ``format``/``type`` on a nullable field still
    reports ``format``/``type``, not a vague union. Only a nullable schema with no scalar ``type``
    (nullable beside ``$ref``/``oneOf``) falls back to an ``anyOf`` null union.
    """
    if isinstance(node, dict):
        rewritten = {key: _openapi_nullable_to_null(value) for key, value in node.items()}
        if not rewritten.pop("nullable", False):
            return rewritten
        node_type = rewritten.get("type")
        if isinstance(node_type, str):
            rewritten["type"] = [node_type, "null"]
            enum = rewritten.get("enum")
            if isinstance(enum, list) and None not in enum:
                rewritten["enum"] = [*enum, None]
            return rewritten
        return {"anyOf": [rewritten, {"type": "null"}]}
    if isinstance(node, list):
        return [_openapi_nullable_to_null(item) for item in node]
    return node


def _openapi_resolve(spec: dict[str, Any], path: str, method: str, status: str | int | None, content_type: str):
    """Resolve an operation's response-body schema to a JSON Pointer into the spec document.

    Returns ``(status_key, pointer)``. Raises ``ValueError`` for any structural miss (unknown path,
    method, status, or content type) - those are test-authoring mistakes, not contract violations.
    """
    method_key = method.lower()
    try:
        responses = spec["paths"][path][method_key]["responses"]
    except (KeyError, TypeError):
        raise ValueError(f"OpenAPI spec has no operation <{method.upper()} {path}>.") from None
    if status is not None:
        status_key = str(status)
        if status_key not in responses:
            raise ValueError(f"Operation <{method.upper()} {path}> declares no response <{status_key}>.")
    else:
        status_key = next((code for code in ("200", "201", "default") if code in responses), "")
        if not status_key:
            raise ValueError(f"Specify status: <{method.upper()} {path}> declares responses {sorted(responses)}.")
    content = responses[status_key].get("content", {})
    if content_type not in content or "schema" not in content[content_type]:
        raise ValueError(f"Response <{status_key}> of <{method.upper()} {path}> declares no <{content_type}> schema.")
    segments = ["paths", path, method_key, "responses", status_key, "content", content_type, "schema"]
    pointer = "#/" + "/".join(segment.replace("~", "~0").replace("/", "~1") for segment in segments)
    return status_key, pointer


def _openapi_expected(error: Any) -> str:
    """Render a jsonschema validation error's constraint as a short 'expected' description."""
    validator, value = error.validator, error.validator_value
    if validator == "required":
        return "all required properties present"
    if validator == "type":
        return f"type {value}"
    if validator == "enum":
        return f"one of {value}"
    if validator == "oneOf":
        return "exactly one of the declared schemas"
    if validator == "anyOf":
        return "one of the declared schemas"
    if validator == "format":
        return f"{value} format"
    return error.message


class JsonMixin(_MixinBase):
    """JSON path navigation and schema validation mixin."""

    def at_json_path(self, path: str) -> Self:
        """Navigate to a JSON path and return a new builder with the matched value.

        Uses JSONPath syntax (e.g. ``$.users[0].name``). If multiple matches are found,
        the value is a list of all matches. If exactly one match is found, the value is
        unwrapped from the list.

        Args:
            path: JSONPath expression.

        Examples:
            Usage:

                data = {"users": [{"name": "Alice"}, {"name": "Bob"}]}
                assert_that(data).at_json_path("$.users[0].name").is_equal_to("Alice")
                assert_that(data).at_json_path("$.users[*].name").is_equal_to(["Alice", "Bob"])

        Returns:
            AssertionBuilder: a new instance with the extracted value

        Raises:
            ValueError: if no match is found at the given path
        """
        jsonpath_ng_ext = _ensure_jsonpath_ng()
        expr = jsonpath_ng_ext.parse(path)
        matches = expr.find(self.val)
        if not matches:
            raise ValueError(f"Expected JSON path <{path}> to exist, but it did not.")
        if len(matches) == 1:
            return self.builder(matches[0].value, self.description, self.kind)
        return self.builder([match.value for match in matches], self.description, self.kind)

    def has_json_path(self, path: str) -> Self:
        """Assert that the given JSON path exists in val.

        Args:
            path: JSONPath expression.

        Examples:
            Usage:

                data = {"meta": {"total": 5}}
                assert_that(data).has_json_path("$.meta.total")

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the path does not exist
        """
        jsonpath_ng_ext = _ensure_jsonpath_ng()
        expr = jsonpath_ng_ext.parse(path)
        matches = expr.find(self.val)
        if not matches:
            return self.error(f"Expected JSON path <{path}> to exist, but it did not.")
        return self

    def does_not_have_json_path(self, path: str) -> Self:
        """Assert that the given JSON path does not exist in val.

        Args:
            path: JSONPath expression.

        Examples:
            Usage:

                data = {"status": "ok"}
                assert_that(data).does_not_have_json_path("$.error")

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the path exists
        """
        jsonpath_ng_ext = _ensure_jsonpath_ng()
        expr = jsonpath_ng_ext.parse(path)
        matches = expr.find(self.val)
        if matches:
            return self.error(f"Expected JSON path <{path}> to not exist, but it did.")
        return self

    def matches_json_schema(self, schema: dict[str, Any]) -> Self:
        """Assert that val conforms to the given JSON Schema.

        Args:
            schema: a JSON Schema as a dict.

        Examples:
            Usage:

                schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
                assert_that({"name": "Alice"}).matches_json_schema(schema)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does not conform to the schema
        """
        jsonschema_mod = _ensure_jsonschema()
        try:
            jsonschema_mod.validate(self.val, schema)
        except jsonschema_mod.ValidationError as exc:
            return self.error(f"Expected val to match JSON schema, but validation failed: {exc.message}")
        return self

    def matches_json_schema_from_file(self, path: str | Path) -> Self:
        """Assert that val conforms to a JSON Schema loaded from a file.

        Args:
            path: path to a JSON file containing the schema.

        Examples:
            Usage:

                assert_that(data).matches_json_schema_from_file("schemas/order.json")

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does not conform to the schema
        """
        schema = json.loads(Path(path).read_text(encoding="utf-8"))
        return self.matches_json_schema(schema)

    def conforms_to_openapi(
        self,
        spec: dict[str, Any],
        path: str,
        method: str,
        *,
        status: str | int | None = None,
        content_type: str = "application/json",
    ) -> Self:
        """Assert that val conforms to an OpenAPI operation's response-body schema.

        val is validated against the schema declared for the ``application/json`` response of the
        ``method``/``path`` operation in ``spec``. This checks only the response body of that one
        operation - not request bodies, parameters, headers, or the spec as a whole.

        Both OpenAPI 3.0 (its ``nullable`` keyword is honoured) and 3.1 are supported. ``$ref``,
        ``oneOf``/``allOf``/``anyOf``, ``enum``, and ``format`` all validate with full JSON-Schema
        semantics, and every violation is reported with its JSON path.

        Args:
            spec: a parsed OpenAPI document (dict); loading YAML/JSON is the caller's job.
            path: the operation's path template, e.g. ``"/orders/{id}"``.
            method: the HTTP method, e.g. ``"get"`` (case-insensitive).
            status: response status to validate against; defaults to ``200``, then ``201``, then
                ``default``.
            content_type: response content type; defaults to ``"application/json"``.

        Examples:
            Usage:

                spec = {...}  # your parsed OpenAPI document
                assert_that(response.json()).conforms_to_openapi(spec, "/orders/{id}", "get")

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does not conform to the response schema
            ValueError: if the operation, status, or content type is not found in the spec
        """
        jsonschema_mod = _ensure_jsonschema()
        import referencing
        from referencing.jsonschema import DRAFT4, DRAFT202012

        is_openapi_31 = str(spec.get("openapi", "")).startswith("3.1")
        status_key, pointer = _openapi_resolve(spec, path, method, status, content_type)
        document = spec if is_openapi_31 else _openapi_nullable_to_null(spec)
        specification = DRAFT202012 if is_openapi_31 else DRAFT4
        validator_cls = jsonschema_mod.Draft202012Validator if is_openapi_31 else jsonschema_mod.Draft4Validator

        base = "urn:assertpy2-openapi"
        registry = referencing.Registry().with_resource(
            uri=base, resource=referencing.Resource(contents=document, specification=specification)
        )
        validator = validator_cls(
            {"$ref": base + pointer}, registry=registry, format_checker=jsonschema_mod.FormatChecker()
        )
        errors = sorted(validator.iter_errors(self.val), key=lambda error: (error.json_path, str(error.validator)))
        if not errors:
            return self
        entries = [
            DiffEntry(path=error.json_path, actual=error.instance, expected=_openapi_expected(error))
            for error in errors
        ]
        plural = "" if len(entries) == 1 else "s"
        return self.error(
            f"Expected the value to conform to the OpenAPI schema for <{method.upper()} {path}> response"
            f" <{status_key}>, but found {len(entries)} violation{plural}.",
            diff=DiffResult(kind="openapi", entries=entries),
        )
