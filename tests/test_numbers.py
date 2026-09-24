import decimal
import math
import numbers

import pytest

from assertpy2 import assert_that, match


def test_is_zero():
    assert_that(0).is_zero()
    assert_that(0.0).is_zero()
    assert_that(0 + 0j).is_zero()


def test_is_zero_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(1).is_zero()
    assert_that(str(exc_info.value)).is_equal_to("Expected <1> to be equal to <0>, but was not.")


def test_is_zero_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_zero()
    assert_that(str(exc_info.value)).is_equal_to("val must be a number, but was <'foo'> (str)")


def test_is_not_zero():
    assert_that(1).is_not_zero()
    assert_that(0.001).is_not_zero()
    assert_that(0 + 1j).is_not_zero()


def test_is_not_zero_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_not_zero()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be not equal to <0>, but was.")


def test_is_not_zero_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_not_zero()
    assert_that(str(exc_info.value)).is_equal_to("val must be a number, but was <'foo'> (str)")


def test_is_nan():
    assert_that(float("NaN")).is_nan()
    assert_that(float("Inf") - float("Inf")).is_nan()


class _BrokenFloat:
    """Accepted as a real number and unreadable as one, which is the shape the guard had to tell apart."""

    def __float__(self) -> float:
        raise OverflowError("my __float__ is broken")

    def __repr__(self) -> str:
        return "<BrokenFloat>"


numbers.Real.register(_BrokenFloat)


@pytest.mark.parametrize("question", ["is_nan", "is_not_nan", "is_inf", "is_not_inf"])
def test_a_float_conversion_of_their_own_that_raises_is_not_an_answer(question):
    """The guard for a bignum swallowed an `OverflowError` from the value's own `__float__` as well.

    Swallowed, `is_not_nan()` and `is_not_inf()` held on a value nothing could read, which is an error
    in the value reported as a verdict.  Told apart by where the traceback stops, the way the ordering
    and matcher paths already tell it apart.
    """
    with pytest.raises(OverflowError, match="my __float__ is broken"):
        getattr(assert_that(_BrokenFloat()), question)()


def test_bignum_int_does_not_overflow_nan_inf_guards():
    # math.isnan/isinf raise OverflowError on an int too large for float; the guards must tolerate it
    big = math.factorial(200)
    assert_that(big).is_close_to(big, 1)
    assert_that(big).is_not_nan()
    assert_that(big).is_not_inf()
    with pytest.raises(AssertionError):
        assert_that(big).is_nan()
    with pytest.raises(AssertionError):
        assert_that(big).is_inf()


def test_nan_fails_relational_assertions():
    # NaN is unordered: it must FAIL relational assertions (diverges from assertpy, where it passes)
    nan = float("nan")
    for call in (
        lambda: assert_that(nan).is_positive(),
        lambda: assert_that(nan).is_negative(),
        lambda: assert_that(nan).is_between(0, 100),
        lambda: assert_that(nan).is_greater_than(0),
        lambda: assert_that(nan).is_greater_than_or_equal_to(0),
        lambda: assert_that(nan).is_less_than(0),
        lambda: assert_that(nan).is_less_than_or_equal_to(0),
    ):
        with pytest.raises(AssertionError):
            call()


def test_nan_passes_is_not_between():
    assert_that(float("nan")).is_not_between(0, 100)


def test_is_nan_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_nan()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be <NaN>, but was not.")


def test_is_nan_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_nan()
    assert_that(str(exc_info.value)).is_equal_to("val must be a number, but was <'foo'> (str)")


def test_is_nan_bad_type_failure_complex():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_nan()
    assert_that(str(exc_info.value)).is_equal_to("val must be a real number, but was <(1+2j)> (complex)")


def test_is_not_nan():
    assert_that(1).is_not_nan()
    assert_that(1.0).is_not_nan()


def test_is_not_nan_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(float("NaN")).is_not_nan()
    assert_that(str(exc_info.value)).is_equal_to("Expected not <NaN>, but was.")


def test_is_not_nan_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_not_nan()
    assert_that(str(exc_info.value)).is_equal_to("val must be a number, but was <'foo'> (str)")


def test_is_not_nan_bad_type_failure_complex():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_not_nan()
    assert_that(str(exc_info.value)).is_equal_to("val must be a real number, but was <(1+2j)> (complex)")


def test_is_inf():
    assert_that(float("Inf")).is_inf()
    assert_that(1e1000).is_inf()


