import pytest

from assertpy2 import AssertionFailure, assert_that, match


class TestSatisfiesExactly:
    def test_matchers_pass(self):
        assert_that([1, "foo", 3.0]).satisfies_exactly(match.is_odd(), match.is_instance_of(str), match.is_positive())

    def test_callables_pass(self):
        assert_that([2, 4]).satisfies_exactly(lambda x: x == 2, lambda x: x == 4)

    def test_returns_self_for_chaining(self):
        assert_that([1, 2]).satisfies_exactly(match.is_odd(), match.is_even()).is_length(2)

    def test_single_item_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, 2, 3]).satisfies_exactly(match.is_odd(), match.is_odd(), match.is_odd())
        message = str(exc_info.value)
        assert_that(message).contains("1 item did not")
        diff = exc_info.value.diff
        assert_that(diff.kind).is_equal_to("match")
        assert_that(diff.entries).is_length(1)
        assert_that(diff.entries[0].path).is_equal_to("[1]")
        assert_that(diff.entries[0].actual).is_equal_to(2)
        assert_that(diff.entries[0].expected).is_equal_to("an odd integer")

    def test_multiple_items_fail(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([2, 4, 5]).satisfies_exactly(match.is_odd(), match.is_odd(), match.is_odd())
        assert_that(str(exc_info.value)).contains("2 items did not")
        assert_that(exc_info.value.diff.entries).is_length(2)

    def test_failing_callable_describes_in_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, 2]).satisfies_exactly(lambda x: x == 1, lambda x: x == 99)
        assert_that(exc_info.value.diff.entries[0].expected).contains("lambda")

    def test_length_greater_than_matchers_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, 2, 3]).satisfies_exactly(match.is_odd())
        assert_that(str(exc_info.value)).is_equal_to("Expected collection length <1>, but was <3>.")
        assert_that(exc_info.value.diff).is_none()

    def test_length_less_than_matchers_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1]).satisfies_exactly(match.is_odd(), match.is_odd())
        assert_that(str(exc_info.value)).is_equal_to("Expected collection length <2>, but was <1>.")

    def test_no_args_raises_value_error(self):
        with pytest.raises(ValueError) as exc_info:
            assert_that([1]).satisfies_exactly()
        assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")

    def test_not_iterable_raises_type_error(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).satisfies_exactly(match.is_odd())
        assert_that(str(exc_info.value)).is_equal_to("val is not iterable")

    def test_bad_matcher_raises_type_error(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that([1, 2]).satisfies_exactly("not a matcher", match.is_even())
        assert_that(str(exc_info.value)).is_equal_to("given arg must be a Matcher or callable")


class TestZipSatisfies:
    def test_pass(self):
        assert_that([1, 2, 3]).zip_satisfies([2, 4, 6], lambda left, right: right == left * 2)

    def test_returns_self_for_chaining(self):
        assert_that([1, 2]).zip_satisfies([1, 2], lambda left, right: left == right).is_length(2)

    def test_single_pair_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, 2, 3]).zip_satisfies([2, 4, 7], lambda left, right: right == left * 2)
        assert_that(str(exc_info.value)).contains("1 pair did not")
        diff = exc_info.value.diff
        assert_that(diff.kind).is_equal_to("match")
        assert_that(diff.entries).is_length(1)
        assert_that(diff.entries[0].path).is_equal_to("[2]")
        assert_that(diff.entries[0].actual).is_equal_to(3)
        assert_that(diff.entries[0].expected).is_equal_to(7)

    def test_multiple_pairs_fail(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, 2, 3]).zip_satisfies([9, 9, 9], lambda left, right: right == left * 2)
        assert_that(str(exc_info.value)).contains("3 pairs did not")
        assert_that(exc_info.value.diff.entries).is_length(3)

    def test_length_greater_than_other_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, 2, 3]).zip_satisfies([1, 2], lambda left, right: True)
        assert_that(str(exc_info.value)).is_equal_to("Expected collection length <2>, but was <3>.")

    def test_length_less_than_other_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1]).zip_satisfies([1, 2], lambda left, right: True)
        assert_that(str(exc_info.value)).is_equal_to("Expected collection length <2>, but was <1>.")

    def test_predicate_not_callable_raises_type_error(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that([1]).zip_satisfies([1], "not callable")
        assert_that(str(exc_info.value)).is_equal_to("given predicate must be callable")

    def test_val_not_iterable_raises_type_error(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).zip_satisfies([1], lambda left, right: True)
        assert_that(str(exc_info.value)).is_equal_to("val is not iterable")

    def test_other_not_iterable_raises_type_error(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that([1]).zip_satisfies(42, lambda left, right: True)
        assert_that(str(exc_info.value)).is_equal_to("given arg must be iterable")


class TestContainsOnlyOnce:
    def test_list_pass(self):
        assert_that([1, 2, 3]).contains_only_once(1, 3)

    def test_string_pass(self):
        assert_that("foo").contains_only_once("f")

    def test_returns_self_for_chaining(self):
        assert_that([1, 2, 3]).contains_only_once(1).contains_only_once(3)

    def test_missing_item_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, 2, 3]).contains_only_once(4)
        message = str(exc_info.value)
        assert_that(message).contains("did not contain <4>")
        diff = exc_info.value.diff
        assert_that(diff.kind).is_equal_to("contains")
        assert_that(diff.entries).is_length(1)
        assert_that(diff.entries[0].path).is_equal_to("missing")
        assert_that(diff.entries[0].expected).is_equal_to(4)

    def test_duplicated_item_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, 2, 2, 3]).contains_only_once(2)
        message = str(exc_info.value)
        assert_that(message).contains("contained <2> more than once")
        diff = exc_info.value.diff
        assert_that(diff.entries).is_length(1)
        assert_that(diff.entries[0].path).is_equal_to("duplicated")
        assert_that(diff.entries[0].actual).is_equal_to(2)
        assert_that(diff.entries[0].expected).is_equal_to(2)

    def test_missing_and_duplicated_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, 2, 2, 3]).contains_only_once(2, 4)
        message = str(exc_info.value)
        assert_that(message).contains("did not contain <4>")
        assert_that(message).contains("contained <2> more than once")
        assert_that(message).contains(" and ")
        assert_that(exc_info.value.diff.entries).is_length(2)

    def test_no_args_raises_value_error(self):
        with pytest.raises(ValueError) as exc_info:
            assert_that([1]).contains_only_once()
        assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")

    def test_not_iterable_raises_type_error(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).contains_only_once(1)
        assert_that(str(exc_info.value)).is_equal_to("val is not iterable")


