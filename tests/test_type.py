import pytest

from assertpy2 import assert_that


class Foo:
    pass


class Bar(Foo):
    pass


def test_is_type_of():
    assert_that("foo").is_type_of(str)
    assert_that(123).is_type_of(int)
    assert_that(0.456).is_type_of(float)
    assert_that(["a", "b"]).is_type_of(list)
    assert_that(("a", "b")).is_type_of(tuple)
    assert_that({"a": 1, "b": 2}).is_type_of(dict)
    assert_that({"a", "b"}).is_type_of(set)
    assert_that(None).is_type_of(type(None))
    assert_that(Foo()).is_type_of(Foo)
    assert_that(Bar()).is_type_of(Bar)


def test_is_type_of_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_type_of(int)
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo:str> to be of type <int>, but was not.")


def test_is_type_of_bad_arg_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_type_of("bad")
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a type")


def test_is_type_of_subclass_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(Bar()).is_type_of(Foo)
    assert_that(str(exc_info.value)).starts_with("Expected <")
    assert_that(str(exc_info.value)).ends_with(":Bar> to be of type <Foo>, but was not.")


def test_is_instance_of():
    assert_that("foo").is_instance_of(str)
    assert_that(123).is_instance_of(int)
    assert_that(0.456).is_instance_of(float)
    assert_that(["a", "b"]).is_instance_of(list)
    assert_that(("a", "b")).is_instance_of(tuple)
    assert_that({"a": 1, "b": 2}).is_instance_of(dict)
    assert_that({"a", "b"}).is_instance_of(set)
    assert_that(None).is_instance_of(type(None))
    assert_that(Foo()).is_instance_of(Foo)
    assert_that(Bar()).is_instance_of(Bar)
    assert_that(Bar()).is_instance_of(Foo)


def test_is_instance_of_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_instance_of(int)
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo:str> to be instance of class <int>, but was not.")


def test_is_instance_of_bad_arg_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_instance_of("bad")
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a class")


def test_is_instance_of_any():
    assert_that(1).is_instance_of_any(int, float)
    assert_that(1.5).is_instance_of_any(int, float)
    assert_that("foo").is_instance_of_any(str, bytes)
    assert_that(Bar()).is_instance_of_any(Foo)
    assert_that(TimeoutError()).is_instance_of_any(OSError, ValueError)


def test_is_instance_of_any_chaining():
    assert_that(1).is_instance_of_any(int, float).is_equal_to(1)


def test_is_instance_of_any_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_instance_of_any(int, float)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <foo:str> to be instance of any of <int, float>, but was not."
    )


def test_is_instance_of_any_no_args_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("foo").is_instance_of_any()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_is_instance_of_any_bad_arg_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_instance_of_any(int, "bad")
    assert_that(str(exc_info.value)).is_equal_to("given args must all be classes")


def test_is_subclass_of():
    assert_that(Bar).is_subclass_of(Foo)
    assert_that(Bar).is_subclass_of(Bar)
    assert_that(bool).is_subclass_of(int)
    assert_that(TimeoutError).is_subclass_of(OSError)


def test_is_subclass_of_chaining():
    assert_that(Bar).is_subclass_of(Foo).is_not_none()


def test_is_subclass_of_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(Foo).is_subclass_of(Bar)
    assert_that(str(exc_info.value)).is_equal_to("Expected <Foo> to be subclass of <Bar>, but was not.")


def test_is_subclass_of_non_class_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(Foo()).is_subclass_of(Foo)
    assert_that(str(exc_info.value)).is_equal_to("val must be a class")


def test_is_subclass_of_bad_arg_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(Foo).is_subclass_of("bad")
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a class")
