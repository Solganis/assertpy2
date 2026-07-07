import re
from collections import namedtuple
from dataclasses import dataclass

import pytest

from assertpy2 import AssertionFailure, assert_that

Pair = namedtuple("Pair", ["a", "b"])


@dataclass
class Point:
    x: float
    y: float


class FakeModel:
    def __init__(self, **data):
        self._data = data

    def model_dump(self):
        return dict(self._data)


class TestToleranceScalar:
    def test_within_tolerance_passes(self):
        assert_that(1.0).is_equal_to(1.0001, tolerance=0.001)

    def test_at_tolerance_boundary_passes(self):
        assert_that(1.0).is_equal_to(1.001, tolerance=0.001)

    def test_just_beyond_tolerance_fails(self):
        with pytest.raises(AssertionFailure):
            assert_that(1.0).is_equal_to(1.0011, tolerance=0.001)

    def test_far_beyond_tolerance_fails(self):
        with pytest.raises(AssertionFailure):
            assert_that(1.0).is_equal_to(5.0, tolerance=0.001)

    def test_int_leaf_within_tolerance(self):
        assert_that(100).is_equal_to(101, tolerance=2)

    def test_nan_never_within_tolerance(self):
        with pytest.raises(AssertionFailure):
            assert_that(float("nan")).is_equal_to(float("nan"), tolerance=0.001)

    def test_expected_nan_never_within_tolerance(self):
        with pytest.raises(AssertionFailure):
            assert_that(1.0).is_equal_to(float("nan"), tolerance=0.001)

    def test_bool_excluded_from_tolerance(self):
        with pytest.raises(AssertionFailure):
            assert_that(True).is_equal_to(False, tolerance=5)


class TestToleranceNested:
    def test_dict_all_within_tolerance(self):
        assert_that({"a": 1.0, "b": 2.0}).is_equal_to({"a": 1.0005, "b": 2.0}, tolerance=0.001)

    def test_dict_leaf_beyond_tolerance_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1.0}).is_equal_to({"a": 1.5}, tolerance=0.001)
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("a")

    def test_nested_dict_all_tolerated_passes(self):
        assert_that({"x": {"y": 1.0}}).is_equal_to({"x": {"y": 1.0001}}, tolerance=0.001)

    def test_nested_dict_partial_reports_only_real_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"x": {"y": 1.0, "z": 5}}).is_equal_to({"x": {"y": 1.0001, "z": 9}}, tolerance=0.001)
        paths = [entry.path for entry in exc_info.value.diff.entries]
        assert_that(paths).is_equal_to(["x.z"])

    def test_list_within_tolerance(self):
        assert_that([1.0, 2.0]).is_equal_to([1.0001, 2.0], tolerance=0.001)

    def test_list_leaf_beyond_tolerance_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1.0, 2.0]).is_equal_to([1.0, 5.0], tolerance=0.001)
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("[1]")

    def test_dataclass_field_within_tolerance(self):
        assert_that(Point(1.0, 2.0)).is_equal_to(Point(1.0001, 2.0), tolerance=0.001)

    def test_dataclass_field_beyond_tolerance_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Point(1.0, 2.0)).is_equal_to(Point(1.0, 9.0), tolerance=0.001)
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to(".y")

    def test_namedtuple_field_within_tolerance(self):
        assert_that(Pair(1.0, 2.0)).is_equal_to(Pair(1.0001, 2.0), tolerance=0.001)

    def test_model_field_within_tolerance(self):
        assert_that(FakeModel(a=1.0, b=2.0)).is_equal_to(FakeModel(a=1.0001, b=2.0), tolerance=0.001)


class TestComparators:
    def test_type_comparator_passes(self):
        assert_that([1, 2]).is_equal_to([10, 20], comparators={int: lambda a, e: True})

    def test_type_comparator_fails(self):
        with pytest.raises(AssertionFailure):
            assert_that([1]).is_equal_to([2], comparators={int: lambda a, e: a == e})

    def test_field_name_comparator_passes(self):
        assert_that({"id": 1, "x": 5}).is_equal_to({"id": 999, "x": 5}, comparators={"id": lambda a, e: True})

    def test_field_name_wins_over_type(self):
        comparators = {"id": lambda a, e: True, int: lambda a, e: a == e}
        assert_that({"id": 1, "n": 5}).is_equal_to({"id": 99, "n": 5}, comparators=comparators)
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"id": 1, "n": 5}).is_equal_to({"id": 99, "n": 6}, comparators=comparators)
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("n")

    def test_exact_type_wins_over_isinstance(self):
        class MyInt(int):
            pass

        calls = []
        comparators = {
            MyInt: lambda a, e: calls.append("exact") or True,
            int: lambda a, e: calls.append("isinstance") or True,
        }
        assert_that([MyInt(1)]).is_equal_to([MyInt(9)], comparators=comparators)
        assert_that(calls).is_equal_to(["exact"])

    def test_isinstance_fallback(self):
        class MyInt(int):
            pass

        assert_that([MyInt(1)]).is_equal_to([MyInt(9)], comparators={int: lambda a, e: True})

    def test_no_matching_comparator_falls_back_to_equality(self):
        with pytest.raises(AssertionFailure):
            assert_that([1]).is_equal_to([2], comparators={str: lambda a, e: True})

    def test_scalar_comparator_equal(self):
        assert_that(5).is_equal_to(6, comparators={int: lambda a, e: True})

    def test_scalar_comparator_leaf(self):
        with pytest.raises(AssertionFailure):
            assert_that(5).is_equal_to(6, comparators={int: lambda a, e: False})

    def test_container_comparator_at_top(self):
        assert_that([1]).is_equal_to([2], comparators={list: lambda a, e: True})

    def test_namedtuple_field_comparator_leaf(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Pair(1, 2)).is_equal_to(Pair(1, 9), comparators={int: lambda a, e: a == e})
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to(".b")

    def test_model_field_comparator_leaf(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(FakeModel(a=1, b=2)).is_equal_to(FakeModel(a=1, b=9), comparators={int: lambda a, e: a == e})
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to(".b")

    def test_nested_namedtuple_field_comparator_leaf(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"p": Pair(1, 2)}).is_equal_to({"p": Pair(1, 9)}, comparators={int: lambda a, e: a == e})
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("p.b")

    def test_nested_model_field_comparator_leaf(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"m": FakeModel(a=1, b=2)}).is_equal_to(
                {"m": FakeModel(a=1, b=9)}, comparators={int: lambda a, e: a == e}
            )
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("m.b")


