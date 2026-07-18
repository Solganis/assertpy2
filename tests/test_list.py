import collections

import pytest

from assertpy2 import AssertionFailure, assert_that


def test_is_length():
    assert_that(["a", "b", "c"]).is_length(3)
    assert_that((1, 2, 3, 4)).is_length(4)
    assert_that({"a": 1, "b": 2}).is_length(2)
    assert_that({"a", "b"}).is_length(2)


def test_is_length_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_length(4)
    assert_that(str(exc_info.value)).is_equal_to("Expected <['a', 'b', 'c']> to be of length <4>, but was <3>.")


def test_is_length_between():
    assert_that(["a", "b", "c"]).is_length_between(1, 5)
    assert_that("foo").is_length_between(3, 3)
    assert_that((1, 2)).is_length_between(2, 4)
    assert_that({"a": 1}).is_length_between(0, 1)


def test_is_length_between_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_length_between(4, 6)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <['a', 'b', 'c']> to be of length between <4> and <6>, but was <3>."
    )


def test_is_length_between_above_high_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_length_between(0, 2)
    assert_that(str(exc_info.value)).contains("to be of length between <0> and <2>, but was <3>.")


def test_is_length_between_bad_args():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["a"]).is_length_between("1", 2)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be an int")
    with pytest.raises(TypeError) as exc_info:
        assert_that(["a"]).is_length_between(1, "2")
    assert_that(str(exc_info.value)).is_equal_to("given high arg must be an int")
    with pytest.raises(ValueError) as exc_info:
        assert_that(["a"]).is_length_between(0, -1)
    assert_that(str(exc_info.value)).is_equal_to("given args must be positive ints")
    with pytest.raises(ValueError) as exc_info:
        assert_that(["a"]).is_length_between(2, 1)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be less than given high arg")


def test_is_length_bad_arg_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["a", "b", "c"]).is_length("bar")
    assert_that(str(exc_info.value)).is_equal_to("given arg must be an int")


def test_is_length_negative_arg_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(["a", "b", "c"]).is_length(-1)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a positive int")


def test_contains():
    assert_that(["a", "b", "c"]).contains("a")
    assert_that(["a", "b", "c"]).contains("c", "b", "a")
    assert_that((1, 2, 3, 4)).contains(1, 2, 3)
    assert_that((1, 2, 3, 4)).contains(4)
    assert_that({"a": 1, "b": 2, "c": 3}).contains("a")
    assert_that({"a": 1, "b": 2, "c": 3}).contains("a", "b")
    assert_that({"a", "b", "c"}).contains("a")
    assert_that({"a", "b", "c"}).contains("c", "b")

    fred = Person("fred")
    joe = Person("joe")
    bob = Person("bob")
    assert_that([fred, joe, bob]).contains(joe)


def test_contains_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).contains("x")
    assert_that(str(exc_info.value)).is_equal_to("Expected <['a', 'b', 'c']> to contain item <x>, but did not.")


def test_contains_multi_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).contains("a", "x", "z")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <['a', 'b', 'c']> to contain items <'a', 'x', 'z'>, but did not contain <'x', 'z'>."
    )


def test_contains_multi_item_single_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).contains("a", "b", "z")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <['a', 'b', 'c']> to contain items <'a', 'b', 'z'>, but did not contain <z>."
    )


def test_does_not_contain():
    assert_that(["a", "b", "c"]).does_not_contain("x")
    assert_that(["a", "b", "c"]).does_not_contain("x", "y")
    assert_that((1, 2, 3, 4)).does_not_contain(5)
    assert_that((1, 2, 3, 4)).does_not_contain(5, 6)
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain("x")
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain("x", "y")
    assert_that({"a", "b", "c"}).does_not_contain("x")
    assert_that({"a", "b", "c"}).does_not_contain("x", "y")

    fred = Person("fred")
    joe = Person("joe")
    bob = Person("bob")
    assert_that([fred, joe]).does_not_contain(bob)


def test_does_not_contain_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).does_not_contain("a")
    assert_that(str(exc_info.value)).is_equal_to("Expected <['a', 'b', 'c']> to not contain item <a>, but did.")


