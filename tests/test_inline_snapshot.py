import pytest

import assertpy2.snapshot as _snap
from assertpy2 import assert_that


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
