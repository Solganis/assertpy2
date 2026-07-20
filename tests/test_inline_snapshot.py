import pytest

import assertpy2._inline as _inline
import assertpy2.snapshot as _snap
from assertpy2 import assert_that
from assertpy2._inline import is_literalable


class TestCompare:
    def test_dict_pass_and_chains(self):
        assert_that({"id": 1, "name": "Alice"}).matches_inline({"id": 1, "name": "Alice"}).is_type_of(dict)

    def test_scalar_pass(self):
        assert_that(42).matches_inline(42)

    def test_list_pass(self):
        assert_that([1, 2, 3]).matches_inline([1, 2, 3])

    def test_drift_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"id": 1}).matches_inline({"id": 2})


class TestSelective:
    def test_ignore(self):
        assert_that({"id": 99, "name": "Alice"}).matches_inline({"id": 0, "name": "Alice"}, ignore="id")

    def test_tolerance(self):
        assert_that({"x": 1.001}).matches_inline({"x": 1.0}, tolerance=0.01)

    def test_placeholders_pass(self):
        assert_that({"id": 123, "name": "Alice"}).matches_inline(
            {"id": 0, "name": "Alice"}, placeholders={"id": lambda value: isinstance(value, int)}
        )

    def test_placeholder_matcher_checked(self):
        with pytest.raises(AssertionError):
            assert_that({"id": "nope", "name": "Alice"}).matches_inline(
                {"id": 0, "name": "Alice"}, placeholders={"id": lambda value: isinstance(value, int)}
            )

    def test_placeholder_invalid_value(self):
        with pytest.raises(TypeError, match="Matcher instances or callables"):
            assert_that({"id": 1}).matches_inline({"id": 1}, placeholders={"id": 42})

    def test_placeholder_requires_dict_like(self):
        with pytest.raises((TypeError, AssertionError)):
            assert_that([1, 2]).matches_inline([1, 2], placeholders={"id": lambda value: True})


class TestEmpty:
    def test_empty_without_update_errors(self, monkeypatch):
        monkeypatch.setattr(_snap, "_CI_MODE", False)
        with pytest.raises(AssertionError, match="run --assertpy2-snapshot-update"):
            assert_that(1).matches_inline()

    def test_empty_in_ci_forbidden(self, monkeypatch):
        monkeypatch.setattr(_snap, "_CI_MODE", True)
        with pytest.raises(AssertionError, match="CI mode forbids"):
            assert_that(1).matches_inline()


class TestLiteralable:
    def test_non_finite_floats_rejected(self):
        # nan/inf render as bare names (invalid source), so they must not be recordable as literals
        assert_that(is_literalable(float("nan"))).is_false()
        assert_that(is_literalable(float("inf"))).is_false()
        assert_that(is_literalable(float("-inf"))).is_false()
        assert_that(is_literalable({"r": float("nan")})).is_false()

    def test_finite_values_literalable(self):
        assert_that(is_literalable({"a": [1, 2.5], "b": "x", "c": True, "d": None})).is_true()

    def test_apply_records_preserves_crlf(self, tmp_path):
        source = tmp_path / "c.py"
        source.write_bytes(b"a = matches_inline()\r\nb = 1\r\n")
        normalized = "a = matches_inline()\nb = 1\n"
        insert_at = normalized.index("matches_inline(") + len("matches_inline(")
        _inline._RECORDS.clear()
        _inline._RECORDS.append((str(source), insert_at, insert_at, "42"))
        _inline.apply_inline_records()
        assert_that(source.read_bytes()).is_equal_to(b"a = matches_inline(42)\r\nb = 1\r\n")


def test_inline_mismatch_names_its_kind_and_the_update_flag():
    # the file-backed branch says which snapshot it measured against; the inline one must not stay
    # silent, or the reader sees the same failure worded two different ways
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"id": 7, "status": "paid"}).matches_inline({"id": 7, "status": "pending"})
    message = str(exc_info.value)
    assert_that(message).contains("Inline snapshot")
    assert_that(message).contains("--assertpy2-snapshot-update")


def test_inline_mismatch_keeps_the_diff():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": {"b": 1}}).matches_inline({"a": {"b": 2}})
    assert_that(exc_info.value.diff.entries[0].path).is_equal_to("a.b")