def test_does_not_contain_list_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).does_not_contain("x", "y", "a")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <['a', 'b', 'c']> to not contain items <'x', 'y', 'a'>, but did contain <a>."
    )


def test_does_not_contain_list_multi_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).does_not_contain("x", "a", "b")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <['a', 'b', 'c']> to not contain items <'x', 'a', 'b'>, but did contain <'a', 'b'>."
    )


def test_contains_only():
    assert_that(["a", "b", "c"]).contains_only("a", "b", "c")
    assert_that(["a", "b", "c"]).contains_only("c", "b", "a")
    assert_that(["a", "a", "b"]).contains_only("a", "b")
    assert_that(["a", "a", "a"]).contains_only("a")
    assert_that((1, 2, 3, 4)).contains_only(1, 2, 3, 4)
    assert_that((1, 2, 3, 1)).contains_only(1, 2, 3)
    assert_that((1, 2, 2, 1)).contains_only(1, 2)
    assert_that((1, 1, 1, 1)).contains_only(1)
    assert_that("foobar").contains_only("f", "o", "b", "a", "r")


def test_contains_only_no_args_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that([1, 2, 3]).contains_only()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_contains_only_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).contains_only(1, 2)
    assert_that(str(exc_info.value)).is_equal_to("Expected <[1, 2, 3]> to contain only <1, 2>, but did contain <3>.")


def test_contains_only_multi_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).contains_only(1, 4)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <[1, 2, 3]> to contain only <1, 4>, but did contain <2, 3> and did not contain <4>."
    )


def test_contains_only_superlist_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).contains_only(1, 2, 3, 4)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <[1, 2, 3]> to contain only <1, 2, 3, 4>, but did not contain <4>."
    )


def test_contains_only_tuple_items_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([("a",)]).contains_only("a")
    assert_that(str(exc_info.value)).contains("but did contain <('a',)>")


def test_contains_only_multi_tuple_items_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([("a",), ("b",)]).contains_only("x")
    assert_that(str(exc_info.value)).contains("but did contain <('a',), ('b',)>")


def test_contains_sequence():
    assert_that(["a", "b", "c"]).contains_sequence("a")
    assert_that(["a", "b", "c"]).contains_sequence("b")
    assert_that(["a", "b", "c"]).contains_sequence("c")
    assert_that(["a", "b", "c"]).contains_sequence("a", "b")
    assert_that(["a", "b", "c"]).contains_sequence("b", "c")
    assert_that(["a", "b", "c"]).contains_sequence("a", "b", "c")
    assert_that((1, 2, 3, 4)).contains_sequence(1)
    assert_that((1, 2, 3, 4)).contains_sequence(2)
    assert_that((1, 2, 3, 4)).contains_sequence(3)
    assert_that((1, 2, 3, 4)).contains_sequence(4)
    assert_that((1, 2, 3, 4)).contains_sequence(1, 2)
    assert_that((1, 2, 3, 4)).contains_sequence(2, 3)
    assert_that((1, 2, 3, 4)).contains_sequence(3, 4)
    assert_that((1, 2, 3, 4)).contains_sequence(1, 2, 3)
    assert_that((1, 2, 3, 4)).contains_sequence(2, 3, 4)
    assert_that((1, 2, 3, 4)).contains_sequence(1, 2, 3, 4)
    assert_that("foobar").contains_sequence("o", "o", "b")

    fred = Person("fred")
    joe = Person("joe")
    bob = Person("bob")
    assert_that([fred, joe, bob]).contains_sequence(fred, joe)


def test_contains_sequence_string_advances_past_match():
    # a single "X" cannot satisfy a two-"X" sequence: the search must advance past the first
    # match, so index arithmetic that re-finds the same "X" must not produce a false pass.
    with pytest.raises(AssertionError):
        assert_that("aX").contains_sequence("X", "X")


def test_contains_sequence_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).contains_sequence(4, 5)
    assert_that(str(exc_info.value)).is_equal_to("Expected <[1, 2, 3]> to contain sequence <4, 5>, but did not.")


