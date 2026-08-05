import copy
import datetime
import decimal
import re
import uuid
from collections import OrderedDict, namedtuple
from dataclasses import dataclass

import pytest

from assertpy2 import AssertionFailure, assert_that, match

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

    def test_equal_infinities_within_tolerance(self):
        # inf == inf must be within any tolerance (abs(inf - inf) is NaN, which broke the check)
        assert_that(float("inf")).is_equal_to(float("inf"), tolerance=0.001)
        assert_that(float("-inf")).is_equal_to(float("-inf"), tolerance=0.001)
        with pytest.raises(AssertionFailure):
            assert_that(float("inf")).is_equal_to(float("-inf"), tolerance=0.001)


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


@dataclass
class OptUser:
    name: str
    age: int | None = None
    score: float | None = None


class TestIgnoreNull:
    def test_object_expected_null_field_ignored(self):
        assert_that(OptUser("A", 30, 9.5)).is_equal_to(OptUser("A"), ignore_null=True)

    def test_object_non_null_field_still_compared(self):
        with pytest.raises(AssertionFailure):
            assert_that(OptUser("A", 30)).is_equal_to(OptUser("B", 30), ignore_null=True)

    def test_dict_expected_null_value_ignored(self):
        assert_that({"a": 1, "b": 5}).is_equal_to({"a": 1, "b": None}, ignore_null=True)

    def test_actual_null_vs_expected_value_not_masked(self):
        # safety: only expected-None fields are skipped, so an unexpectedly-None actual is still caught
        with pytest.raises(AssertionFailure):
            assert_that(OptUser("A", None)).is_equal_to(OptUser("A", 30), ignore_null=True)

    def test_nested_expected_null_field_ignored(self):
        assert_that({"user": {"name": "A", "age": 30}}).is_equal_to(
            {"user": {"name": "A", "age": None}}, ignore_null=True
        )

    def test_list_elements_are_not_null_fields(self):
        # a None *element* has no field name, so ignore_null must not skip it
        with pytest.raises(AssertionFailure):
            assert_that([1, 5]).is_equal_to([1, None], ignore_null=True)

    def test_combined_with_tolerance(self):
        assert_that(OptUser("A", 30, 1.0)).is_equal_to(OptUser("A", None, 1.0001), ignore_null=True, tolerance=0.001)

    def test_ignore_null_not_a_bool_fails(self):
        with pytest.raises(TypeError, match="ignore_null"):
            assert_that({}).is_equal_to({}, ignore_null="yes")


_ELIDED = re.compile(r"[\[{]\.\.")


def _elision_matrix():
    """(label, actual, expected, kwargs) across the shapes whose failure message gets reduced."""
    shapes = [
        ("flat_dict", {"a": 1.0}, {"a": 1.001}, {"a": 9.0}),
        ("nested_dict", {"n": {"a": 1.0}}, {"n": {"a": 1.001}}, {"n": {"a": 9.0}}),
        ("dict_to_list_dicts", {"d": [{"a": 1.0}]}, {"d": [{"a": 1.001}]}, {"d": [{"a": 9.0}]}),
        ("dict_to_list_lists", {"d": [[1.0]]}, {"d": [[1.001]]}, {"d": [[9.0]]}),
        ("dict_to_tuple", {"d": (1.0,)}, {"d": (1.001,)}, {"d": (9.0,)}),
        ("dict_to_dataclass", {"d": Point(1.0, 2.0)}, {"d": Point(1.001, 2.0)}, {"d": Point(9.0, 2.0)}),
        ("dict_to_namedtuple", {"d": Pair(1.0, 2.0)}, {"d": Pair(1.001, 2.0)}, {"d": Pair(9.0, 2.0)}),
        ("dict_to_model", {"d": FakeModel(a=1.0)}, {"d": FakeModel(a=1.001)}, {"d": FakeModel(a=9.0)}),
        (
            "deep_payload",
            {"ok": True, "data": [{"id": 1, "o": {"s": 1.0}}]},
            {"ok": True, "data": [{"id": 1, "o": {"s": 1.001}}]},
            {"ok": True, "data": [{"id": 1, "o": {"s": 9.0}}]},
        ),
    ]
    configs = [
        ("no_config", {}),
        ("tolerance", {"tolerance": 0.01}),
        ("comparators", {"comparators": {float: lambda x, y: abs(x - y) < 0.01}}),
        ("ignore_null", {"ignore_null": True}),
    ]
    specs = [("no_spec", {}), ("ignore_bare", {"ignore": "a"}), ("ignore_tuple", {"ignore": ("d", "a")})]
    for name, actual, near, far in shapes:
        variants = [("near", near), ("far", far), ("extra_key", {**actual, "zz": 1})]
        for variant, expected in variants:
            for config_name, config in configs:
                for spec_name, spec in specs:
                    label = f"{name}/{variant}/{config_name}/{spec_name}"
                    yield label, actual, expected, {**config, **spec}


