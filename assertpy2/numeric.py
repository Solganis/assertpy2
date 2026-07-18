from __future__ import annotations

import datetime
import math
import numbers
from typing import TYPE_CHECKING

from ._engine._mixin_base import _MixinBase

if TYPE_CHECKING:
    from ._engine._compat import Self

__tracebackhide__ = True


def _fmt_operand(value: object) -> object:
    """Format a relational operand: datetimes as ``%Y-%m-%d %H:%M:%S``, everything else verbatim."""
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def _is_nan(value) -> bool:
    """`math.isnan` guarded so a bignum int/Decimal that overflows float reports False (never NaN)."""
    try:
        return math.isnan(value)
    except OverflowError:
        return False


def _is_inf(value) -> bool:
    """`math.isinf` guarded so a bignum int/Decimal that overflows float reports False (never infinite)."""
    try:
        return math.isinf(value)
    except OverflowError:
        return False


def _fmt_tolerance(tolerance: datetime.timedelta) -> str:
    """Format a timedelta tolerance as ``h:mm:ss``."""
    tolerance_seconds = tolerance.days * 86400 + tolerance.seconds + tolerance.microseconds / 1000000
    hours, remainder = divmod(tolerance_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}"


class NumericMixin(_MixinBase):
    """Numeric assertions mixin."""

    _NUMERIC_COMPAREABLE = frozenset({datetime.datetime, datetime.timedelta, datetime.date, datetime.time})
    _NUMERIC_NON_COMPAREABLE = frozenset({complex})

    def _validate_compareable(self, other):
        self_type = type(self.val)
        other_type = type(other)

        if self_type in self._NUMERIC_NON_COMPAREABLE:
            raise TypeError(f"ordering is not defined for type <{self_type.__name__}>")
        if self_type in self._NUMERIC_COMPAREABLE:
            if other_type is not self_type:
                raise TypeError(f"given arg must be <{self_type.__name__}>, but was <{other_type.__name__}>")
            return
        if isinstance(self.val, numbers.Number):
            if not isinstance(other, numbers.Number):
                raise TypeError(f"given arg must be a number, but was <{other_type.__name__}>")
            return
        try:
            _ = self.val < other
        except TypeError:
            raise TypeError(f"ordering is not defined for type <{self_type.__name__}>") from None

    def _validate_number(self):
        """Raise TypeError if val is not numeric."""
        if not isinstance(self.val, numbers.Number):
            raise TypeError("val is not numeric")

    def _validate_real(self):
        """Raise TypeError if val is not real number."""
        if not isinstance(self.val, numbers.Real):
            raise TypeError("val is not real number")

    def is_zero(self) -> Self:
        """Asserts that val is numeric and is zero.

        Examples:
            Usage:

                assert_that(0).is_zero()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** zero
        """
        self._validate_number()
        return self.is_equal_to(0)

    def is_not_zero(self) -> Self:
        """Asserts that val is numeric and is *not* zero.

        Examples:
            Usage:

                assert_that(1).is_not_zero()
                assert_that(123.4).is_not_zero()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** zero
        """
        self._validate_number()
        return self.is_not_equal_to(0)

    def is_nan(self) -> Self:
        """Asserts that val is real number and is ``NaN`` (not a number).

        Examples:
            Usage:

                assert_that(float('nan')).is_nan()
                assert_that(float('inf') * 0).is_nan()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** NaN
        """
        self._validate_number()
        self._validate_real()
        if not _is_nan(self.val):
            return self.error(f"Expected <{self.val}> to be <NaN>, but was not.")
        return self

    def is_not_nan(self) -> Self:
        """Asserts that val is real number and is *not* ``NaN`` (not a number).

        Examples:
            Usage:

                assert_that(0).is_not_nan()
                assert_that(123.4).is_not_nan()
                assert_that(float('inf')).is_not_nan()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** NaN
        """
        self._validate_number()
        self._validate_real()
        if _is_nan(self.val):
            return self.error("Expected not <NaN>, but was.")
        return self

    def is_inf(self) -> Self:
        """Asserts that val is real number and is ``Inf`` (infinity).

        Examples:
            Usage:

                assert_that(float('inf')).is_inf()
                assert_that(float('inf') * 1).is_inf()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** Inf
        """
        self._validate_number()
        self._validate_real()
        if not _is_inf(self.val):
            return self.error(f"Expected <{self.val}> to be <Inf>, but was not.")
        return self

    def is_not_inf(self) -> Self:
        """Asserts that val is real number and is *not* ``Inf`` (infinity).

        Examples:
            Usage:

                assert_that(0).is_not_inf()
                assert_that(123.4).is_not_inf()
                assert_that(float('nan')).is_not_inf()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** Inf
        """
        self._validate_number()
        self._validate_real()
        if _is_inf(self.val):
            return self.error("Expected not <Inf>, but was.")
        return self

    def is_greater_than(self, other: object) -> Self:
        """Asserts that val is numeric and is greater than other.

        Args:
            other: the other date, expected to be less than val

        Examples:
            Usage:

                assert_that(1).is_greater_than(0)
                assert_that(123.4).is_greater_than(111.1)

            For dates, behavior is identical to [`is_after()`][assertpy2.date.DateMixin.is_after]:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(today).is_greater_than(yesterday)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** greater than other

        Note:
            A ``NaN`` value is unordered, so it **fails** every relational assertion here
            (``is_greater_than``, ``is_less_than``, ``is_between``, ``is_positive``, ...). This diverges
            from the original assertpy, where ``NaN`` silently passes.
        """
        self._validate_compareable(other)
        if not self.val > other:  # positive form so NaN (unordered) fails instead of slipping through
            return self.error(
                f"Expected <{_fmt_operand(self.val)}> to be greater than <{_fmt_operand(other)}>, but was not."
            )
        return self

    def is_greater_than_or_equal_to(self, other: object) -> Self:
        """Asserts that val is numeric and is greater than or equal to other.

        Args:
            other: the other date, expected to be less than or equal to val

        Examples:
            Usage:

                assert_that(1).is_greater_than_or_equal_to(0)
                assert_that(1).is_greater_than_or_equal_to(1)
                assert_that(123.4).is_greater_than_or_equal_to(111.1)

            For dates, behavior is identical to [`is_after()`][assertpy2.date.DateMixin.is_after] *except* when equal:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(today).is_greater_than_or_equal_to(yesterday)
                assert_that(today).is_greater_than_or_equal_to(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** greater than or equal to other
        """
        self._validate_compareable(other)
        if not self.val >= other:  # positive form so NaN (unordered) fails instead of slipping through
            return self.error(
                f"Expected <{_fmt_operand(self.val)}> to be greater than or equal to"
                f" <{_fmt_operand(other)}>, but was not."
            )
        return self

    def is_less_than(self, other: object) -> Self:
        """Asserts that val is numeric and is less than other.

        Args:
            other: the other date, expected to be greater than val

        Examples:
            Usage:

                assert_that(0).is_less_than(1)
                assert_that(123.4).is_less_than(555.5)

            For dates, behavior is identical to [`is_before()`][assertpy2.date.DateMixin.is_before]:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(yesterday).is_less_than(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** less than other

        Note:
            A ``NaN`` value is unordered and **fails** here, diverging from the original assertpy where
            ``NaN`` silently passes relational assertions.
        """
        self._validate_compareable(other)
        if not self.val < other:  # positive form so NaN (unordered) fails instead of slipping through
            return self.error(
                f"Expected <{_fmt_operand(self.val)}> to be less than <{_fmt_operand(other)}>, but was not."
            )
        return self

    def is_less_than_or_equal_to(self, other: object) -> Self:
        """Asserts that val is numeric and is less than or equal to other.

        Args:
            other: the other date, expected to be greater than or equal to val

        Examples:
            Usage:

                assert_that(1).is_less_than_or_equal_to(0)
                assert_that(1).is_less_than_or_equal_to(1)
                assert_that(123.4).is_less_than_or_equal_to(100.0)

            For dates, behavior is identical to [`is_before()`][assertpy2.date.DateMixin.is_before]
            *except* when equal:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(yesterday).is_less_than_or_equal_to(today)
                assert_that(today).is_less_than_or_equal_to(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** less than or equal to other
        """
        self._validate_compareable(other)
        if not self.val <= other:  # positive form so NaN (unordered) fails instead of slipping through
            return self.error(
                f"Expected <{_fmt_operand(self.val)}> to be less than or equal to <{_fmt_operand(other)}>, but was not."
            )
        return self

    def is_positive(self) -> Self:
        """Asserts that val is numeric and is greater than zero.

        Examples:
            Usage:

                assert_that(1).is_positive()
                assert_that(123.4).is_positive()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** positive

        Note:
            ``NaN`` is not positive, so this **fails** for ``float("nan")``. This diverges from the
            original assertpy, where ``NaN`` silently passes relational assertions.
        """
        return self.is_greater_than(0)

    def is_negative(self) -> Self:
        """Asserts that val is numeric and is less than zero.

        Examples:
            Usage:

                assert_that(-1).is_negative()
                assert_that(-123.4).is_negative()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** negative

        Note:
            ``NaN`` is not negative, so this **fails** for ``float("nan")``. This diverges from the
            original assertpy, where ``NaN`` silently passes relational assertions.
        """
        return self.is_less_than(0)

    def is_between(self, low: object, high: object) -> Self:
        """Asserts that val is numeric and is between low and high.

        Args:
            low: the low value
            high: the high value

        Examples:
            Usage:

                assert_that(1).is_between(0, 2)
                assert_that(123.4).is_between(111.1, 222.2)

            For dates, works as expected:

                import datetime

                today = datetime.datetime.now()
                middle = today - datetime.timedelta(hours=12)
                yesterday = today - datetime.timedelta(days=1)

                assert_that(middle).is_between(yesterday, today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** between low and high

        Note:
            ``NaN`` is not within any range, so this **fails** for ``float("nan")``. This diverges from
            the original assertpy, where ``NaN`` silently passes relational assertions.
        """
        val_type = type(self.val)
        self._validate_between_args(val_type, low, high)

        if not low <= self.val <= high:  # positive form so NaN (unordered) fails instead of passing
            return self.error(
                f"Expected <{_fmt_operand(self.val)}> to be between"
                f" <{_fmt_operand(low)}> and <{_fmt_operand(high)}>, but was not."
            )
        return self

    def is_not_between(self, low: object, high: object) -> Self:
        """Asserts that val is numeric and is *not* between low and high.

        Args:
            low: the low value
            high: the high value

        Examples:
            Usage:

                assert_that(1).is_not_between(2, 3)
                assert_that(1.1).is_not_between(2.2, 3.3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** between low and high
        """
        val_type = type(self.val)
        self._validate_between_args(val_type, low, high)

        if low <= self.val <= high:
            return self.error(
                f"Expected <{_fmt_operand(self.val)}> to not be between"
                f" <{_fmt_operand(low)}> and <{_fmt_operand(high)}>, but was."
            )
        return self

    def _validate_int(self):
        if isinstance(self.val, bool) or not isinstance(self.val, int):
            raise TypeError(f"val is not an integer, got {type(self.val).__name__}")

    def is_even(self) -> Self:
        """Asserts that val is an integer and is even.

        Examples:
            Usage:

                assert_that(0).is_even()
                assert_that(2).is_even()
                assert_that(-4).is_even()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** even
        """
        self._validate_int()
        if self.val % 2 != 0:
            return self.error(f"Expected <{self.val}> to be even, but was not.")
        return self

    def is_odd(self) -> Self:
        """Asserts that val is an integer and is odd.

        Examples:
            Usage:

                assert_that(1).is_odd()
                assert_that(3).is_odd()
                assert_that(-5).is_odd()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** odd
        """
        self._validate_int()
        if self.val % 2 == 0:
            return self.error(f"Expected <{self.val}> to be odd, but was not.")
        return self

    def is_divisible_by(self, divisor: int) -> Self:
        """Asserts that val is an integer and is divisible by divisor.

        Args:
            divisor: the divisor to check against (must be a non-zero integer)

        Examples:
            Usage:

                assert_that(10).is_divisible_by(5)
                assert_that(12).is_divisible_by(3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** divisible by divisor
        """
        self._validate_int()
        if isinstance(divisor, bool) or not isinstance(divisor, int):
            raise TypeError(f"given divisor arg must be an integer, got {type(divisor).__name__}")
        if divisor == 0:
            raise ValueError("given divisor arg must not be zero")
        if self.val % divisor != 0:
            return self.error(f"Expected <{self.val}> to be divisible by <{divisor}>, but was not.")
        return self

    def is_close_to(self, other, tolerance) -> Self:
        """Asserts that val is numeric and is close to other within tolerance.

        Args:
            other (object): the other value, expected to be close to val within tolerance
            tolerance (object): the tolerance

        Examples:
            Usage:

                assert_that(123).is_close_to(100, 25)
                assert_that(123.4).is_close_to(123, 0.5)

            For dates, works as expected:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(today).is_close_to(yesterday, datetime.timedelta(hours=36))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** close to other within tolerance
        """
        self._validate_close_to_args(self.val, other, tolerance)

        if not isinstance(self.val, datetime.datetime) and (_is_nan(self.val) or _is_nan(other)):
            return self.error(
                f"Expected <{self.val}> to be close to <{other}> within tolerance <{tolerance}>, but was not."
            )
        if self.val < (other - tolerance) or self.val > (other + tolerance):
            if isinstance(self.val, datetime.datetime):
                return self.error(
                    f"Expected <{_fmt_operand(self.val)}> to be close to"
                    f" <{_fmt_operand(other)}> within tolerance"
                    f" <{_fmt_tolerance(tolerance)}>, but was not."
                )
            else:
                return self.error(
                    f"Expected <{self.val}> to be close to <{other}> within tolerance <{tolerance}>, but was not."
                )
        return self

    def is_not_close_to(self, other, tolerance) -> Self:
        """Asserts that val is numeric and is *not* close to other within tolerance.

        Args:
            other (object): the other value
            tolerance (object): the tolerance

        Examples:
            Usage:

                assert_that(123).is_not_close_to(100, 22)
                assert_that(123.4).is_not_close_to(123, 0.1)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** close to other within tolerance
        """
        self._validate_close_to_args(self.val, other, tolerance)

        if (other - tolerance) <= self.val <= (other + tolerance):
            if isinstance(self.val, datetime.datetime):
                return self.error(
                    f"Expected <{_fmt_operand(self.val)}> to not be close to"
                    f" <{_fmt_operand(other)}> within tolerance"
                    f" <{_fmt_tolerance(tolerance)}>, but was."
                )
            else:
                return self.error(
                    f"Expected <{self.val}> to not be close to <{other}> within tolerance <{tolerance}>, but was."
                )
        return self