def test_is_inf_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_inf()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be <Inf>, but was not.")


def test_is_inf_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_inf()
    assert_that(str(exc_info.value)).is_equal_to("val must be a number, but was <'foo'> (str)")


def test_is_inf_bad_type_failure_complex():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_inf()
    assert_that(str(exc_info.value)).is_equal_to("val must be a real number, but was <(1+2j)> (complex)")


def test_is_not_inf():
    assert_that(1).is_not_inf()
    assert_that(123.456).is_not_inf()


def test_is_not_inf_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(float("Inf")).is_not_inf()
    assert_that(str(exc_info.value)).is_equal_to("Expected not <Inf>, but was.")


def test_is_not_inf_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_not_inf()
    assert_that(str(exc_info.value)).is_equal_to("val must be a number, but was <'foo'> (str)")


def test_is_not_inf_bad_type_failure_complex():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_not_inf()
    assert_that(str(exc_info.value)).is_equal_to("val must be a real number, but was <(1+2j)> (complex)")


def test_is_greater_than():
    assert_that(123).is_greater_than(100)
    assert_that(123).is_greater_than(0)
    assert_that(123).is_greater_than(-100)
    assert_that(123).is_greater_than(122.5)


def test_is_greater_than_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_greater_than(123)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be greater than <123>, but was not.")