def _elided_failure(actual, expected, kwargs):
    """Return the failure whose message hides the equal parts, or ``None`` when the invariant is moot.

    A plain ``AssertionError``, or a message that names both values outright, is readable on its own
    and carries no diff by design, so only the elided form takes part in the sweep.
    """
    try:
        assert_that(actual).is_equal_to(expected, **kwargs)
    except AssertionFailure as failure:
        return failure if _ELIDED.search(str(failure).splitlines()[0]) else None
    except AssertionError:
        return None
    return None


class TestElidedFailureAlwaysCarriesDiff:
    """A message that hides the equal parts must be explained by the structured diff.

    The dict failure message is reduced to the differing keys (``{.., 'b': 2}``), which is only
    readable because the diff spells out what changed.  The verdict and the diff are produced at
    separate call sites, so drift between them yields a failure that claims inequality while showing
    nothing - a real 2026-07 defect.  This pins the pairing across a shape/config/spec matrix rather
    than for one hand-picked case.
    """

    def test_every_elided_failure_is_explained_by_its_diff(self):
        violations = [
            f"{label}: {str(failure).splitlines()[0]}"
            for label, actual, expected, kwargs in _elision_matrix()
            if (failure := _elided_failure(actual, expected, kwargs)) is not None
            and (failure.diff is None or not failure.diff.entries)
        ]
        assert_that(violations).is_empty()

    def test_the_matrix_actually_exercises_elided_failures(self):
        # a guard on the guard: if the message stops eliding, the sweep above would go vacuous
        elided = [
            label
            for label, actual, expected, kwargs in _elision_matrix()
            if _elided_failure(actual, expected, kwargs) is not None
        ]
        assert_that(elided).is_not_empty()
        assert_that(len(elided)).is_greater_than(20)


