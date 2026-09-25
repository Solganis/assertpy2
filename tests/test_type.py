import typing

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
    assert_that(str(exc_info.value)).is_equal_to("given type arg must be a type, but was <'bad'> (str)")


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
    assert_that(str(exc_info.value)).is_equal_to("given class arg must be a class, but was <'bad'> (str)")


@pytest.mark.parametrize(
    "expected",
    [
        int | list[str],
        list[str] | int,
        str | list[str],
        (int, list[str]),
        (list[str], int),
        (str, (list[str],)),
        typing.Union[int, list[str]],  # noqa: UP007  # the old spelling is the subject
    ],
    ids=[
        "union-first-matches",
        "union-generic-first",
        "union-none-match",
        "tuple-first-matches",
        "tuple-generic-first",
        "nested-none-match",
        "legacy-union",
    ],
)
def test_is_instance_of_refuses_a_bad_member_whichever_comes_first(expected):
    with pytest.raises(TypeError, match="given class arg must be a class"):
        assert_that(1).is_instance_of(expected)


def test_is_instance_of_refuses_a_generic_alone_though_it_passes_for_a_class_on_3_10():
    with pytest.raises(TypeError, match="given class arg must be a class"):
        assert_that([1]).is_instance_of(list[int])


def test_is_instance_of_refuses_a_bad_member_before_the_negation_reads_a_pass():
    with pytest.raises(TypeError, match="given class arg must be a class"):
        assert_that(1).not_.is_instance_of((int, list[str]))


class _Named(typing.Protocol):
    name: str


class _AsksOnlyForNumbers(type):
    def __instancecheck__(cls, instance):
        return instance.real >= 0


class _NonNegative(metaclass=_AsksOnlyForNumbers):
    pass


@pytest.mark.parametrize("expected", [_Named, (int, _Named)], ids=["alone", "behind-a-matching-class"])
def test_is_instance_of_reports_a_protocol_isinstance_cannot_use_the_same_way_wherever_it_stands(expected):
    with pytest.raises(TypeError, match="runtime_checkable"):
        assert_that(1).is_instance_of(expected)


def test_is_instance_of_reads_the_members_left_to_right_as_isinstance_does():
    with pytest.raises(TypeError, match="given class arg must be a class"):
        assert_that(1).is_instance_of((list[str], _Named))
    with pytest.raises(TypeError, match="runtime_checkable"):
        assert_that(1).is_instance_of((_Named, list[str]))


def test_is_instance_of_asks_a_member_only_about_the_value_under_assertion():
    # its `__instancecheck__` reads `.real`, which `None` has not got: a stand-in value would break it
    assert_that(1).is_instance_of((int, _NonNegative))
    assert_that(1).is_instance_of_any(str, _NonNegative)


def test_is_instance_of_reads_a_tuple_from_its_storage_as_isinstance_does():
    class Shadowed(tuple):
        def __iter__(self):
            return iter((list[str],))

    assert_that(1).is_instance_of(Shadowed((int,)))
    assert_that(1).is_instance_of_any(Shadowed((int,)))


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
    assert_that(str(exc_info.value)).is_equal_to(
        "given class arg must be classes, but was <(<class 'int'>, 'bad')> (tuple)"
    )


@pytest.mark.parametrize(
    "classes",
    [(int, list[str]), (list[str], int), (int | list[str], float), (str, bytes, (list[str],))],
    ids=["first-matches", "generic-first", "union-member", "none-match"],
)
def test_is_instance_of_any_refuses_a_bad_member_whichever_comes_first(classes):
    with pytest.raises(TypeError, match="given class arg must be classes"):
        assert_that(1).is_instance_of_any(*classes)


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
    # the repr of an instance carries its address, so the assertion is on everything around it
    assert_that(str(exc_info.value)).starts_with("val must be a class, but was <").ends_with("> (Foo)")


def test_is_subclass_of_bad_arg_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(Foo).is_subclass_of("bad")
    assert_that(str(exc_info.value)).is_equal_to("given class arg must be a class, but was <'bad'> (str)")