def test_contains_sequence_tail_prefix_absent_fails_cleanly():
    # the last element matches the sequence's first item but the full sequence runs past the end:
    # the scan must fail cleanly (AssertionError), never walk off the end into IndexError (loop-bound guard)
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).contains_sequence(3, 9)
    assert_that(str(exc_info.value)).is_equal_to("Expected <[1, 2, 3]> to contain sequence <3, 9>, but did not.")


def test_contains_sequence_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).contains_sequence(1, 2)
    assert_that(str(exc_info.value)).is_equal_to("val is not iterable")


def test_contains_sequence_no_args_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that([1, 2, 3]).contains_sequence()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_contains_sequence_string_substrings():
    assert_that("foobar").contains_sequence("foo", "bar")
    assert_that("foobar").contains_sequence("f", "bar")
    assert_that("foobar").contains_sequence("fo", "ob", "ar")
    assert_that("foobar").contains_sequence("foo")
    assert_that("foobar").contains_sequence("bar")
    assert_that("abcdef").contains_sequence("ab", "cd", "ef")
    assert_that("abcdef").contains_sequence("a", "f")
    assert_that("hello world").contains_sequence("hello", "world")


def test_contains_sequence_string_substrings_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foobar").contains_sequence("bar", "foo")
    assert_that(str(exc_info.value)).is_equal_to("Expected <foobar> to contain sequence <'bar', 'foo'>, but did not.")


def test_contains_sequence_string_substrings_not_found():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foobar").contains_sequence("foo", "xyz")
    assert_that(str(exc_info.value)).is_equal_to("Expected <foobar> to contain sequence <'foo', 'xyz'>, but did not.")


def test_contains_sequence_string_bad_arg_type():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foobar").contains_sequence("foo", 123)
    assert_that(str(exc_info.value)).is_equal_to("given args must be strings when val is a string")


def test_contains_duplicates():
    assert_that(["a", "b", "c", "a"]).contains_duplicates()
    assert_that(("a", "b", "c", "a")).contains_duplicates()
    assert_that([1, 2, 3, 3]).contains_duplicates()
    assert_that((1, 2, 3, 3)).contains_duplicates()
    assert_that("foobar").contains_duplicates()

    fred = Person("fred")
    joe = Person("joe")
    assert_that([fred, joe, fred]).contains_duplicates()


def test_contains_duplicates_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).contains_duplicates()
    assert_that(str(exc_info.value)).is_equal_to("Expected <[1, 2, 3]> to contain duplicates, but did not.")


def test_contains_duplicates_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).contains_duplicates()
    assert_that(str(exc_info.value)).is_equal_to("val is not iterable")


def test_does_not_contain_duplicates():
    assert_that(["a", "b", "c"]).does_not_contain_duplicates()
    assert_that(("a", "b", "c")).does_not_contain_duplicates()
    assert_that({"a", "b", "c"}).does_not_contain_duplicates()
    assert_that([1, 2, 3]).does_not_contain_duplicates()
    assert_that((1, 2, 3)).does_not_contain_duplicates()
    assert_that({1, 2, 3}).does_not_contain_duplicates()
    assert_that("fobar").does_not_contain_duplicates()

    fred = Person("fred")
    joe = Person("joe")
    assert_that([fred, joe]).does_not_contain_duplicates()


def test_does_not_contain_duplicates_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3, 3]).does_not_contain_duplicates()
    assert_that(str(exc_info.value)).is_equal_to("Expected <[1, 2, 3, 3]> to not contain duplicates, but did.")


def test_does_not_contain_duplicates_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).does_not_contain_duplicates()
    assert_that(str(exc_info.value)).is_equal_to("val is not iterable")


def test_contains_duplicates_unhashable_items():
    # a list of dicts (unhashable) must use an == based fallback, not raise "val is not iterable"
    assert_that([{"a": 1}, {"b": 2}, {"a": 1}]).contains_duplicates()
    with pytest.raises(AssertionError):
        assert_that([{"a": 1}, {"b": 2}]).contains_duplicates()


def test_does_not_contain_duplicates_unhashable_items():
    assert_that([{"a": 1}, {"b": 2}]).does_not_contain_duplicates()
    with pytest.raises(AssertionError):
        assert_that([{"a": 1}, {"a": 1}]).does_not_contain_duplicates()


