import collections

import pytest

from assertpy2 import assert_that


def test_is_iterable():
    assert_that(["a", "b", "c"]).is_iterable()
    assert_that((1, 2, 3)).is_iterable()
    assert_that("foo").is_iterable()
    assert_that({"a": 1, "b": 2, "c": 3}.keys()).is_iterable()
    assert_that({"a": 1, "b": 2, "c": 3}.values()).is_iterable()
    assert_that({"a": 1, "b": 2, "c": 3}.items()).is_iterable()


def test_is_iterable_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_iterable()
    assert_that(str(exc_info.value)).is_equal_to("Expected iterable, but was not.")


def test_is_not_iterable():
    assert_that(123).is_not_iterable()
    assert_that({"a": 1, "b": 2, "c": 3}).is_iterable()


def test_is_not_iterable_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_not_iterable()
    assert_that(str(exc_info.value)).is_equal_to("Expected not iterable, but was.")


def test_is_subset_of():
    assert_that(["a", "b", "c"]).is_subset_of(["a", "b", "c"])
    assert_that(["a", "b", "c"]).is_subset_of(["a", "b", "c", "d"])
    assert_that(["a", "b", "c"]).is_subset_of(["a"], ["b"], ["c"])
    assert_that(["a", "b", "c"]).is_subset_of("a", "b", "c")
    assert_that(["a", "b", "a"]).is_subset_of(["a", "a", "b"])
    assert_that((1, 2, 3)).is_subset_of((1, 2, 3))
    assert_that((1, 2, 3)).is_subset_of((1, 2, 3, 4))
    assert_that((1, 2, 3)).is_subset_of((1,), (2,), (3,))
    assert_that((1, 2, 3)).is_subset_of(1, 2, 3)
    assert_that((1, 2, 1)).is_subset_of(1, 1, 2)
    assert_that("foo").is_subset_of("abcdefghijklmnopqrstuvwxyz")
    assert_that("foo").is_subset_of("abcdef", {"m", "n", "o"}, ["x", "y"])
    assert_that({1, 2, 3}).is_subset_of({1, 2, 3, 4})
    assert_that({"a": 1, "b": 2}).is_subset_of({"a": 1, "b": 2, "c": 3})
    assert_that({"a": 1, "b": 2}).is_subset_of({"a": 3}, {"b": 2}, {"a": 1})


def test_is_subset_of_single_item_superset():
    assert_that(["a"]).is_subset_of(["a"])
    assert_that((1,)).is_subset_of((1,))
    assert_that("ab").is_subset_of("ab")
    assert_that({1}).is_subset_of({1})
    assert_that({"a": 1}).is_subset_of({"a": 1})


def test_is_subset_of_failure_empty_superset():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_subset_of([])
    assert_that(str(exc_info.value)).contains("to be subset of <>")


def test_is_subset_of_failure_single_item_superset():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_subset_of(["x"])
    assert_that(str(exc_info.value)).contains("to be subset of <{'x'}>")
    assert_that(str(exc_info.value)).contains("but <'a', 'b', 'c'> were missing.")


def test_is_subset_of_failure_array():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_subset_of(["a", "b"])
    assert_that(str(exc_info.value)).contains("but <c> was missing.")


def test_is_subset_of_failure_set():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({1, 2, 3}).is_subset_of({1, 2})
    assert_that(str(exc_info.value)).contains("but <3> was missing.")


def test_is_subset_of_failure_string():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("abc").is_subset_of("abx")
    assert_that(str(exc_info.value)).contains("but <c> was missing.")


def test_is_subset_of_failure_dict_key():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_subset_of({"a": 1, "c": 3})
    assert_that(str(exc_info.value)).contains("but <{'b': 2}> was missing")


def test_is_subset_of_failure_dict_value():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_subset_of({"a": 1, "b": 22})
    assert_that(str(exc_info.value)).contains("but <{'b': 2}> was missing.")


