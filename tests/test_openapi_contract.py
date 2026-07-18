import pytest

pytest.importorskip("jsonschema", reason="jsonschema not installed")

from assertpy2 import assert_that

# --- OpenAPI 3.0 operation exercising $ref, oneOf, enum, format, nullable, and a plain constraint ---
SPEC_30 = {
    "openapi": "3.0.3",
    "info": {"title": "Orders", "version": "1.0"},
    "paths": {
        "/orders/{id}": {
            "get": {
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Order"}}}},
                    "default": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                }
            }
        },
        "/orders": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"$ref": "#/components/schemas/Order"}}
                            }
                        }
                    }
                }
            }
        },
    },
    "components": {
        "schemas": {
            "Order": {
                "type": "object",
                "required": ["id", "status", "payment"],
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string", "minLength": 3},
                    "status": {"type": "string", "enum": ["placed", "approved", "delivered"]},
                    "customerEmail": {"type": "string", "format": "email", "nullable": True},
                    "priority": {"type": "string", "enum": ["low", "high"], "nullable": True},
                    "refund": {
                        "nullable": True,
                        "oneOf": [{"$ref": "#/components/schemas/Card"}, {"$ref": "#/components/schemas/Bank"}],
                    },
                    "payment": {
                        "oneOf": [{"$ref": "#/components/schemas/Card"}, {"$ref": "#/components/schemas/Bank"}]
                    },
                },
            },
            "Card": {
                "type": "object",
                "required": ["kind", "last4"],
                "properties": {"kind": {"type": "string", "enum": ["card"]}, "last4": {"type": "string"}},
            },
            "Bank": {
                "type": "object",
                "required": ["kind", "iban"],
                "properties": {"kind": {"type": "string", "enum": ["bank"]}, "iban": {"type": "string"}},
            },
            "Error": {"type": "object", "required": ["message"], "properties": {"message": {"type": "string"}}},
        }
    },
}

# 3.1 variant: nullable expressed the standard way, so no preprocessing is needed
SPEC_31 = {
    "openapi": "3.1.0",
    "info": {"title": "Orders", "version": "1.0"},
    "paths": {
        "/orders/{id}": {
            "get": {
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Order"}}}}
                }
            }
        }
    },
    "components": {
        "schemas": {
            "Order": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "integer"},
                    "customerEmail": {"type": ["string", "null"], "format": "email"},
                },
            }
        }
    },
}

CARD = {"kind": "card", "last4": "4242"}
CONFORMANT = {"id": 1, "name": "widget", "status": "approved", "customerEmail": "a@b.com", "payment": CARD}