def test_contains_only_once_unhashable_items():
    assert_that([{"a": 1}, {"b": 2}]).contains_only_once({"a": 1})
    with pytest.raises(AssertionError):
        assert_that([{"a": 1}, {"a": 1}]).contains_only_once({"a": 1})


def test_is_empty():
    assert_that([]).is_empty()
    assert_that(()).is_empty()
    assert_that({}).is_empty()


def test_is_empty_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b"]).is_empty()
    assert_that(str(exc_info.value)).is_equal_to("Expected <['a', 'b']> to be empty, but was not.")


def test_is_not_empty():
    assert_that(["a", "b"]).is_not_empty()
    assert_that((1, 2)).is_not_empty()
    assert_that({"a": 1, "b": 2}).is_not_empty()
    assert_that({"a", "b"}).is_not_empty()


def test_is_not_empty_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([]).is_not_empty()
    assert_that(str(exc_info.value)).is_equal_to("Expected not empty, but was empty.")


def test_starts_with():
    assert_that(["a", "b", "c"]).starts_with("a")
    assert_that((1, 2, 3)).starts_with(1)

    ordered = collections.OrderedDict([("z", 9), ("x", 7), ("y", 8)])
    assert_that(ordered.keys()).starts_with("z")
    assert_that(ordered.values()).starts_with(9)
    assert_that(ordered.items()).starts_with(("z", 9))


def test_starts_with_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).starts_with("d")
    assert_that(str(exc_info.value)).is_equal_to("Expected ['a', 'b', 'c'] to start with <d>, but did not.")


def test_starts_with_bad_val_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that([]).starts_with("a")
    assert_that(str(exc_info.value)).is_equal_to("val must not be empty")


def test_starts_with_bad_prefix_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["a", "b", "c"]).starts_with("a", "b")
    assert_that(str(exc_info.value)).contains("starts_with() takes 2 positional arguments but 3 were given")


def test_ends_with():
    assert_that(["a", "b", "c"]).ends_with("c")
    assert_that((1, 2, 3)).ends_with(3)

    ordered = collections.OrderedDict([("z", 9), ("x", 7), ("y", 8)])
    assert_that(ordered.keys()).ends_with("y")
    assert_that(ordered.values()).ends_with(8)
    assert_that(ordered.items()).ends_with(("y", 8))


def test_ends_with_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).ends_with("d")
    assert_that(str(exc_info.value)).is_equal_to("Expected ['a', 'b', 'c'] to end with <d>, but did not.")


def test_ends_with_bad_val_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that([]).ends_with("a")
    assert_that(str(exc_info.value)).is_equal_to("val must not be empty")


def test_ends_with_bad_prefix_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["a", "b", "c"]).ends_with("b", "c")
    assert_that(str(exc_info.value)).contains("ends_with() takes 2 positional arguments but 3 were given")


def test_chaining():
    assert_that(["a", "b", "c"]).is_type_of(list).is_length(3).contains("a").does_not_contain("x")
    assert_that(["a", "b", "c"]).is_type_of(list).is_length(3).contains("a", "b").does_not_contain("x", "y")


def test_list_of_lists():
    nested = [[1, 2, 3], ["a", "b", "c"], (4, 5, 6)]
    assert_that(nested).is_length(3)
    assert_that(nested).is_equal_to([[1, 2, 3], ["a", "b", "c"], (4, 5, 6)])

    assert_that(nested).contains([1, 2, 3])
    assert_that(nested).contains(["a", "b", "c"])
    assert_that(nested).contains((4, 5, 6))

    assert_that(nested).starts_with([1, 2, 3])
    assert_that(nested).ends_with((4, 5, 6))

    assert_that(nested[0]).is_equal_to([1, 2, 3])
    assert_that(nested[2]).is_equal_to((4, 5, 6))

    assert_that(nested[0][0]).is_equal_to(1)
    assert_that(nested[2][2]).is_equal_to(6)


