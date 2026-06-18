import collections

import pytest

from assertpy2 import assert_that

Foo = collections.namedtuple("Foo", ["bar", "baz"])
foo = Foo(bar="abc", baz=123)
foos = [foo, Foo(bar="xyz", baz=456)]


def test_namedtuple_equals():
    assert_that(foo).is_instance_of(Foo)
    assert_that(foo).is_instance_of(tuple)
    assert_that(foo).is_instance_of(object)
    assert_that(foo).is_type_of(Foo)
    assert_that(foo).is_equal_to(("abc", 123))
    assert_that(foo).is_equal_to(Foo(bar="abc", baz=123))
    assert_that(foo).is_not_equal_to(Foo(bar="abc", baz=124))
    assert_that(foo.bar).is_equal_to("abc")
    assert_that(foo[0]).is_equal_to("abc")
    assert_that(foo.baz).is_equal_to(123)
    assert_that(foo[1]).is_equal_to(123)
    assert_that(foo._fields).is_equal_to(("bar", "baz"))


def test_namedtuple_equals_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(foo).is_equal_to(Foo(bar="abc", baz=124))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <Foo(bar='abc', baz=123)> to be equal to <Foo(bar='abc', baz=124)>, but was not."
    )


def test_namedtuple_has():
    assert_that(foo).has_bar("abc")
    assert_that(foo).has_baz(123)


def test_namedtuple_has_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(foo).has_missing("x")
    assert_that(str(exc_info.value)).is_equal_to("Expected attribute <missing>, but val has no attribute <missing>.")


def test_namedtuple_extracting_by_index():
    assert_that(foos).extracting(0).is_equal_to(["abc", "xyz"])
    assert_that(foos).extracting(1).is_equal_to([123, 456])


def test_namedtuple_extracting_by_name():
    assert_that(foos).extracting("bar").is_equal_to(["abc", "xyz"])
    assert_that(foos).extracting("baz").is_equal_to([123, 456])


def test_namedtuple_extracting_by_name_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(foos).extracting("missing").is_equal_to("x")
    assert_that(str(exc_info.value)).is_equal_to("item attributes ('bar', 'baz') did no contain attribute <missing>")