class TestConformant:
    def test_conformant_body_passes_and_chains(self):
        assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", "get").is_type_of(dict)

    def test_nullable_field_null_is_conformant(self):
        assert_that({**CONFORMANT, "customerEmail": None}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")

    def test_nullable_enum_null_and_value_conformant(self):
        assert_that({**CONFORMANT, "priority": None}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")
        assert_that({**CONFORMANT, "priority": "low"}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")

    def test_nullable_oneof_null_and_value_conformant(self):
        assert_that({**CONFORMANT, "refund": None}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")
        assert_that({**CONFORMANT, "refund": CARD}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")

    def test_nullable_optional_field_absent(self):
        body = {"id": 1, "status": "placed", "payment": CARD}
        assert_that(body).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")

    def test_property_literally_named_nullable_is_validated(self):
        # a property whose NAME is "nullable" must not be mistaken for the OpenAPI nullable keyword
        schema = {
            "type": "object",
            "properties": {"nullable": {"type": "string"}, "name": {"type": "string"}},
            "required": ["nullable", "name"],
        }
        spec = {
            "openapi": "3.0.3",
            "paths": {"/c": {"get": {"responses": {"200": {"content": {"application/json": {"schema": schema}}}}}}},
        }
        assert_that({"nullable": "x", "name": "y"}).conforms_to_openapi(spec, "/c", "get")
        with pytest.raises(AssertionError):
            assert_that({"nullable": 123, "name": 456}).conforms_to_openapi(spec, "/c", "get")

    def test_nullable_false_does_not_allow_null(self):
        # nullable: false must drop the keyword without permitting null
        schema = {"type": "object", "properties": {"name": {"type": "string", "nullable": False}}, "required": ["name"]}
        spec = {
            "openapi": "3.0.3",
            "paths": {"/c": {"get": {"responses": {"200": {"content": {"application/json": {"schema": schema}}}}}}},
        }
        assert_that({"name": "x"}).conforms_to_openapi(spec, "/c", "get")
        with pytest.raises(AssertionError):
            assert_that({"name": None}).conforms_to_openapi(spec, "/c", "get")

    def test_yaml_integer_status_key_is_matched(self):
        # PyYAML parses an unquoted status code (200:) as an int; it must still resolve and match
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}
        spec = {
            "openapi": "3.0.3",
            "paths": {"/x": {"get": {"responses": {200: {"content": {"application/json": {"schema": schema}}}}}}},
        }
        assert_that({"id": 5}).conforms_to_openapi(spec, "/x", "get")
        assert_that({"id": 5}).conforms_to_openapi(spec, "/x", "get", status=200)
        with pytest.raises(AssertionError):
            assert_that({"id": "bad"}).conforms_to_openapi(spec, "/x", "get")

    def test_dangling_response_ref_raises(self):
        spec = {
            "openapi": "3.0.3",
            "paths": {"/y": {"get": {"responses": {"200": {"$ref": "#/components/responses/Nope"}}}}},
        }
        with pytest.raises(ValueError, match="unresolvable"):
            assert_that({"id": 5}).conforms_to_openapi(spec, "/y", "get")

    def test_external_response_ref_raises(self):
        spec = {"openapi": "3.0.3", "paths": {"/y": {"get": {"responses": {"200": {"$ref": "other.yaml#/x"}}}}}}
        with pytest.raises(ValueError, match="unresolvable"):
            assert_that({"id": 5}).conforms_to_openapi(spec, "/y", "get")

    def test_response_level_ref_is_resolved(self):
        # a Response Object given as a local $ref into components must resolve, not report "no schema"
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}
        spec = {
            "openapi": "3.0.3",
            "paths": {"/x": {"get": {"responses": {"200": {"$ref": "#/components/responses/Ok"}}}}},
            "components": {
                "responses": {"Ok": {"description": "ok", "content": {"application/json": {"schema": schema}}}}
            },
        }
        assert_that({"id": 5}).conforms_to_openapi(spec, "/x", "get")
        with pytest.raises(AssertionError):
            assert_that({"id": "bad"}).conforms_to_openapi(spec, "/x", "get")

    def test_array_response_conformant(self):
        assert_that([CONFORMANT, {**CONFORMANT, "id": 2}]).conforms_to_openapi(SPEC_30, "/orders", "get")

    def test_method_is_case_insensitive(self):
        assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", "GET")

    def test_explicit_status_str_and_int(self):
        assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", "get", status=200)
        assert_that({"message": "boom"}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get", status="default")

    def test_openapi_31_native_null(self):
        assert_that({"id": 1, "customerEmail": None}).conforms_to_openapi(SPEC_31, "/orders/{id}", "get")


def _entries(exc: AssertionError) -> dict[str, str]:
    """Map the structured diff carried by an OpenAPI failure to ``{path: expected}``."""
    return {entry.path: entry.expected for entry in exc.diff.entries}


class TestViolations:
    def _violation(self, body: dict) -> dict[str, str]:
        with pytest.raises(AssertionError) as exc_info:
            assert_that(body).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")
        return _entries(exc_info.value)

    def test_wrong_type_reports_path(self):
        assert_that(self._violation({**CONFORMANT, "id": "one"})).contains_key("$.id")

    def test_wrong_type_expected_text(self):
        assert_that(self._violation({**CONFORMANT, "id": "one"})["$.id"]).contains("type integer")

    def test_missing_required_field(self):
        assert_that(self._violation({"status": "placed", "payment": CARD})["$"]).contains("required properties")

    def test_bad_enum_value(self):
        assert_that(self._violation({**CONFORMANT, "status": "SHIPPED"})["$.status"]).contains("one of")

    def test_bad_format_on_nullable_field_stays_precise(self):
        assert_that(self._violation({**CONFORMANT, "customerEmail": "not-an-email"})["$.customerEmail"]).is_equal_to(
            "email format"
        )

    def test_bad_enum_on_nullable_field_stays_precise(self):
        assert_that(self._violation({**CONFORMANT, "priority": "urgent"})["$.priority"]).contains("one of")

    def test_oneof_matching_neither(self):
        assert_that(self._violation({**CONFORMANT, "payment": {"kind": "paypal"}})["$.payment"]).contains(
            "exactly one of"
        )

    def test_nullable_oneof_wrong_value_reports_anyof(self):
        assert_that(self._violation({**CONFORMANT, "refund": {"kind": "paypal"}})["$.refund"]).is_equal_to(
            "one of the declared schemas"
        )

    def test_plain_constraint_falls_back_to_message(self):
        assert_that(self._violation({**CONFORMANT, "name": "ab"})["$.name"]).contains("too short")

    def test_multiple_violations_counted(self):
        body = {"id": "x", "status": "SHIPPED", "payment": {"kind": "paypal"}}
        with pytest.raises(AssertionError, match="3 violations"):
            assert_that(body).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")

    def test_single_violation_is_singular(self):
        with pytest.raises(AssertionError, match="found 1 violation"):
            assert_that({**CONFORMANT, "id": "x"}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")


class TestStructuralErrors:
    def test_unknown_operation(self):
        with pytest.raises(ValueError, match="no operation <POST /orders/"):
            assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", "post")

    def test_unknown_path(self):
        with pytest.raises(ValueError, match="no operation"):
            assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/nope", "get")

    def test_unknown_status(self):
        with pytest.raises(ValueError, match="no response <404>"):
            assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", "get", status=404)

    def test_no_autopickable_status(self):
        spec = {"openapi": "3.0.3", "paths": {"/x": {"get": {"responses": {"418": {"content": {}}}}}}}
        with pytest.raises(ValueError, match="Specify status"):
            assert_that(CONFORMANT).conforms_to_openapi(spec, "/x", "get")

    def test_missing_content_type(self):
        spec = {
            "openapi": "3.0.3",
            "paths": {"/x": {"get": {"responses": {"200": {"content": {"text/plain": {"schema": {}}}}}}}},
        }
        with pytest.raises(ValueError, match="no <application/json> schema"):
            assert_that(CONFORMANT).conforms_to_openapi(spec, "/x", "get")

    def test_custom_content_type(self):
        spec = {
            "openapi": "3.0.3",
            "paths": {
                "/x": {
                    "get": {
                        "responses": {"200": {"content": {"application/vnd.api+json": {"schema": {"type": "object"}}}}}
                    }
                }
            },
        }
        assert_that({}).conforms_to_openapi(spec, "/x", "get", content_type="application/vnd.api+json")