def test_list_of_dicts():
    dicts = [{"a": 1}, {"b": 2}, {"c": 3}]
    assert_that(dicts).is_length(3)
    assert_that(dicts).is_equal_to([{"a": 1}, {"b": 2}, {"c": 3}])

    assert_that(dicts).contains({"a": 1})
    assert_that(dicts).contains({"b": 2})
    assert_that(dicts).contains({"c": 3})

    assert_that(dicts).starts_with({"a": 1})
    assert_that(dicts).ends_with({"c": 3})

    assert_that(dicts[0]).is_equal_to({"a": 1})
    assert_that(dicts[2]).is_equal_to({"c": 3})

    assert_that(dicts[0]["a"]).is_equal_to(1)
    assert_that(dicts[2]["c"]).is_equal_to(3)


class Person:
    def __init__(self, name):
        self.name = name


class TestContainsClosestElement:
    def test_closest_element_pinpoints_difference(self):
        haystack = [{"id": 1, "name": "Alice", "role": "admin"}, {"id": 2, "name": "Bob", "role": "user"}]
        with pytest.raises(AssertionError) as exc:
            assert_that(haystack).contains({"id": 2, "name": "Bob", "role": "ADMIN"})
        assert_that(str(exc.value)).contains("Closest element").contains("role ('user' != 'ADMIN')")

    def test_closest_element_populates_structured_diff(self):
        haystack = [{"id": 2, "name": "Bob", "role": "user"}]
        with pytest.raises(AssertionError) as exc:
            assert_that(haystack).contains({"id": 2, "name": "Bob", "role": "ADMIN"})
        assert_that([entry.path for entry in exc.value.diff.entries]).contains("role")

    def test_unrelated_needle_has_no_closest(self):
        with pytest.raises(AssertionError) as exc:
            assert_that([{"id": 1, "name": "Alice"}]).contains({"zzz": 999})
        assert_that(str(exc.value)).does_not_contain("Closest element")

    def test_scalar_haystack_with_dict_needle_has_no_closest(self):
        with pytest.raises(AssertionError) as exc:
            assert_that([1, 2, 3]).contains({"a": 1})
        assert_that(str(exc.value)).does_not_contain("Closest element")

    def test_closest_is_the_most_similar_of_several(self):
        # element 0 differs only in y; element 1 differs in x and y -> element 0 is closest
        with pytest.raises(AssertionError) as exc:
            assert_that([{"id": 2, "x": 1, "y": 2}, {"id": 2, "x": 9, "y": 9}]).contains({"id": 2, "x": 1, "y": 1})
        assert_that(str(exc.value)).contains("{'id': 2, 'x': 1, 'y': 2}").contains("y (2 != 1)")

    def test_many_differences_are_truncated(self):
        # 4 differing paths, limit 3 -> reports exactly "and 1 more" (pins the count, not just its presence)
        with pytest.raises(AssertionError) as exc:
            assert_that([{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}]).contains(
                {"a": 1, "b": 99, "c": 99, "d": 99, "e": 99}
            )
        assert_that(str(exc.value)).contains("Closest element").contains("and 1 more")

    def test_differences_exactly_at_limit_have_no_more_suffix(self):
        # exactly `limit` (3) differing paths -> all shown, no "and 0 more" suffix (boundary at == limit)
        with pytest.raises(AssertionError) as exc:
            assert_that([{"a": 1, "b": 2, "c": 3, "d": 4}]).contains({"a": 1, "b": 99, "c": 99, "d": 99})
        assert_that(str(exc.value)).contains("Closest element").does_not_contain("more")


class TestContainsExactly:
    def test_list(self):
        assert_that([1, 2, 3]).contains_exactly(1, 2, 3)

    def test_tuple(self):
        assert_that((1, 2, 3)).contains_exactly(1, 2, 3)

    def test_string_chars(self):
        assert_that("abc").contains_exactly("a", "b", "c")

    def test_wrong_order_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_exactly(1, 3, 2)
        assert_that(str(exc_info.value)).contains("to contain exactly")

    def test_missing_items_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_exactly(1, 2)
        assert_that(str(exc_info.value)).contains("to contain exactly")

    def test_extra_items_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2]).contains_exactly(1, 2, 3)
        assert_that(str(exc_info.value)).contains("to contain exactly")

    def test_empty_args_failure(self):
        with pytest.raises(ValueError) as exc_info:
            assert_that([1]).contains_exactly()
        assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")

    def test_not_iterable_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).contains_exactly(1)
        assert_that(str(exc_info.value)).is_equal_to("val is not iterable")

    def test_unhashable_items_failure(self):
        # the failure path used Counter and crashed with TypeError on unhashable items
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([[1], [2]]).contains_exactly([2], [1], [3])
        assert_that(str(exc_info.value)).contains("to contain exactly")
        entries = exc_info.value.diff.entries
        assert_that([(entry.path, entry.actual, entry.expected) for entry in entries]).is_equal_to(
            [("missing", None, [3])]
        )