class TestConfigThroughNestedContainers:
    """A container reached through a dict keeps the compare config.

    The equality decision delegates to the same structural walker that renders the diff, so every shape
    the walker decomposes is compared under the config.  It used to fall back to plain equality there, so
    tolerance / comparators / ignore_null silently stopped applying below the first non-dict container -
    the shape of almost every JSON API response.
    """

    def test_tolerance_reaches_dicts_inside_a_nested_list(self):
        assert_that({"d": [{"s": 1.0}]}).is_equal_to({"d": [{"s": 1.001}]}, tolerance=0.01)

    def test_tolerance_reaches_a_nested_list_of_lists(self):
        assert_that({"d": [[1.0]]}).is_equal_to({"d": [[1.001]]}, tolerance=0.01)

    def test_tolerance_reaches_a_nested_tuple(self):
        assert_that({"d": ({"s": 1.0},)}).is_equal_to({"d": ({"s": 1.001},)}, tolerance=0.01)

    def test_tolerance_reaches_a_nested_dataclass(self):
        assert_that({"d": Point(1.0, 2.0)}).is_equal_to({"d": Point(1.001, 2.0)}, tolerance=0.01)

    def test_tolerance_reaches_a_nested_namedtuple(self):
        assert_that({"d": Pair(1.0, 2.0)}).is_equal_to({"d": Pair(1.001, 2.0)}, tolerance=0.01)

    def test_tolerance_reaches_a_nested_model(self):
        assert_that({"d": FakeModel(s=1.0)}).is_equal_to({"d": FakeModel(s=1.001)}, tolerance=0.01)

    def test_tolerance_reaches_a_list_of_dataclasses(self):
        assert_that({"d": [Point(1.0, 2.0)]}).is_equal_to({"d": [Point(1.001, 2.0)]}, tolerance=0.01)

    def test_comparators_reach_a_nested_list(self):
        close = {float: lambda actual, expected: abs(actual - expected) < 0.01}
        assert_that({"d": [{"s": 1.0}]}).is_equal_to({"d": [{"s": 1.001}]}, comparators=close)

    def test_ignore_null_reaches_a_nested_list(self):
        assert_that({"d": [{"a": 1, "b": 5}]}).is_equal_to({"d": [{"a": 1, "b": None}]}, ignore_null=True)

    def test_identical_container_short_circuits_on_identity(self):
        # identity first, the way Python's own container comparison does, so a self-unequal value matches
        shared = [float("nan")]
        assert_that({"d": shared, "k": 1}).is_equal_to({"d": shared, "k": 2}, ignore="k")

    def test_length_mismatch_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": [{"s": 1.0}]}).is_equal_to({"d": [{"s": 1.0}, {"s": 2.0}]}, tolerance=0.01)

    def test_leaf_outside_tolerance_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": [1.0]}).is_equal_to({"d": [9.0]}, tolerance=0.01)

    def test_dataclass_outside_tolerance_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": Point(1.0, 2.0)}).is_equal_to({"d": Point(9.0, 2.0)}, tolerance=0.01)

    def test_dict_element_difference_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": [{"s": 1.0, "n": "a"}]}).is_equal_to({"d": [{"s": 1.0, "n": "b"}]}, tolerance=0.01)

    def test_inner_list_difference_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": [[1.0]]}).is_equal_to({"d": [[9.0]]}, tolerance=0.01)

    def test_undecomposable_leaf_difference_still_fails(self):
        # a string is a leaf the walker does not decompose, so it falls back to the plain check
        with pytest.raises(AssertionError):
            assert_that({"d": "a"}).is_equal_to({"d": "b"}, tolerance=0.01)

    def test_plain_difference_without_config_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": [1, 2], "k": 1}).is_equal_to({"d": [1, 9], "k": 2}, ignore="k")


