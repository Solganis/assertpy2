import pytest

from assertpy2 import assert_that


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
    assert_that(str(exc_info.value)).is_equal_to("val is not numeric")


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
    assert_that(str(exc_info.value)).is_equal_to("val is not numeric")


def test_is_nan():
    assert_that(float("NaN")).is_nan()
    assert_that(float("Inf") - float("Inf")).is_nan()


def test_is_nan_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_nan()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be <NaN>, but was not.")


def test_is_nan_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_nan()
    assert_that(str(exc_info.value)).is_equal_to("val is not numeric")


def test_is_nan_bad_type_failure_complex():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_nan()
    assert_that(str(exc_info.value)).is_equal_to("val is not real number")


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
    assert_that(str(exc_info.value)).is_equal_to("val is not numeric")


def test_is_not_nan_bad_type_failure_complex():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_not_nan()
    assert_that(str(exc_info.value)).is_equal_to("val is not real number")


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
    assert_that(str(exc_info.value)).is_equal_to("val is not numeric")


def test_is_inf_bad_type_failure_complex():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_inf()
    assert_that(str(exc_info.value)).is_equal_to("val is not real number")


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
    assert_that(str(exc_info.value)).is_equal_to("val is not numeric")


def test_is_not_inf_bad_type_failure_complex():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_not_inf()
    assert_that(str(exc_info.value)).is_equal_to("val is not real number")


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
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <complex>")


def test_is_greater_than_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_greater_than(0)
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <str>")


def test_is_greater_than_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_greater_than("foo")
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a number, but was <str>")


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
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <complex>")


def test_is_greater_than_or_equal_to_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_greater_than_or_equal_to(0)
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <str>")


def test_is_greater_than_or_equal_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_greater_than_or_equal_to("foo")
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a number, but was <str>")


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
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <complex>")


def test_is_less_than_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_less_than(0)
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <str>")


def test_is_less_than_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_less_than("foo")
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a number, but was <str>")


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
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <complex>")


def test_is_less_than_or_equal_to_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_less_than_or_equal_to(0)
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <str>")


def test_is_less_than_or_equal_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_less_than_or_equal_to("foo")
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a number, but was <str>")


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
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <complex>")


def test_is_between_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_between(0, 1)
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <str>")


def test_is_between_low_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_between("foo", 1)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be numeric, but was <str>")


def test_is_between_high_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_between(0, "foo")
    assert_that(str(exc_info.value)).is_equal_to("given high arg must be numeric, but was <str>")


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
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <complex>")


def test_is_not_between_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_not_between(0, 1)
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <str>")


def test_is_not_between_low_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_not_between("foo", 1)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be numeric, but was <str>")


def test_is_not_between_high_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_not_between(0, "foo")
    assert_that(str(exc_info.value)).is_equal_to("given high arg must be numeric, but was <str>")


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
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for complex numbers")


def test_is_close_to_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_close_to(123, 1)
    assert_that(str(exc_info.value)).is_equal_to("val is not numeric or datetime")


def test_is_close_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123.01).is_close_to("foo", 1)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be numeric")


def test_is_close_to_bad_tolerance_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123.01).is_close_to(0, "foo")
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must be numeric")


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
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for complex numbers")


def test_is_not_close_to_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_not_close_to(123, 1)
    assert_that(str(exc_info.value)).is_equal_to("val is not numeric or datetime")


def test_is_not_close_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123.01).is_not_close_to("foo", 1)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be numeric")


def test_is_not_close_to_bad_tolerance_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123.01).is_not_close_to(0, "foo")
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must be numeric")


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
    assert_that(str(exc_info.value)).is_equal_to("ordering is not defined for type <NoOrder>")


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
    assert_that(str(exc_info.value)).is_equal_to("val is not an integer, got float")


def test_is_even_bad_type_str_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_even()
    assert_that(str(exc_info.value)).is_equal_to("val is not an integer, got str")


def test_is_even_bad_type_bool_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(True).is_even()
    assert_that(str(exc_info.value)).is_equal_to("val is not an integer, got bool")


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
    assert_that(str(exc_info.value)).is_equal_to("val is not an integer, got float")


def test_is_odd_bad_type_bool_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(False).is_odd()
    assert_that(str(exc_info.value)).is_equal_to("val is not an integer, got bool")


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
    assert_that(str(exc_info.value)).is_equal_to("val is not an integer, got float")


def test_is_divisible_by_bad_divisor_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(10).is_divisible_by(2.5)
    assert_that(str(exc_info.value)).is_equal_to("given divisor arg must be an integer, got float")


def test_is_divisible_by_bad_divisor_bool_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(10).is_divisible_by(True)
    assert_that(str(exc_info.value)).is_equal_to("given divisor arg must be an integer, got bool")


def test_is_divisible_by_zero_divisor_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(10).is_divisible_by(0)
    assert_that(str(exc_info.value)).is_equal_to("given divisor arg must not be zero")


def test_chaining():
    assert_that(123).is_greater_than(100).is_less_than(1000).is_between(120, 125).is_close_to(100, 25)


def test_chaining_even_odd():
    assert_that(4).is_even().is_positive().is_divisible_by(2)
    assert_that(3).is_odd().is_positive()
