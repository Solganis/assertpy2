import pytest

from assertpy2 import assert_that, match
from assertpy2._engine._introspection import is_attrs_instance
from assertpy2.errors import AssertionFailure

attrs = pytest.importorskip("attrs", reason="attrs not installed")
import attr  # noqa: E402  # low-level attrs API, imported only after importorskip confirms attrs is installed


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


@attrs.define(frozen=True)
class Frozen:
    x: int
    y: int


@attrs.define
class Converted:
    n: int = attrs.field(converter=int)


@attrs.define
class Private:
    _secret: int
    name: str


@attr.s
class OldStyle:
    x = attr.ib()
    y = attr.ib()


@attrs.define
class Nested:
    inner: Frozen
    tag: str


class TestVariants:
    def test_attrs_class_is_not_an_instance(self):
        assert_that(is_attrs_instance(Frozen)).is_false()
        assert_that(is_attrs_instance(Frozen(1, 2))).is_true()

    def test_comparing_classes_does_not_crash(self):
        assert_that(Frozen).is_equal_to(Frozen)  # class, not instance: equal by identity, no field read

    def test_frozen_field_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Frozen(1, 2)).is_equal_to(Frozen(1, 9))
        assert_that([entry.path for entry in exc_info.value.diff.entries]).contains(".y")

    def test_converter_value_compared(self):
        assert_that(Converted("5")).is_equal_to(Converted(5))
        assert_that(Converted("5")).matches_structure({"n": 5})

    def test_private_field_name_kept(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Private(1, "a")).is_equal_to(Private(9, "a"))
        assert_that([entry.path for entry in exc_info.value.diff.entries]).contains("._secret")
        assert_that(Private(1, "a")).matches_structure({"_secret": 1})

    def test_old_style_attr_s(self):
        assert_that(OldStyle(1, 2)).is_equal_to(OldStyle(1, 2))
        assert_that(OldStyle(1, 2)).matches_structure({"x": 1})

    def test_nested_ignore_reaches_into_attrs(self):
        assert_that(Nested(Frozen(1, 2), "a")).is_equal_to(Nested(Frozen(1, 9), "a"), ignore=("inner", "y"))

    def test_nested_include_reaches_into_attrs(self):
        assert_that(Nested(Frozen(1, 2), "a")).is_equal_to(Nested(Frozen(1, 9), "b"), include=("inner", "x"))

    def test_nested_ignore_does_not_over_ignore(self):
        with pytest.raises(AssertionError):
            assert_that(Nested(Frozen(1, 2), "a")).is_equal_to(Nested(Frozen(1, 9), "a"), ignore="tag")


class TestFieldWalk:
    def test_all_fields_satisfy_walks_into_attrs(self):
        assert_that(Line(Point(1, 2), Point(3, 4))).all_fields_satisfy(lambda leaf: isinstance(leaf, int))

    def test_all_fields_satisfy_flags_bad_leaf(self):
        with pytest.raises(AssertionError):
            assert_that(Named(1, 2, "a")).all_fields_satisfy(lambda leaf: isinstance(leaf, int))

    def test_has_no_none_fields_on_attrs(self):
        @attrs.define
        class Maybe:
            a: int
            b: object

        assert_that(Maybe(1, 2)).has_no_none_fields()
        with pytest.raises(AssertionError):
            assert_that(Maybe(1, None)).has_no_none_fields()


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
