import typing

import pytest

pytest.importorskip("jsonschema", reason="jsonschema not installed")

from assertpy2 import assert_that

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

    def test_a_method_that_is_not_a_string_is_named_rather_than_crashing(self):
        """It used to answer with `AttributeError: 'int' object has no attribute 'lower'`."""
        with pytest.raises(TypeError, match="given method arg must be a string"):
            assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", 42)  # ty: ignore[invalid-argument-type]  # the shape under test

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


SPEC_20 = {
    "swagger": "2.0",
    "info": {"title": "Orders", "version": "1.0"},
    "paths": {
        "/orders/{id}": {
            "get": {
                "produces": ["application/json"],
                "responses": {
                    "200": {"schema": {"$ref": "#/definitions/Order"}},
                    "204": {"description": "no content, no schema"},
                },
            }
        }
    },
    "definitions": {
        "Order": {
            "type": "object",
            "required": ["id", "status"],
            "properties": {
                "id": {"type": "integer"},
                "status": {"type": "string", "enum": ["placed", "approved"]},
                "note": {"type": "string", "x-nullable": True},
            },
        }
    },
}


class TestSwagger20:
    PATH, METHOD = "/orders/{id}", "get"

    def test_conformant_body_with_definitions_ref_passes_and_chains(self):
        result = assert_that({"id": 1, "status": "placed"}).conforms_to_openapi(SPEC_20, self.PATH, self.METHOD)
        assert_that(result).is_not_none()

    def test_x_nullable_null_is_conformant(self):
        assert_that({"id": 1, "status": "placed", "note": None}).conforms_to_openapi(SPEC_20, self.PATH, self.METHOD)

    def test_x_nullable_wrong_type_reports_path(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"id": 1, "status": "placed", "note": 5}).conforms_to_openapi(SPEC_20, self.PATH, self.METHOD)
        assert_that(_entries(exc_info.value)).contains_key("$.note")

    def test_wrong_type_reports_path(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"id": "x", "status": "placed"}).conforms_to_openapi(SPEC_20, self.PATH, self.METHOD)
        assert_that(_entries(exc_info.value)).contains_key("$.id")

    def test_bad_enum_reports_path(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"id": 1, "status": "unknown"}).conforms_to_openapi(SPEC_20, self.PATH, self.METHOD)
        assert_that(_entries(exc_info.value)).contains_key("$.status")

    def test_response_without_schema_raises(self):
        # the method is echoed upper case, as the spec spells it, not as the argument was written
        with pytest.raises(ValueError, match=r"of <GET /orders/\{id\}> declares no schema"):
            assert_that({"x": 1}).conforms_to_openapi(SPEC_20, self.PATH, self.METHOD, status=204)

    def test_content_type_outside_produces_raises(self):
        # 2.0 has no content-type layer, so the check falls to the operation's `produces` list
        with pytest.raises(ValueError, match="no <application/xml> schema"):
            assert_that({"id": 1, "status": "placed"}).conforms_to_openapi(
                SPEC_20, self.PATH, self.METHOD, content_type="application/xml"
            )

    def test_content_type_inside_produces_passes(self):
        assert_that({"id": 1, "status": "placed"}).conforms_to_openapi(
            SPEC_20, self.PATH, self.METHOD, content_type="application/json"
        )

    def test_global_produces_is_honoured(self):
        spec = {
            "swagger": "2.0",
            "produces": ["application/json"],
            "paths": {"/x": {"get": {"responses": {"200": {"schema": {"type": "object"}}}}}},
        }
        with pytest.raises(ValueError, match="no <application/xml> schema"):
            assert_that({}).conforms_to_openapi(spec, "/x", "get", content_type="application/xml")

    def test_absent_produces_skips_the_content_type_check(self):
        spec = {"swagger": "2.0", "paths": {"/x": {"get": {"responses": {"200": {"schema": {"type": "object"}}}}}}}
        assert_that({}).conforms_to_openapi(spec, "/x", "get", content_type="application/xml")