def test_is_greater_than_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_greater_than(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_greater_than_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_greater_than(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be comparable with val <'foo'> (str), but was <0> (int)"
    )


def test_is_greater_than_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_greater_than("foo")
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a number, but was <'foo'> (str)")


def test_is_greater_than_or_equal_to():
    assert_that(123).is_greater_than_or_equal_to(100)
    assert_that(123).is_greater_than_or_equal_to(123)
    assert_that(123).is_greater_than_or_equal_to(0)
    assert_that(123).is_greater_than_or_equal_to(-100)
    assert_that(123).is_greater_than_or_equal_to(122.5)


def test_is_greater_than_or_equal_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_greater_than_or_equal_to(1000)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be greater than or equal to <1000>, but was not.")


def test_is_greater_than_or_equal_to_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_greater_than_or_equal_to(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_greater_than_or_equal_to_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_greater_than_or_equal_to(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be comparable with val <'foo'> (str), but was <0> (int)"
    )


def test_is_greater_than_or_equal_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_greater_than_or_equal_to("foo")
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a number, but was <'foo'> (str)")


def test_is_less_than():
    assert_that(123).is_less_than(1000)
    assert_that(123).is_less_than(1e6)
    assert_that(-123).is_less_than(-100)
    assert_that(123).is_less_than(123.001)


def test_is_less_than_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_less_than(123)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be less than <123>, but was not.")


def test_is_less_than_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_less_than(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_less_than_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_less_than(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be comparable with val <'foo'> (str), but was <0> (int)"
    )


def test_is_less_than_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_less_than("foo")
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a number, but was <'foo'> (str)")


def test_is_less_than_or_equal_to():
    assert_that(123).is_less_than_or_equal_to(1000)
    assert_that(123).is_less_than_or_equal_to(123)
    assert_that(123).is_less_than_or_equal_to(1e6)
    assert_that(-123).is_less_than_or_equal_to(-100)
    assert_that(123).is_less_than_or_equal_to(123.001)


def test_is_less_than_or_equal_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_less_than_or_equal_to(100)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be less than or equal to <100>, but was not.")


def test_is_less_than_or_equal_to_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_less_than_or_equal_to(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_less_than_or_equal_to_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_less_than_or_equal_to(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be comparable with val <'foo'> (str), but was <0> (int)"
    )


def test_is_less_than_or_equal_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_less_than_or_equal_to("foo")
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a number, but was <'foo'> (str)")


def test_is_positive():
    assert_that(1).is_positive()


def test_is_positive_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_positive()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be greater than <0>, but was not.")


def test_is_negative():
    assert_that(-1).is_negative()


def test_is_negative_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_negative()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be less than <0>, but was not.")


def test_is_between():
    assert_that(123).is_between(120, 125)
    assert_that(123).is_between(0, 1e6)
    assert_that(-123).is_between(-150, -100)
    assert_that(123).is_between(122.999, 123.001)


def test_is_between_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_between(0, 1)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be between <0> and <1>, but was not.")


def test_is_between_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_between(0, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_between_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_between(0, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a number or a date, which is what an ordering is defined for, but was <'foo'> (str)"
    )


def test_is_between_low_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_between("foo", 1)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be a number, but was <'foo'> (str)")


def test_is_between_high_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_between(0, "foo")
    assert_that(str(exc_info.value)).is_equal_to("given high arg must be a number, but was <'foo'> (str)")


def test_is_between_bad_arg_delta_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(123).is_between(1, 0)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be less than given high arg")


def test_is_not_between():
    assert_that(123).is_not_between(124, 125)
    assert_that(123).is_not_between(1e5, 1e6)
    assert_that(-123).is_not_between(-1000, -150)
    assert_that(123).is_not_between(122.999, 122.9999)


def test_is_not_between_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_not_between(0, 1000)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to not be between <0> and <1000>, but was.")


def test_is_not_between_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_not_between(0, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_not_between_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_not_between(0, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a number or a date, which is what an ordering is defined for, but was <'foo'> (str)"
    )


def test_is_not_between_low_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_not_between("foo", 1)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be a number, but was <'foo'> (str)")


def test_is_not_between_high_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_not_between(0, "foo")
    assert_that(str(exc_info.value)).is_equal_to("given high arg must be a number, but was <'foo'> (str)")


def test_is_not_between_bad_arg_delta_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(123).is_not_between(1, 0)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be less than given high arg")


def test_is_close_to():
    assert_that(123.01).is_close_to(123, 1)
    assert_that(0.01).is_close_to(0, 1)
    assert_that(-123.01).is_close_to(-123, 1)


def test_is_close_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123.01).is_close_to(100, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <123.01> to be close to <100> within tolerance <1>, but was not."
    )


def test_is_close_to_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_close_to(0, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_close_to_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_close_to(123, 1)
    assert_that(str(exc_info.value)).is_equal_to("val must be a number or a datetime, but was <'foo'> (str)")


def test_is_close_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123.01).is_close_to("foo", 1)
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a number, but was <'foo'> (str)")


def test_is_close_to_bad_tolerance_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123.01).is_close_to(0, "foo")
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must be a number, but was <'foo'> (str)")


def test_is_close_to_negative_tolerance_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(123.01).is_close_to(123, -1)
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must be positive")


def test_is_close_to_nan_val_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(float("nan")).is_close_to(123, 0.1)
    assert_that(str(exc_info.value)).contains("to be close to")


def test_is_close_to_nan_other_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_close_to(float("nan"), 0.1)
    assert_that(str(exc_info.value)).contains("to be close to")


def test_is_close_to_nan_tolerance_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(123).is_close_to(123, float("nan"))
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must not be NaN")


def test_is_not_close_to_nan():
    assert_that(float("nan")).is_not_close_to(123, 0.1)


def test_is_not_close_to():
    assert_that(123.01).is_not_close_to(122, 1)
    assert_that(0.01).is_not_close_to(0, 0.001)
    assert_that(-123.01).is_not_close_to(-122, 1)


def test_is_not_close_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123.01).is_not_close_to(123, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <123.01> to not be close to <123> within tolerance <1>, but was."
    )


def test_is_not_close_to_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_not_close_to(0, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_not_close_to_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_not_close_to(123, 1)
    assert_that(str(exc_info.value)).is_equal_to("val must be a number or a datetime, but was <'foo'> (str)")


def test_is_not_close_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123.01).is_not_close_to("foo", 1)
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a number, but was <'foo'> (str)")


def test_is_not_close_to_bad_tolerance_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123.01).is_not_close_to(0, "foo")
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must be a number, but was <'foo'> (str)")


def test_is_not_close_to_negative_tolerance_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(123.01).is_not_close_to(123, -1)
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must be positive")


def test_comparable_duck_typing():
    assert_that("b").is_greater_than("a")
    assert_that("a").is_less_than("b")
    assert_that("b").is_greater_than_or_equal_to("a")
    assert_that("b").is_greater_than_or_equal_to("b")
    assert_that("a").is_less_than_or_equal_to("b")
    assert_that("a").is_less_than_or_equal_to("a")


def test_comparable_duck_typing_custom_class():
    class Rank:
        def __init__(self, level):
            self.level = level

        def __lt__(self, other):
            return self.level < other.level

        def __le__(self, other):
            return self.level <= other.level

        def __gt__(self, other):
            return self.level > other.level

        def __ge__(self, other):
            return self.level >= other.level

        def __repr__(self):
            return f"Rank({self.level})"

    low = Rank(1)
    mid = Rank(5)
    high = Rank(10)

    assert_that(high).is_greater_than(low)
    assert_that(low).is_less_than(high)
    assert_that(mid).is_greater_than_or_equal_to(mid)
    assert_that(mid).is_less_than_or_equal_to(mid)


def test_comparable_duck_typing_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("a").is_greater_than("b")
    assert_that(str(exc_info.value)).is_equal_to("Expected <a> to be greater than <b>, but was not.")


def test_comparable_no_ordering_failure():
    class NoOrder:
        pass

    with pytest.raises(TypeError) as exc_info:
        assert_that(NoOrder()).is_greater_than(NoOrder())
    # the repr of a local class carries its address, so the assertion is on the sentence around it
    message = str(exc_info.value)
    assert_that(message).starts_with("given other arg must be comparable with val <")
    assert_that(message).ends_with("(NoOrder)")


class _NumberWithNoOrder:
    """Registered as a real and converting to a float, and ordered against nothing."""

    def __float__(self) -> float:
        return 0.0

    def __repr__(self) -> str:
        return "<NumberWithNoOrder>"


numbers.Real.register(_NumberWithNoOrder)


@pytest.mark.parametrize(
    ("question", "arguments", "operand"),
    [
        ("is_between", (0, 9), "low"),
        ("is_not_between", (0, 9), "low"),
        ("is_close_to", (0, 1), "other"),
        ("is_not_close_to", (0, 1), "other"),
    ],
)
def test_a_range_over_a_pair_with_no_order_refuses_as_one_relation_does(question, arguments, operand):
    """The ordering engine's private `UnorderableError` reached the caller from these four, reading "pair".

    Not a `TypeError`, so `except TypeError` let it through, where 2.26.0 raised one.  The single relations
    refuse the same pair with this sentence, because they ask whether it orders before comparing.
    """
    with pytest.raises(TypeError) as caught:
        getattr(assert_that(_NumberWithNoOrder()), question)(*arguments)
    assert_that(str(caught.value)).is_equal_to(
        f"given {operand} arg must be comparable with val <<NumberWithNoOrder>> (_NumberWithNoOrder), but was <0> (int)"
    )


class _OrderedAgainstIntsOnly:
    """A registered real standing for five, ordered against an `int` and against nothing else."""

    def __float__(self) -> float:
        return 5.0

    def __lt__(self, other: object) -> bool:
        return 5 < other if type(other) is int else NotImplemented

    def __gt__(self, other: object) -> bool:
        return 5 > other if type(other) is int else NotImplemented

    def __repr__(self) -> str:
        return "<OrderedAgainstIntsOnly>"


numbers.Real.register(_OrderedAgainstIntsOnly)


def test_the_bound_a_range_never_reaches_is_never_asked():
    """Below the low bound the answer is known, so a high bound the value cannot be ordered against is not asked.

    Refused up front, it turned this passing `is_not_between` into a `TypeError`, where 2.26.0's chained
    comparison answered.
    """
    assert_that(_OrderedAgainstIntsOnly()).is_not_between(10, 20.5)
    with pytest.raises(AssertionError) as caught:
        assert_that(_OrderedAgainstIntsOnly()).is_between(10, 20.5)
    assert_that(str(caught.value)).is_equal_to(
        "Expected <<OrderedAgainstIntsOnly>> to be between <10> and <20.5>, but was not."
    )


@pytest.mark.parametrize(("value", "other"), [(-1.1, -0.9), (-0.9, -1.1)], ids=["value-below", "value-above"])
def test_a_distance_the_floats_round_past_the_tolerance_is_within_it_every_way_it_is_asked(value, other):
    """The two differ by `0.20000000000000007` as floats, and `is_close_to` held this pair before it was one rule."""
    assert_that(value).is_close_to(other, 0.2)
    assert_that(match.close_to(other, 0.2).matches(value)).is_true()
    assert_that(value).is_equal_to(other, tolerance=0.2)


@pytest.mark.parametrize("question", ["is_close_to", "is_not_close_to"])
def test_a_window_bound_the_value_cannot_be_ordered_against_is_refused_under_other(question):
    """The window is `other` plus and minus the tolerance, and it is those the value is ordered against.

    Checking `other` alone passed here, `10` being an `int`, and the float bounds let the engine's own
    error out.
    """
    with pytest.raises(TypeError) as caught:
        getattr(assert_that(_OrderedAgainstIntsOnly()), question)(10, 0.5)
    assert_that(str(caught.value)).is_equal_to(
        "given other arg must be comparable with val <<OrderedAgainstIntsOnly>> (_OrderedAgainstIntsOnly),"
        " but was <10> (int)"
    )


@pytest.mark.parametrize("value", ["a", b"a", [1], (1,), {"a": 1}], ids=["str", "bytes", "list", "tuple", "dict"])
def test_a_nan_on_the_right_does_not_make_an_unorderable_pair_a_verdict(value):
    """Answered before the pair was tried, a NaN turned "these cannot be compared" into "it was not".

    `assert_that("a").is_less_than(1)` refuses the operands; with a NaN in its place the same pair
    reported a failed comparison, which says a comparison happened.
    """
    with pytest.raises(TypeError) as caught:
        assert_that(value).is_less_than(float("nan"))
    assert_that(str(caught.value)).starts_with("given other arg must be comparable with val <")


def test_a_decimal_nan_still_answers_rather_than_signalling():
    """It signals instead of answering, which is why the pre-check existed: the answer is still neither."""
    with pytest.raises(AssertionError) as caught:
        assert_that(decimal.Decimal(1)).is_less_than(decimal.Decimal("NaN"))
    assert_that(str(caught.value)).is_equal_to("Expected <1> to be less than <NaN>, but was not.")

    with pytest.raises(AssertionError) as caught:
        assert_that(decimal.Decimal("NaN")).is_greater_than(decimal.Decimal(1))
    assert_that(str(caught.value)).is_equal_to("Expected <NaN> to be greater than <1>, but was not.")


def test_a_nan_is_absorbed_however_deep_the_signal_comes_from():
    """The operands decide, not the traceback: `Decimal` signals from one frame or from four.

    Measured, the C accelerator raises at the comparison site and `_pydecimal` raises four frames in,
    so reading the depth answered which interpreter build was running rather than what was compared.
    CI found it on a build this machine does not have.
    """

    class Deeply(decimal.Decimal):
        def __lt__(self, other):
            return self._signal()

        def __gt__(self, other):
            return self._signal()

        def _signal(self):
            return decimal.Decimal("NaN") < decimal.Decimal(1)

    with pytest.raises(AssertionError) as caught:
        assert_that(Deeply("NaN")).is_less_than(decimal.Decimal(1))
    assert_that(str(caught.value)).starts_with("Expected <NaN> to be less than <1>")


def test_a_subclass_does_not_decide_whether_its_own_signal_is_a_verdict():
    """It is not a NaN, and saying so must not turn its own `InvalidOperation` into a failed comparison."""

    class Liar(decimal.Decimal):
        def is_nan(self):
            return True

        def __lt__(self, other):
            raise decimal.InvalidOperation("own comparison failed")

        def __gt__(self, other):
            raise decimal.InvalidOperation("own comparison failed")

    with pytest.raises(decimal.InvalidOperation, match="own comparison failed"):
        assert_that(Liar(1)).is_less_than(decimal.Decimal(2))


def test_a_subclass_cannot_hide_that_it_is_a_nan():
    """The other direction: a real NaN saying it is not must still answer rather than signal."""

    class Hidden(decimal.Decimal):
        def is_nan(self):
            return False

    with pytest.raises(AssertionError) as caught:
        assert_that(Hidden("NaN")).is_less_than(decimal.Decimal(2))
    assert_that(str(caught.value)).starts_with("Expected <NaN> to be less than <2>")


def test_a_float_subclass_does_not_call_itself_unordered():
    """`value != value` is the NaN test, and a subclass owning `__ne__` owned the answer with it."""

    class Contrary(float):
        def __ne__(self, other):
            return True

        def __hash__(self):
            return 0

    assert_that([Contrary(1.0), 2.0]).is_sorted()
    with pytest.raises(AssertionError):
        assert_that([2.0, Contrary(1.0)]).is_sorted()


def test_a_subclass_saying_it_is_a_nan_does_not_change_a_tolerance_verdict():
    """The same lie in the other helper: it turned a passing `is_close_to` into a failure."""

    class Liar(decimal.Decimal):
        def is_nan(self):
            return True

    assert_that(Liar(1)).is_close_to(decimal.Decimal(1), decimal.Decimal("0.1"))
    assert_that(decimal.Decimal("NaN")).is_not_close_to(decimal.Decimal(1), decimal.Decimal("0.1"))


def test_a_signal_raised_inside_their_own_comparison_travels_out():
    """A bug in the value, not a pair without an order: answering it would send the reader elsewhere."""

    class Signalling(decimal.Decimal):
        def __lt__(self, other):
            raise decimal.InvalidOperation("from my own __lt__")

        def __gt__(self, other):
            raise decimal.InvalidOperation("from my own __gt__")

    with pytest.raises(decimal.InvalidOperation, match="from my own"):
        assert_that(Signalling(1)).is_less_than(decimal.Decimal(2))


def test_is_even():
    assert_that(0).is_even()
    assert_that(2).is_even()
    assert_that(-4).is_even()
    assert_that(1000000).is_even()


def test_is_even_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(1).is_even()
    assert_that(str(exc_info.value)).is_equal_to("Expected <1> to be even, but was not.")


def test_is_even_negative_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(-3).is_even()
    assert_that(str(exc_info.value)).is_equal_to("Expected <-3> to be even, but was not.")


def test_is_even_bad_type_float_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(2.0).is_even()
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer, but was <2.0> (float)")


def test_is_even_bad_type_str_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_even()
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer, but was <'foo'> (str)")


def test_is_even_bad_type_bool_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(True).is_even()
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer, but was <True> (bool)")


def test_is_odd():
    assert_that(1).is_odd()
    assert_that(3).is_odd()
    assert_that(-5).is_odd()
    assert_that(999999).is_odd()


def test_is_odd_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_odd()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be odd, but was not.")


def test_is_odd_negative_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(-4).is_odd()
    assert_that(str(exc_info.value)).is_equal_to("Expected <-4> to be odd, but was not.")


def test_is_odd_bad_type_float_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1.0).is_odd()
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer, but was <1.0> (float)")


def test_is_odd_bad_type_bool_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(False).is_odd()
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer, but was <False> (bool)")


def test_is_divisible_by():
    assert_that(10).is_divisible_by(5)
    assert_that(10).is_divisible_by(2)
    assert_that(10).is_divisible_by(1)
    assert_that(0).is_divisible_by(7)
    assert_that(-12).is_divisible_by(3)
    assert_that(12).is_divisible_by(-3)


def test_is_divisible_by_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(10).is_divisible_by(3)
    assert_that(str(exc_info.value)).is_equal_to("Expected <10> to be divisible by <3>, but was not.")


def test_is_divisible_by_bad_type_float_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(10.0).is_divisible_by(5)
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer, but was <10.0> (float)")


def test_is_divisible_by_bad_divisor_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(10).is_divisible_by(2.5)
    assert_that(str(exc_info.value)).is_equal_to("given divisor arg must be an integer, but was <2.5> (float)")


def test_is_divisible_by_bad_divisor_bool_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(10).is_divisible_by(True)
    assert_that(str(exc_info.value)).is_equal_to("given divisor arg must be an integer, but was <True> (bool)")


def test_is_divisible_by_zero_divisor_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(10).is_divisible_by(0)
    assert_that(str(exc_info.value)).is_equal_to("given divisor arg must not be zero")


def test_chaining():
    assert_that(123).is_greater_than(100).is_less_than(1000).is_between(120, 125).is_close_to(100, 25)


def test_chaining_even_odd():
    assert_that(4).is_even().is_positive().is_divisible_by(2)
    assert_that(3).is_odd().is_positive()


def test_is_between_boundary_inclusive():
    assert_that(5).is_between(5, 10)
    assert_that(10).is_between(5, 10)


def test_is_not_between_boundary_fails():
    with pytest.raises(AssertionError):
        assert_that(5).is_not_between(5, 10)
    with pytest.raises(AssertionError):
        assert_that(10).is_not_between(5, 10)


def test_is_close_to_boundary_inclusive():
    assert_that(10).is_close_to(8, 2)
    assert_that(6).is_close_to(8, 2)


def test_is_not_close_to_boundary_fails():
    with pytest.raises(AssertionError):
        assert_that(10).is_not_close_to(8, 2)
    with pytest.raises(AssertionError):
        assert_that(6).is_not_close_to(8, 2)


def test_is_divisible_by_negative_divisor():
    assert_that(9).is_divisible_by(-3)
    with pytest.raises(AssertionError):
        assert_that(10).is_divisible_by(-3)