class TestHasSameSizeAs:
    def test_list_vs_tuple_pass(self):
        assert_that([1, 2, 3]).has_same_size_as((4, 5, 6))

    def test_string_vs_list_pass(self):
        assert_that("foo").has_same_size_as([1, 2, 3])

    def test_returns_self_for_chaining(self):
        assert_that([1, 2]).has_same_size_as([3, 4]).is_length(2)

    def test_greater_size_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).has_same_size_as([1, 2])
        assert_that(str(exc_info.value)).is_equal_to(
            "Expected <[1, 2, 3]> to have same size as <[1, 2]> of length <2>, but was length <3>."
        )

    def test_lesser_size_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1]).has_same_size_as([1, 2])
        assert_that(str(exc_info.value)).contains("of length <2>, but was length <1>.")

    def test_other_not_sized_raises_type_error(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that([1]).has_same_size_as(42)
        assert_that(str(exc_info.value)).is_equal_to("given arg <int> is not a sized object")

    def test_val_not_sized_raises_type_error(self):
        with pytest.raises(TypeError):
            assert_that(42).has_same_size_as([1])

    def test_equal_large_lengths_compare_by_value(self):
        # lengths > 256 are not interned, so `!=` must compare by value, not identity (`is not`)
        assert_that([0] * 300).has_same_size_as((0,) * 300)