class TestStrictTypes:
    """`==` alone lets a type change pass at any depth, so `strict_types` closes it."""

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            (True, 1),
            (0, False),
            (1, 1.0),
            (decimal.Decimal(1), 1),
            ([True], [1]),
            ({"active": True}, {"active": 1}),
            ({"a": {"b": [{"c": True}]}}, {"a": {"b": [{"c": 1}]}}),
            (OrderedDict(a=1), {"a": 1}),
            ((1, True), (1, 1)),
            (Point(1, 2), Point(1.0, 2)),
        ],
        ids=str,
    )
    def test_a_type_change_is_caught_at_any_depth(self, actual, expected):
        assert_that(actual).is_equal_to(expected)  # plain equality accepts all of these
        with pytest.raises(AssertionError):
            assert_that(actual).is_equal_to(expected, strict_types=True)

    def test_equal_payload_still_passes(self):
        payload = {"id": 1, "tags": ["a"], "meta": {"ok": True, "n": None}}
        assert_that(payload).is_equal_to(dict(payload), strict_types=True)

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ({1, 2}, {1, 2}),
            ({"s": {1, 2}}, {"s": {1, 2}}),
            ({"s": frozenset({1})}, {"s": frozenset({1})}),
            ([{1}], [{1}]),
            ({"s": {"a": {1}}}, {"s": {"a": {1}}}),
        ],
        ids=str,
    )
    def test_an_equal_set_is_not_read_as_a_difference(self, actual, expected):
        # forcing the walk must only ever enter what the walker takes apart. A set is a container it
        # does not, so entering one hands the caller a value it reads as a difference
        assert_that(actual).is_equal_to(expected, strict_types=True)
        assert_that(match.equal_to(expected, strict_types=True).matches(actual)).is_true()

    def test_a_differing_set_is_still_reported(self):
        with pytest.raises(AssertionError):
            assert_that({"s": {1}}).is_equal_to({"s": {2}}, strict_types=True)

    def test_an_undecomposable_item_survives_the_filtered_sequence_path(self):
        # ignore/include on a list routes items through their own comparison, which has to read a
        # forced descent the same way the diff walker does
        assert_that([{1}]).is_equal_to([{1}], strict_types=True, ignore="absent")
        with pytest.raises(AssertionError):
            assert_that([{1}]).is_equal_to([{2}], strict_types=True, ignore="absent")

    @pytest.mark.parametrize(
        "value",
        [uuid.UUID(int=1), decimal.Decimal(3), datetime.date(2026, 1, 1), {1, 2}, frozenset({1}), "abc", b"ab"],
        ids=str,
    )
    def test_an_undecomposable_value_at_the_top_level_is_equal_to_its_copy(self, value):
        # the top-level builder has its own ladder, wider than the nested walker's: it knows sets,
        # strings and bytes. A forced descent has to read "the ladder ran out" as equality there too
        assert_that(value).is_equal_to(copy.deepcopy(value), strict_types=True)

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            (uuid.UUID(int=1), uuid.UUID(int=2)),
            (datetime.date(2026, 1, 1), datetime.date(2026, 1, 2)),
            ("abc", "abd"),
        ],
        ids=str,
    )
    def test_a_differing_undecomposable_value_is_still_reported(self, actual, expected):
        with pytest.raises(AssertionError):
            assert_that(actual).is_equal_to(expected, strict_types=True)

    def test_an_undecomposable_field_of_a_namedtuple_survives(self):
        # the namedtuple walker has its own descent helper, and it must carry the reason through
        pair = namedtuple("pair", ["first", "second"])
        assert_that(pair(1, {2})).is_equal_to(pair(1, {2}), strict_types=True)
        with pytest.raises(AssertionError):
            assert_that(pair(1, {2})).is_equal_to(pair(1, {3}), strict_types=True)

    def test_matchers_stay_exempt(self):
        # the expected leaf is a Matcher, not a value, so comparing its type would break composition
        assert_that({"id": 7}).is_equal_to({"id": match.greater_than(0)}, strict_types=True)
        assert_that({"u": {"age": 30}}).is_equal_to({"u": {"age": match.between(18, 120)}}, strict_types=True)
        assert_that([1, 5]).is_equal_to([1, match.greater_than(4)], strict_types=True)

    def test_a_comparator_still_owns_its_leaves(self):
        assert_that({"a": True}).is_equal_to({"a": 1}, strict_types=True, comparators={bool: lambda x, y: True})

    def test_strictness_wins_over_tolerance(self):
        # a tolerance says how far apart two numbers may be, not that they may be different types
        assert_that(1).is_equal_to(1.0, tolerance=0.5)
        with pytest.raises(AssertionError):
            assert_that(1).is_equal_to(1.0, tolerance=0.5, strict_types=True)

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ({True: "a"}, {1: "a"}),
            ({1: "a"}, {1.0: "a"}),
            ({1}, {1.0}),
            ({True}, {1}),
            (frozenset({1}), frozenset({True})),
            ({"s": {1}}, {"s": {1.0}}),
        ],
        ids=str,
    )
    def test_hash_matched_positions_are_a_known_gap(self, actual, expected):
        # a dict key and a set element are found by hash, and 1, 1.0 and True hash alike, so the pair
        # is matched before anything looks at its type. Documented, not fixed.
        assert_that(actual).is_equal_to(expected, strict_types=True)
        assert_that(match.equal_to(expected, strict_types=True).matches(actual)).is_true()

    @pytest.mark.parametrize("bad", ["yes", 1, None])
    def test_non_bool_is_rejected(self, bad):
        with pytest.raises(TypeError, match="strict_types arg must be a bool"):
            assert_that(1).is_equal_to(1, strict_types=bad)

    def test_a_self_referential_pair_behaves_the_same_either_way(self):
        # forcing the walk into a container whose own `==` was true raises the question of what happens
        # on a cycle. Nothing new: two distinct self-referential structures already exhaust the stack
        # without the flag, and so does bare `==` (CPython's guard covers `a is b`, not this)
        actual = {"x": 1}
        actual["self"] = actual
        expected = {"x": 1}
        expected["self"] = expected
        with pytest.raises(RecursionError):
            assert_that(actual).is_equal_to(expected)
        with pytest.raises(RecursionError):
            assert_that(actual).is_equal_to(expected, strict_types=True)

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ({"cfg": OrderedDict(a=1)}, {"cfg": {"a": 1}}),
            ({"o": {"cfg": OrderedDict(a=1)}}, {"o": {"cfg": {"a": 1}}}),
            ([OrderedDict(a=1)], [{"a": 1}]),
            ({"t": (1, 2)}, {"t": [1, 2]}),
        ],
        ids=str,
    )
    def test_a_container_type_change_is_caught_below_the_top_level(self, actual, expected):
        # the top-level guard sits before the dict-like dispatch; these prove the node check covers the rest
        with pytest.raises(AssertionError):
            assert_that(actual).is_equal_to(expected, strict_types=True)

    def test_a_shared_subnode_is_not_walked_twice(self):
        # forcing the walk gives up the identity shortcut CPython applies inside a container, and a
        # shared subnode is where that shortcut is doing real work: here it is also cyclic
        shared = {"k": 1}
        shared["self"] = shared
        assert_that({"cfg": shared, "n": 1}).is_equal_to({"cfg": shared, "n": 1}, strict_types=True)

    def test_the_same_nan_object_still_compares_equal(self):
        # `nan != nan`, so a container holding one is equal to itself only through that same shortcut.
        # Without it a strict run would disagree with a plain one over something unrelated to types.
        nan = float("nan")
        assert_that([nan]).is_equal_to([nan])
        assert_that([nan]).is_equal_to([nan], strict_types=True)
        assert_that({"v": nan}).is_equal_to({"v": nan}, strict_types=True)

    def test_negation_goes_through_not_(self):
        # is_not_equal_to takes no comparison kwargs; `.not_` is how the whole family is inverted
        assert_that({"a": True}).not_.is_equal_to({"a": 1}, strict_types=True)
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            assert_that(True).is_not_equal_to(1, strict_types=True)


