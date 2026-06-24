import sys

import pytest

from assertpy2 import assert_that


class Person:
    def __init__(self, first_name, last_name, shoe_size):
        self.first_name = first_name
        self.last_name = last_name
        self.shoe_size = shoe_size

    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def say_hello(self, name):
        return f"Hello, {name}!"


fred = Person("Fred", "Smith", 12)
john = Person("John", "Jones", 9.5)
people = [fred, john]


def test_extracting_property():
    assert_that(people).extracting("first_name").contains("Fred", "John")


def test_extracting_multiple_properties():
    assert_that(people).extracting("first_name", "last_name", "shoe_size").contains(
        ("Fred", "Smith", 12), ("John", "Jones", 9.5)
    )


def test_extracting_zero_arg_method():
    assert_that(people).extracting("full_name").contains("Fred Smith", "John Jones")


def test_extracting_property_and_method():
    assert_that(people).extracting("first_name", "full_name").contains(("Fred", "Fred Smith"), ("John", "John Jones"))


def test_extracting_dict():
    people_as_dicts = [{"first_name": person.first_name, "last_name": person.last_name} for person in people]
    assert_that(people_as_dicts).extracting("first_name").contains("Fred", "John")
    assert_that(people_as_dicts).extracting("last_name").contains("Smith", "Jones")


def test_extracting_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).extracting("bar")
    assert_that(str(exc_info.value)).is_equal_to("val is not iterable")


def test_extracting_bad_val_str_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").extracting("bar")
    assert_that(str(exc_info.value)).is_equal_to("val must not be string")


def test_extracting_empty_args_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(people).extracting()
    assert_that(str(exc_info.value)).is_equal_to("one or more name args must be given")


def test_extracting_bad_property_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(people).extracting("foo")
    assert_that(str(exc_info.value)).is_equal_to("item does not have property or zero-arg method <foo>")


def test_extracting_too_many_args_method_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(people).extracting("say_hello")
    assert_that(str(exc_info.value)).is_equal_to("item method <say_hello()> exists, but is not zero-arg method")


def test_extracting_dict_missing_key_failure():
    people_as_dicts = [{"first_name": person.first_name, "last_name": person.last_name} for person in people]
    with pytest.raises(ValueError) as exc_info:
        assert_that(people_as_dicts).extracting("foo")
    assert_that(str(exc_info.value)).matches(r"item keys \[.*\] did not contain key <foo>")


def test_described_as_with_extracting():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(people).described_as("extra msg").extracting("first_name").contains("Fred", "Bob")
    assert_that(str(exc_info.value)).is_equal_to(
        "[extra msg] Expected <['Fred', 'John']> to contain items <'Fred', 'Bob'>, but did not contain <Bob>."
    )


def test_described_as_with_double_extracting():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(people).described_as("extra msg").extracting("first_name").described_as("other msg").contains(
            "Fred", "Bob"
        )
    assert_that(str(exc_info.value)).is_equal_to(
        "[other msg] Expected <['Fred', 'John']> to contain items <'Fred', 'Bob'>, but did not contain <Bob>."
    )


users = [
    {"user": "Fred", "age": 36, "active": True},
    {"user": "Bob", "age": 40, "active": False},
    {"user": "Johnny", "age": 13, "active": True},
]


def test_extracting_filter():
    assert_that(users).extracting("user", filter="active").is_equal_to(["Fred", "Johnny"])
    assert_that(users).extracting("user", filter={"active": False}).is_equal_to(["Bob"])
    assert_that(users).extracting("user", filter={"age": 36, "active": True}).is_equal_to(["Fred"])
    assert_that(users).extracting("user", filter=lambda x: x["age"] > 20).is_equal_to(["Fred", "Bob"])
    assert_that(users).extracting("user", filter=lambda x: x["age"] < 10).is_empty()


def test_extracting_filter_none():
    assert_that(users).extracting("user", filter=None).is_equal_to(["Fred", "Bob", "Johnny"])


def test_extracting_filter_bad_type():
    with pytest.raises(TypeError, match="must be a str, dict, or callable"):
        assert_that(users).extracting("user", filter=123)


def test_extracting_filter_ignore_bad_key_types():
    assert_that(users).extracting("user", filter={"active": True, 123: "foo"}).is_equal_to(["Fred", "Johnny"])


def test_extracting_filter_custom_func():
    def _f(x):
        return x["user"] == "Bob" or x["age"] == 13

    assert_that(users).extracting("user", filter=_f).is_equal_to(["Bob", "Johnny"])


def test_extracting_filter_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(users).extracting("user", filter="foo")
    assert_that(str(exc_info.value)).ends_with("'] did not contain key <foo>")


def test_extracting_filter_dict_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(users).extracting("user", filter={"foo": "bar"})
    assert_that(str(exc_info.value)).ends_with("'] did not contain key <foo>")


def test_extracting_filter_multi_item_dict_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(users).extracting("user", filter={"age": 36, "active": True, "foo": "bar"})
    assert_that(str(exc_info.value)).ends_with("'] did not contain key <foo>")


def test_extracting_filter_lambda_failure():
    with pytest.raises(KeyError) as exc_info:
        assert_that(users).extracting("user", filter=lambda x: x["foo"] > 0)
    assert_that(str(exc_info.value)).is_equal_to("'foo'")


def test_extracting_filter_custom_func_failure():
    def _f(x):
        raise RuntimeError("foobar!")

    with pytest.raises(RuntimeError) as exc_info:
        assert_that(users).extracting("user", filter=_f)
    assert_that(str(exc_info.value)).is_equal_to("foobar!")