class TestContainsExactlyInAnyOrder:
    def test_list(self):
        assert_that([3, 1, 2]).contains_exactly_in_any_order(1, 2, 3)

    def test_same_order(self):
        assert_that([1, 2, 3]).contains_exactly_in_any_order(1, 2, 3)

    def test_tuple(self):
        assert_that((2, 3, 1)).contains_exactly_in_any_order(1, 2, 3)

    def test_string_chars(self):
        assert_that("cba").contains_exactly_in_any_order("a", "b", "c")

    def test_duplicates_counted(self):
        assert_that(["b", "a", "b"]).contains_exactly_in_any_order("a", "b", "b")

    def test_unhashable_items(self):
        assert_that([[3], [1, 2]]).contains_exactly_in_any_order([1, 2], [3])

    def test_mixed_non_comparable_types_diff_fails_cleanly(self):
        # a failing diff over non-comparable items (int + str) must sort stably by repr for the message,
        # never by natural order (which raises TypeError on mixed types)
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, "a"]).contains_exactly_in_any_order(2, "b")
        assert_that(str(exc_info.value)).is_equal_to(
            "Expected <[1, 'a']> to contain exactly <2, 'b'> in any order, but did not."
        )

    def test_extra_duplicate_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 2]).contains_exactly_in_any_order(1, 2)
        assert_that(str(exc_info.value)).is_equal_to(
            "Expected <[1, 2, 2]> to contain exactly <1, 2> in any order, but did not."
        )

    def test_missing_duplicate_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2]).contains_exactly_in_any_order(1, 2, 2)
        assert_that(str(exc_info.value)).contains("to contain exactly").contains("in any order")

    def test_failure_diff_entries(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, 4]).contains_exactly_in_any_order(1, 2)
        diff = exc_info.value.diff
        assert_that(diff.kind).is_equal_to("contains")
        assert_that([(entry.path, entry.actual, entry.expected) for entry in diff.entries]).is_equal_to(
            [("extra", 4, None), ("missing", None, 2)]
        )

    def test_unhashable_items_failure(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([[1], [1]]).contains_exactly_in_any_order([1], [2])
        assert_that(str(exc_info.value)).contains("in any order")
        entries = exc_info.value.diff.entries
        assert_that([(entry.path, entry.actual, entry.expected) for entry in entries]).is_equal_to(
            [("extra", [1], None), ("missing", None, [2])]
        )

    def test_empty_args_failure(self):
        with pytest.raises(ValueError) as exc_info:
            assert_that([1]).contains_exactly_in_any_order()
        assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")

    def test_not_iterable_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).contains_exactly_in_any_order(1)
        assert_that(str(exc_info.value)).is_equal_to("val is not iterable")


class TestContainsInOrder:
    def test_all_present(self):
        assert_that([1, 5, 2, 8, 3]).contains_in_order(1, 2, 3)

    def test_contiguous(self):
        assert_that([1, 2, 3]).contains_in_order(1, 2, 3)

    def test_strings(self):
        assert_that(["a", "x", "b", "y", "c"]).contains_in_order("a", "b", "c")

    def test_single_item(self):
        assert_that([1, 2, 3]).contains_in_order(2)

    def test_wrong_order_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_in_order(3, 1)
        assert_that(str(exc_info.value)).contains("in order, but did not")

    def test_missing_item_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_in_order(1, 4)
        assert_that(str(exc_info.value)).contains("in order, but did not")

    def test_empty_args_failure(self):
        with pytest.raises(ValueError) as exc_info:
            assert_that([1]).contains_in_order()
        assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")

    def test_not_iterable_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).contains_in_order(1)
        assert_that(str(exc_info.value)).is_equal_to("val is not iterable")