class TestStatusAutoSelection:
    """With no ``status=`` the first declared response among 200, 201 and ``default`` is used, in that
    order.  Every test above either names a status or declares exactly one, so neither the order nor
    the membership of that list was pinned."""

    @staticmethod
    def _spec(*status_codes):
        responses = {
            code: {"content": {"application/json": {"schema": {"type": "object", "required": [code]}}}}
            for code in status_codes
        }
        return {"openapi": "3.0.3", "paths": {"/x": {"get": {"responses": responses}}}}

    def test_two_hundred_wins_over_two_hundred_and_one(self):
        # the schema of whichever response is picked demands a property named after its status code,
        # so the failure names the one that was chosen
        with pytest.raises(AssertionError, match="200"):
            assert_that({}).conforms_to_openapi(self._spec("201", "200"), "/x", "get")

    def test_two_hundred_and_one_wins_over_default(self):
        with pytest.raises(AssertionError, match="201"):
            assert_that({}).conforms_to_openapi(self._spec("default", "201"), "/x", "get")

    def test_default_is_used_when_nothing_else_is_declared(self):
        with pytest.raises(AssertionError, match="default"):
            assert_that({}).conforms_to_openapi(self._spec("default"), "/x", "get")

    def test_an_unpickable_set_names_what_was_declared(self):
        with pytest.raises(ValueError, match=r"Specify status: <GET /x> declares responses \['418'\]"):
            assert_that({}).conforms_to_openapi(self._spec("418"), "/x", "get")


class TestStructuralErrorsNameTheMethodInUpperCase:
    """The operation is echoed as the caller would find it in the spec, which is upper case: the
    argument itself is lower case, so a message built from it unchanged reads as a different key."""

    def test_an_unknown_operation_upper_cases_the_method(self):
        with pytest.raises(ValueError, match=r"<POST /orders/\{id\}>"):
            assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", "post")

    def test_an_unknown_status_upper_cases_the_method(self):
        with pytest.raises(ValueError, match=r"<GET /orders/\{id\}>"):
            assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", "get", status=404)

    def test_a_missing_content_type_upper_cases_the_method(self):
        spec = {
            "openapi": "3.0.3",
            "paths": {"/x": {"get": {"responses": {"200": {"content": {"text/plain": {"schema": {}}}}}}}},
        }
        with pytest.raises(ValueError, match=r"<GET /x>"):
            assert_that(CONFORMANT).conforms_to_openapi(spec, "/x", "get")

    def test_a_response_without_a_schema_upper_cases_the_method(self):
        spec = {"openapi": "3.0.3", "paths": {"/x": {"get": {"responses": {"200": {}}}}}}
        with pytest.raises(ValueError, match=r"<GET /x>"):
            assert_that(CONFORMANT).conforms_to_openapi(spec, "/x", "get")


class TestNullableInsideArrays:
    """``nullable: true`` is rewritten to a null-union before jsonschema sees it, and the rewrite has
    to reach schemas nested inside a list.  Nothing put a nullable schema inside one."""

    _SPEC: typing.ClassVar = {
        "openapi": "3.0.3",
        "paths": {
            "/x": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "who": {
                                                "oneOf": [
                                                    {"type": "string", "nullable": True},
                                                    {"type": "integer"},
                                                ]
                                            }
                                        },
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
    }

    def test_a_null_inside_a_oneof_branch_is_conformant(self):
        assert_that({"who": None}).conforms_to_openapi(self._SPEC, "/x", "get")

    def test_a_non_null_value_still_has_to_match_a_branch(self):
        with pytest.raises(AssertionError):
            assert_that({"who": 1.5}).conforms_to_openapi(self._SPEC, "/x", "get")


class TestSwagger20NullableInsideArrays:
    """Swagger 2.0 spells nullability ``x-nullable``, and the rewrite carries that keyword down.
    Losing it inside a list recursion falls back to the 3.0 spelling, which a 2.0 spec never uses."""

    _SPEC: typing.ClassVar = {
        "swagger": "2.0",
        "paths": {
            "/x": {
                "get": {
                    "produces": ["application/json"],
                    "responses": {
                        "200": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "who": {"allOf": [{"type": "string", "x-nullable": True}]},
                                },
                            }
                        }
                    },
                }
            }
        },
    }

    def test_a_null_inside_an_allof_branch_is_conformant(self):
        assert_that({"who": None}).conforms_to_openapi(self._SPEC, "/x", "get")

    def test_a_wrong_type_inside_the_branch_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"who": 1}).conforms_to_openapi(self._SPEC, "/x", "get")