class TestConfigValidation:
    def test_tolerance_not_real_raises(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(1).is_equal_to(1, tolerance="x")
        assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must be a real number")

    def test_tolerance_bool_raises(self):
        with pytest.raises(TypeError):
            assert_that(1).is_equal_to(1, tolerance=True)

    def test_tolerance_complex_raises(self):
        with pytest.raises(TypeError):
            assert_that(1).is_equal_to(1, tolerance=1j)

    def test_tolerance_nan_raises(self):
        with pytest.raises(ValueError) as exc_info:
            assert_that(1).is_equal_to(1, tolerance=float("nan"))
        assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must not be NaN")

    def test_tolerance_negative_raises(self):
        with pytest.raises(ValueError) as exc_info:
            assert_that(1).is_equal_to(1, tolerance=-1)
        assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must not be negative")

    def test_comparators_not_dict_raises(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(1).is_equal_to(1, comparators=[lambda a, e: True])
        assert_that(str(exc_info.value)).is_equal_to("given comparators arg must be a dict")

    def test_comparator_not_callable_raises(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(1).is_equal_to(1, comparators={int: "nope"})
        assert_that(str(exc_info.value)).is_equal_to("each comparator must be callable")


class TestRegexTypeIgnoreInclude:
    def test_ignore_by_regex(self):
        assert_that({"_id": 1, "name": "a"}).is_equal_to({"_id": 999, "name": "a"}, ignore=re.compile(r"^_"))

    def test_ignore_by_regex_still_catches_real_diff(self):
        with pytest.raises(AssertionFailure):
            assert_that({"_id": 1, "name": "a"}).is_equal_to({"_id": 1, "name": "b"}, ignore=re.compile(r"^_"))

    def test_ignore_by_type(self):
        assert_that({"x": 1.5, "n": "a"}).is_equal_to({"x": 9.9, "n": "a"}, ignore=float)

    def test_include_by_regex(self):
        assert_that({"a1": 1, "a2": 2, "b": 99}).is_equal_to({"a1": 1, "a2": 2, "b": 0}, include=re.compile(r"^a"))

    def test_include_by_type(self):
        assert_that({"x": 1, "n": "a"}).is_equal_to({"x": 1, "n": "different"}, include=int)

    def test_include_regex_no_match_does_not_report_missing(self):
        assert_that({"b": 1}).is_equal_to({"b": 1}, include=re.compile(r"^a"))


class TestDiffMessageConsistency:
    def test_tolerated_leaf_absent_from_diff_and_message(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1.0, "b": 5}).is_equal_to({"a": 1.0001, "b": 9}, tolerance=0.001)
        message = str(exc_info.value)
        paths = [entry.path for entry in exc_info.value.diff.entries]
        assert_that(paths).is_equal_to(["b"])
        assert_that(message).does_not_contain("1.0001")
        assert_that(message).contains("'b'")

    def test_comparator_equal_leaf_absent_from_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"id": 1, "n": 5}).is_equal_to({"id": 999, "n": 9}, comparators={"id": lambda a, e: True})
        paths = [entry.path for entry in exc_info.value.diff.entries]
        assert_that(paths).is_equal_to(["n"])


class TestConfigWithFilter:
    def test_ignore_combined_with_tolerance(self):
        assert_that({"id": 1, "v": 1.0}).is_equal_to({"id": 999, "v": 1.0001}, ignore="id", tolerance=0.001)

    def test_seq_filter_item_within_tolerance(self):
        assert_that([1.0]).is_equal_to([1.0001], include="x", tolerance=0.001)

    def test_seq_filter_item_beyond_tolerance_fails(self):
        with pytest.raises(AssertionFailure):
            assert_that([1.0]).is_equal_to([1.5], include="x", tolerance=0.001)

    def test_nested_dict_vs_scalar_under_config_fails_cleanly(self):
        # one side dict-nested, the other scalar: reports a clean difference, not a TypeError from
        # descending into the scalar.
        with pytest.raises(AssertionFailure):
            assert_that({"a": {"x": 1.0}}).is_equal_to({"a": 5.0}, tolerance=0.001)

    def test_tolerated_key_does_not_short_circuit_later_keys(self):
        # int keys hash deterministically (hash(0)=0 < hash(1)=1), so the set iterates 0 then 1: key 0 is
        # within tolerance and key 1 differs, so both keys must be checked, not just the first.
        with pytest.raises(AssertionFailure):
            assert_that({0: 1.0, 1: 5.0}).is_equal_to({0: 1.0001, 1: 9.0}, tolerance=0.001)


class TestNoConfigUnchanged:
    def test_plain_equal_dict_passes(self):
        assert_that({"a": 1}).is_equal_to({"a": 1})

    def test_plain_unequal_scalar_fails(self):
        with pytest.raises(AssertionFailure):
            assert_that(1).is_equal_to(2)
