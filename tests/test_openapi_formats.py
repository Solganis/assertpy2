"""The formats `conforms_to_openapi` checks, each held to the document that defines it.

jsonschema checks `date-time` only beside a package this library does not install, and knows nothing of
OpenAPI's `int32` and `int64`, so ``"yesterday"`` passed for a moment and ``2**40`` for an `int32`.  The
moments here are the examples and the grammar of RFC 3339, and the bounds are the signed ranges.
"""

from __future__ import annotations

from typing import Any

import pytest

from assertpy2 import AssertionFailure, assert_that

jsonschema = pytest.importorskip("jsonschema", reason="jsonschema not installed")


def _spec(version: str, schema: dict[str, Any]) -> dict[str, Any]:
    wrapped = {"type": "object", "properties": {"v": schema}}
    if version == "2.0":
        return {"swagger": "2.0", "paths": {"/orders": {"get": {"responses": {"200": {"schema": wrapped}}}}}}
    return {
        "openapi": version,
        "paths": {"/orders": {"get": {"responses": {"200": {"content": {"application/json": {"schema": wrapped}}}}}}},
    }


def _conforms(value: object, schema: dict[str, Any], version: str = "3.0.3") -> bool:
    try:
        assert_that({"v": value}).conforms_to_openapi(_spec(version, schema), "/orders", "get")
    except AssertionFailure:
        return False
    return True


_MOMENT = {"type": "string", "format": "date-time"}


class TestADateTimeIsWrittenAsRfc3339WritesIt:
    @pytest.mark.parametrize(
        "moment",
        [
            "1985-04-12T23:20:50.52Z",
            "1996-12-19T16:39:57-08:00",
            "1990-12-31T23:59:60Z",
            "1990-12-31T15:59:60-08:00",
            "1937-01-01T12:00:27.87+00:20",
            "1985-04-12t23:20:50z",
            "2026-02-28T00:00:00+23:59",
            "2024-02-29T10:00:00.123456789012Z",
            "2000-02-29T00:00:00Z",
            "0000-02-29T00:00:00Z",
        ],
    )
    def test_a_moment_the_rfc_writes_passes(self, moment):
        assert_that(_conforms(moment, _MOMENT)).is_true()

    @pytest.mark.parametrize(
        "text",
        [
            "yesterday",
            "2026-13-45T99:99",
            "2026-02-30T10:00:00Z",
            "2026-02-29T10:00:00Z",
            "1900-02-29T10:00:00Z",
            "2026-13-01T10:00:00Z",
            "2026-00-10T10:00:00Z",
            "2026-01-00T10:00:00Z",
            "2026-04-31T10:00:00Z",
            "2026-01-01 10:00:00Z",
            "2026-01-01T10:00:00",
            "2026-01-01T24:00:00Z",
            "2026-01-01T10:60:00Z",
            "2026-01-01T10:00:61Z",
            "2026-01-01T10:00:00+24:00",
            "2026-01-01T10:00:00+10:60",
            "2026-01-01T10:00:00Z ",
            "2026-01-01T10:00:00.Z",
            "2026-01-01T10:00Z",
            "٢٠٢٦-01-01T10:00:00Z",
            "",
        ],
    )
    def test_a_text_that_is_none_fails(self, text):
        assert_that(_conforms(text, _MOMENT)).is_false()

    @pytest.mark.parametrize(
        "moment",
        [
            "1990-12-31T23:59:60Z",
            "1990-12-31T23:59:60.5z",
            "1990-12-31T15:59:60-08:00",
            "2026-07-01T08:59:60+09:00",
            "2026-06-30T23:59:60+00:00",
            "2026-06-30T23:59:60-00:00",
            "2026-06-30T00:00:60-23:59",
            "2026-07-01T23:58:60+23:59",
            "2026-02-28T23:59:60Z",
            "2024-02-29T23:59:60Z",
        ],
    )
    def test_a_second_of_sixty_passes_in_the_last_minute_of_a_month_in_utc(self, moment):
        assert_that(_conforms(moment, _MOMENT)).is_true()

    @pytest.mark.parametrize(
        "text",
        [
            "2026-01-01T10:00:60Z",
            "2026-06-29T23:59:60Z",
            "2026-06-30T23:58:60Z",
            "2026-06-30T23:59:60+01:00",
            "2026-06-30T23:59:60-00:01",
            "2026-06-30T15:59:60+08:00",
            "2026-07-02T08:59:60+09:00",
            "2026-07-01T08:59:60-09:00",
            "2026-06-30T08:59:60+09:00",
            "2024-02-28T23:59:60Z",
            "2026-06-31T23:59:60Z",
            "2026-06-30T23:59:61Z",
        ],
    )
    def test_a_second_of_sixty_fails_anywhere_else(self, text):
        assert_that(_conforms(text, _MOMENT)).is_false()

    @pytest.mark.parametrize("version", ["2.0", "3.0.3", "3.1.0", "3.2.0"])
    def test_in_every_dialect_the_assertion_reads(self, version):
        assert_that(_conforms("yesterday", _MOMENT, version)).is_false()
        assert_that(_conforms("1985-04-12T23:20:50.52Z", _MOMENT, version)).is_true()

    def test_a_text_of_a_class_of_its_own_is_a_text(self):
        named = type("Named", (str,), {})
        assert_that(_conforms(named("yesterday"), _MOMENT)).is_false()
        assert_that(_conforms(named("1985-04-12T23:20:50.52Z"), _MOMENT)).is_true()

    def test_what_is_no_text_is_the_type_keywords_to_judge(self):
        assert_that(_conforms(5, {"format": "date-time"})).is_true()
        assert_that(_conforms(None, {"format": "date-time"})).is_true()
        assert_that(_conforms(5, _MOMENT)).is_false()

    def test_a_check_jsonschema_brings_of_its_own_does_not_take_its_place(self, monkeypatch):
        """Beside the package that gives jsonschema a `date-time` check, a text still gets the verdict it gets here."""
        asked = []

        def theirs(value: object) -> bool:
            asked.append(value)
            return True

        monkeypatch.setitem(jsonschema.FormatChecker.checkers, "date-time", (theirs, ()))
        assert_that(_conforms("yesterday", _MOMENT)).is_false()
        assert_that(_conforms("0000-02-29T23:59:60Z", _MOMENT)).is_true()
        assert_that(asked).is_empty()