class TestConfigSurvivesTheFilteredPaths:
    """`ignore` / `include` route the comparison through a separate walk, which must carry the config.

    Every knob was only ever tested on the plain path or on scalar elements, so dropping the config on
    the filtered list and object paths changed nothing the suite looked at: tolerance stopped being
    applied to dict-valued elements and to object fields, silently turning a pass into a failure.
    """

    def test_tolerance_reaches_dict_valued_list_elements(self):
        assert_that([{"value": 1.0, "id": 1}]).is_equal_to([{"value": 1.05, "id": 99}], ignore="id", tolerance=0.1)
        with pytest.raises(AssertionFailure):
            assert_that([{"value": 1.0, "id": 1}]).is_equal_to([{"value": 1.5, "id": 99}], ignore="id", tolerance=0.1)

    def test_tolerance_reaches_object_fields(self):
        assert_that(Point(1.0, 1.0)).is_equal_to(Point(1.05, 99.0), ignore="y", tolerance=0.1)
        with pytest.raises(AssertionFailure):
            assert_that(Point(1.0, 1.0)).is_equal_to(Point(1.5, 99.0), ignore="y", tolerance=0.1)

    def test_strict_types_reaches_a_nested_list_element(self):
        assert_that([[1]]).is_equal_to([[1]], strict_types=True, ignore="absent")
        with pytest.raises(AssertionFailure):
            assert_that([[1]]).is_equal_to([[True]], strict_types=True, ignore="absent")
        with pytest.raises(AssertionFailure):
            assert_that([(1, 2)]).is_equal_to([(True, 2)], strict_types=True, ignore="absent")

    def test_an_element_pair_where_only_one_side_introspects(self):
        # the pair guard is a conjunction: with a dataclass on one side and an int on the other, taking
        # either side alone walks a None as if it were a mapping
        with pytest.raises(AssertionFailure, match="index"):
            assert_that([1]).is_equal_to([Point(1.0, 2.0)], ignore="id")
        with pytest.raises(AssertionFailure, match="index"):
            assert_that([Point(1.0, 2.0)]).is_equal_to([1], ignore="id")
