from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._mixin_base import _MixinBase

if TYPE_CHECKING:
    from ._compat import Self

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
            Usage::

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
        return self.builder([m.value for m in matches], self.description, self.kind)

    def has_json_path(self, path: str) -> Self:
        """Assert that the given JSON path exists in val.

        Args:
            path: JSONPath expression.

        Examples:
            Usage::

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
            Usage::

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
            Usage::

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
            Usage::

                assert_that(data).matches_json_schema_from_file("schemas/order.json")

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does not conform to the schema
        """
        schema = json.loads(Path(path).read_text(encoding="utf-8"))
        return self.matches_json_schema(schema)