class TestAnIntegerFormatIsItsSignedRange:
    @pytest.mark.parametrize(
        ("bits", "value", "fits"),
        [
            (32, 2**31 - 1, True),
            (32, 2**31, False),
            (32, -(2**31), True),
            (32, -(2**31) - 1, False),
            (32, 2**40, False),
            (32, 0, True),
            (64, 2**63 - 1, True),
            (64, 2**63, False),
            (64, -(2**63), True),
            (64, -(2**63) - 1, False),
            (64, 2**70, False),
            (64, 2**40, True),
        ],
    )
    def test_a_whole_number_is_held_to_the_range(self, bits, value, fits):
        schema = {"type": "integer", "format": f"int{bits}"}
        assert_that(_conforms(value, schema)).is_equal_to(fits)
        assert_that(_conforms(value, schema, "3.1.0")).is_equal_to(fits)

    def test_a_float_that_holds_a_whole_number_is_one(self):
        assert_that(_conforms(2.0**31, {"type": "number", "format": "int32"})).is_false()
        assert_that(_conforms(5.0, {"type": "number", "format": "int32"})).is_true()
        assert_that(_conforms(5.5, {"type": "number", "format": "int32"})).is_true()

    def test_a_whole_number_of_a_class_of_its_own_is_one(self):
        counted = type("Counted", (int,), {})
        measured = type("Measured", (float,), {})
        assert_that(_conforms(counted(2**40), {"format": "int32"})).is_false()
        assert_that(_conforms(counted(7), {"format": "int32"})).is_true()
        assert_that(_conforms(measured(2.0**40), {"format": "int32"})).is_false()

    def test_a_number_that_answers_its_own_comparisons_is_read_by_what_it_holds(self):
        agreeing = type("Agreeing", (int,), {"__le__": lambda self, other: True, "__ge__": lambda self, other: True})
        refusing = type("Refusing", (int,), {"__le__": lambda self, other: False, "__ge__": lambda self, other: False})
        rounded = type("Rounded", (float,), {"is_integer": lambda self: False, "__le__": lambda self, other: True})
        assert_that(_conforms(agreeing(2**40), {"format": "int32"})).is_false()
        assert_that(_conforms(refusing(7), {"format": "int32"})).is_true()
        assert_that(_conforms(rounded(2.0**40), {"format": "int32"})).is_false()

    def test_what_is_no_number_is_the_type_keywords_to_judge(self):
        assert_that(_conforms("5", {"format": "int32"})).is_true()
        assert_that(_conforms("5", {"type": "integer", "format": "int32"})).is_false()

    def test_the_failure_names_the_place_and_the_format(self):
        outcome = (
            assert_that({"v": 2**40})
            .check()
            .conforms_to_openapi(_spec("3.0.3", {"type": "integer", "format": "int32"}), "/orders", "get")
        )
        assert_that(outcome.passed).is_false()
        entries = outcome.diff.entries
        assert_that([(entry.path, entry.actual) for entry in entries]).is_equal_to([("$.v", 2**40)])
        assert_that(entries[0].expected).contains("int32")


class TestWhatJsonschemaCheckedAlreadyIsCheckedStill:
    @pytest.mark.parametrize(
        ("form", "good", "bad"),
        [
            ("date", "2026-02-28", "2026-13-45"),
            ("email", "a@b.example", "not-an-email"),
            ("ipv4", "10.0.0.1", "10.0.0.256"),
            ("uuid", "123e4567-e89b-12d3-a456-426614174000", "not-a-uuid"),
        ],
    )
    def test_each_keeps_its_check(self, form, good, bad):
        schema = {"type": "string", "format": form}
        assert_that(_conforms(good, schema, "3.1.0")).is_true()
        assert_that(_conforms(bad, schema, "3.1.0")).is_false()
