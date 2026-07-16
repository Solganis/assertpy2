import pytest

attrs = pytest.importorskip("attrs", reason="attrs not installed")

from assertpy2 import assert_that, match
from assertpy2.errors import AssertionFailure


@attrs.define
class Point:
    x: int
    y: int


@attrs.define
class Line:
    start: Point
    end: Point


@attrs.define
class Named:
    x: int
    y: int
    label: str


class TestStructuralDiff:
    def test_nested_attrs_reports_field_path(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Line(Point(1, 2), Point(3, 4))).is_equal_to(Line(Point(1, 2), Point(9, 4)))
        diff = exc_info.value.diff
        assert_that(diff.kind).is_equal_to("attrs")
        assert_that([entry.path for entry in diff.entries]).contains(".end.x")

    def test_equal_attrs_pass(self):
        assert_that(Line(Point(1, 2), Point(3, 4))).is_equal_to(Line(Point(1, 2), Point(3, 4)))

    def test_top_level_field_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Point(1, 2)).is_equal_to(Point(1, 99))
        assert_that([entry.path for entry in exc_info.value.diff.entries]).contains(".y")

    def test_extra_and_missing_fields(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Named(1, 2, "a")).is_equal_to(Point(1, 2))
        paths = [entry.path for entry in exc_info.value.diff.entries]
        assert_that(paths).contains(".label")  # present in actual, absent in expected

    def test_ignore_and_tolerance_still_work(self):
        assert_that(Named(1, 2, "a")).is_equal_to(Named(1, 2, "b"), ignore="label")


class TestMatchesStructure:
    def test_attrs_with_matchers(self):
        assert_that(Point(1, 2)).matches_structure({"x": match.between(0, 10), "y": 2})

    def test_nested_attrs_structure(self):
        assert_that(Line(Point(1, 2), Point(3, 4))).matches_structure({"end": {"x": 3}})

    def test_attrs_mismatch_reports_field(self):
        with pytest.raises(AssertionError, match="x"):
            assert_that(Point(1, 2)).matches_structure({"x": 99})

    def test_non_mapping_value_rejected(self):
        with pytest.raises(TypeError, match="dict, a pydantic-style model, or an attrs instance"):
            assert_that([1, 2]).matches_structure({"x": 1})