def test_extracting_filter_bad_values():
    bad = [{"user": "Fred", "age": 36}, {"user": "Bob", "age": "bad"}, {"user": "Johnny", "age": 13}]
    with pytest.raises(TypeError) as exc_info:
        assert_that(bad).extracting("user", filter=lambda x: x["age"] > 20)
    if sys.version_info[1] <= 5:
        assert_that(str(exc_info.value)).contains("unorderable types")
    else:
        assert_that(str(exc_info.value)).contains("not supported between instances of 'str' and 'int'")


def test_extracting_sort():
    assert_that(users).extracting("user", sort="age").is_equal_to(["Johnny", "Fred", "Bob"])
    assert_that(users).extracting("user", sort=["active", "age"]).is_equal_to(["Bob", "Johnny", "Fred"])
    assert_that(users).extracting("user", sort=("active", "age")).is_equal_to(["Bob", "Johnny", "Fred"])
    assert_that(users).extracting("user", sort=lambda x: -x["age"]).is_equal_to(["Bob", "Fred", "Johnny"])


def test_extracting_sort_none():
    assert_that(users).extracting("user", sort=None).is_equal_to(["Fred", "Bob", "Johnny"])


def test_extracting_sort_ignore_bad_type():
    assert_that(users).extracting("user", sort=123).is_equal_to(["Fred", "Bob", "Johnny"])


def test_extracting_sort_ignore_bad_key_types():
    assert_that(users).extracting("user", sort=["active", "age", 123]).is_equal_to(["Bob", "Johnny", "Fred"])


def test_extracting_sort_custom_func():
    def _f(x):
        if x["user"] == "Johnny":
            return 0
        elif x["age"] == 40:
            return 1
        return 10

    assert_that(users).extracting("user", sort=_f).is_equal_to(["Johnny", "Bob", "Fred"])


def test_extracting_sort_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(users).extracting("user", sort="foo")
    assert_that(str(exc_info.value)).ends_with("'] did not contain key <foo>")


def test_extracting_sort_list_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(users).extracting("user", sort=["foo"])
    assert_that(str(exc_info.value)).ends_with("'] did not contain key <foo>")


def test_extracting_sort_multi_item_dict_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(users).extracting("user", sort=["active", "age", "foo"])
    assert_that(str(exc_info.value)).ends_with("'] did not contain key <foo>")


def test_extracting_sort_lambda_failure():
    with pytest.raises(KeyError) as exc_info:
        assert_that(users).extracting("user", sort=lambda x: x["foo"] > 0)
    assert_that(str(exc_info.value)).is_equal_to("'foo'")


def test_extracting_sort_custom_func_failure():
    def _f(x):
        raise RuntimeError("foobar!")

    with pytest.raises(RuntimeError) as exc_info:
        assert_that(users).extracting("user", sort=_f)
    assert_that(str(exc_info.value)).is_equal_to("foobar!")


def test_extracting_sort_bad_values():
    bad = [{"user": "Fred", "age": 36}, {"user": "Bob", "age": "bad"}, {"user": "Johnny", "age": 13}]
    with pytest.raises(TypeError) as exc_info:
        assert_that(bad).extracting("user", sort="age")
    if sys.version_info[1] <= 5:
        assert_that(str(exc_info.value)).contains("unorderable types")
    else:
        assert_that(str(exc_info.value)).contains("not supported between instances of 'str' and 'int'")


def test_extracting_iterable_of_lists():
    matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    assert_that(matrix).extracting(0).is_equal_to([1, 4, 7])
    assert_that(matrix).extracting(0, 1).is_equal_to([(1, 2), (4, 5), (7, 8)])
    assert_that(matrix).extracting(-1).is_equal_to([3, 6, 9])
    assert_that(matrix).extracting(-1, -2).extracting(0).is_equal_to([3, 6, 9])


def test_extracting_iterable_multi_extracting():
    matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    assert_that(matrix).extracting(-1, 2).is_equal_to([(3, 3), (6, 6), (9, 9)])
    assert_that(matrix).extracting(-1, 1).extracting(1, 0).is_equal_to([(2, 3), (5, 6), (8, 9)])


def test_extracting_iterable_of_tuples():
    tuples = [(1, 2, 3), (4, 5, 6), (7, 8, 9)]
    assert_that(tuples).extracting(0).is_equal_to([1, 4, 7])
    assert_that(tuples).extracting(0, 1).is_equal_to([(1, 2), (4, 5), (7, 8)])
    assert_that(tuples).extracting(-1).is_equal_to([3, 6, 9])


def test_extracting_iterable_of_strings():
    strings = ["foo", "bar", "baz"]
    assert_that(strings).extracting(0).is_equal_to(["f", "b", "b"])
    assert_that(strings).extracting(0, 2).is_equal_to([("f", "o"), ("b", "r"), ("b", "z")])


def test_extracting_iterable_failure_set():
    with pytest.raises(TypeError) as exc_info:
        assert_that([{1}]).extracting(0).contains(1, 4, 7)
    assert_that(str(exc_info.value)).is_equal_to("item <set> does not have [] accessor")


def test_extracting_iterable_failure_out_of_range():
    with pytest.raises(IndexError) as exc_info:
        assert_that([[1], [2], [3]]).extracting(4).is_equal_to(0)
    assert_that(str(exc_info.value)).is_equal_to("list index out of range")


def test_extracting_iterable_failure_index_is_not_int():
    with pytest.raises(TypeError) as exc_info:
        assert_that([[1], [2], [3]]).extracting("1").is_equal_to(0)
    assert_that(str(exc_info.value)).contains("list indices must be integers")