def test_is_subset_of_failure_single_key_dict_value():
    # a single-key superset dict previously crashed with KeyError while formatting the message
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 5}).is_subset_of({"a": 3})
    assert_that(str(exc_info.value)).contains("to be subset of <{'a': 3}>").contains("missing")


def test_is_subset_of_failure_bad_dict_arg1():
    with pytest.raises(TypeError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_subset_of("foo")
    assert_that(str(exc_info.value)).contains("arg #1").contains("is not dict-like")


def test_is_subset_of_failure_bad_dict_arg2():
    with pytest.raises(TypeError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_subset_of({"a": 1}, "foo")
    assert_that(str(exc_info.value)).contains("arg #2").contains("is not dict-like")


def test_is_subset_of_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_subset_of(1234)
    assert_that(str(exc_info.value)).is_equal_to("val is not iterable")


def test_is_subset_of_bad_arg_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(["a", "b", "c"]).is_subset_of()
    assert_that(str(exc_info.value)).is_equal_to("one or more superset args must be given")


def test_is_sorted():
    assert_that([1, 2, 3]).is_sorted()
    assert_that((3, 2, 1)).is_sorted(reverse=True)
    assert_that(["a", "b", "c"]).is_sorted()
    assert_that(["c", "b", "a"]).is_sorted(reverse=True)
    assert_that("abcdefghijklmnopqrstuvwxyz").is_sorted()
    assert_that("zyxwvutsrqponmlkjihgfedcba").is_sorted(reverse=True)
    assert_that([{"a": 1}, {"a": 2}, {"a": 3}]).is_sorted(key=lambda x: x["a"])
    assert_that([{"a": 3}, {"a": 2}, {"a": 1}]).is_sorted(key=lambda x: x["a"], reverse=True)
    assert_that([("a", 2), ("b", 1)]).is_sorted(key=lambda x: x[0])
    assert_that([("a", 2), ("b", 1)]).is_sorted(key=lambda x: x[1], reverse=True)
    assert_that([1, 1, 1]).is_sorted()
    assert_that([1, 1, 1]).is_sorted(reverse=True)
    assert_that([]).is_sorted()
    assert_that([1]).is_sorted()

    ordered = collections.OrderedDict([("a", 2), ("b", 1)])
    assert_that(ordered).is_sorted()
    assert_that(ordered.keys()).is_sorted()


def test_is_sorted_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3, 4, 5, 6, -1, 7, 8, 9]).is_sorted()
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <[1, 2, 3, 4, 5, 6, -1, 7, 8, 9]> to be sorted, but subset <6, -1> at index 5 is not."
    )


def test_is_sorted_reverse_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).is_sorted(reverse=True)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <[1, 2, 3]> to be sorted reverse, but subset <1, 2> at index 0 is not."
    )


def test_is_sorted_failure_bad_val():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_sorted()
    assert_that(str(exc_info.value)).is_equal_to("val is not iterable")


def test_chaining():
    assert_that(["a", "b", "c"]).is_iterable().is_type_of(list).is_sorted().is_length(3)


def test_filter_that_empties_the_subject_says_so():
    # an empty derived value carries no context of its own: without the origin the failure reads the
    # same whether the input was empty or the filter removed every element
    with pytest.raises(AssertionError) as exc_info:
        assert_that([{"n": 1}, {"n": 2}]).filtered_on(lambda item: False).is_not_empty()
    assert_that(str(exc_info.value)).contains("filtered_on() kept 0 of 2 items")


def test_a_filter_that_keeps_something_adds_no_note():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([{"n": 1}, {"n": 2}]).filtered_on(lambda item: item["n"] == 1).is_length(5)
    assert_that(str(exc_info.value)).does_not_contain("filtered_on() kept")


def test_extracting_that_empties_the_subject_says_so():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([]).extracting("name").is_not_empty()
    assert_that(str(exc_info.value)).contains("extracting() produced 0 of 0 items")
