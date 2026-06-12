# Copyright (c) 2015-2019, Activision Publishing, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from __future__ import annotations

import datetime
import math
import numbers
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing_extensions import Self

__tracebackhide__ = True


class NumericMixin:
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
        if isinstance(self.val, numbers.Number) is False:
            raise TypeError("val is not numeric")

    def _validate_real(self):
        """Raise TypeError if val is not real number."""
        if isinstance(self.val, numbers.Real) is False:
            raise TypeError("val is not real number")

    def is_zero(self) -> Self:
        """Asserts that val is numeric and is zero.

        Examples:
            Usage::

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
            Usage::

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
            Usage::

                assert_that(float('nan')).is_nan()
                assert_that(float('inf') * 0).is_nan()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** NaN
        """
        self._validate_number()
        self._validate_real()
        if not math.isnan(self.val):
            return self.error(f"Expected <{self.val}> to be <NaN>, but was not.")
        return self

    def is_not_nan(self) -> Self:
        """Asserts that val is real number and is *not* ``NaN`` (not a number).

        Examples:
            Usage::

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
        if math.isnan(self.val):
            return self.error("Expected not <NaN>, but was.")
        return self

    def is_inf(self) -> Self:
        """Asserts that val is real number and is ``Inf`` (infinity).

        Examples:
            Usage::

                assert_that(float('inf')).is_inf()
                assert_that(float('inf') * 1).is_inf()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** Inf
        """
        self._validate_number()
        self._validate_real()
        if not math.isinf(self.val):
            return self.error(f"Expected <{self.val}> to be <Inf>, but was not.")
        return self

    def is_not_inf(self) -> Self:
        """Asserts that val is real number and is *not* ``Inf`` (infinity).

        Examples:
            Usage::

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
        if math.isinf(self.val):
            return self.error("Expected not <Inf>, but was.")
        return self

    def is_greater_than(self, other) -> Self:
        """Asserts that val is numeric and is greater than other.

        Args:
            other: the other date, expected to be less than val

        Examples:
            Usage::

                assert_that(1).is_greater_than(0)
                assert_that(123.4).is_greater_than(111.1)

            For dates, behavior is identical to :meth:`~assertpy.date.DateMixin.is_after`::

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(today).is_greater_than(yesterday)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** greater than other
        """
        self._validate_compareable(other)
        if self.val <= other:
            if type(self.val) is datetime.datetime:
                return self.error(
                    f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to be greater than"
                    f" <{other.strftime('%Y-%m-%d %H:%M:%S')}>, but was not."
                )
            else:
                return self.error(f"Expected <{self.val}> to be greater than <{other}>, but was not.")
        return self

    def is_greater_than_or_equal_to(self, other) -> Self:
        """Asserts that val is numeric and is greater than or equal to other.

        Args:
            other: the other date, expected to be less than or equal to val

        Examples:
            Usage::

                assert_that(1).is_greater_than_or_equal_to(0)
                assert_that(1).is_greater_than_or_equal_to(1)
                assert_that(123.4).is_greater_than_or_equal_to(111.1)

            For dates, behavior is identical to :meth:`~assertpy.date.DateMixin.is_after` *except* when equal::

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
        if self.val < other:
            if type(self.val) is datetime.datetime:
                return self.error(
                    f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to be greater than or equal to"
                    f" <{other.strftime('%Y-%m-%d %H:%M:%S')}>, but was not."
                )
            else:
                return self.error(f"Expected <{self.val}> to be greater than or equal to <{other}>, but was not.")
        return self

    def is_less_than(self, other) -> Self:
        """Asserts that val is numeric and is less than other.

        Args:
            other: the other date, expected to be greater than val

        Examples:
            Usage::

                assert_that(0).is_less_than(1)
                assert_that(123.4).is_less_than(555.5)

            For dates, behavior is identical to :meth:`~assertpy.date.DateMixin.is_before`::

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(yesterday).is_less_than(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** less than other
        """
        self._validate_compareable(other)
        if self.val >= other:
            if type(self.val) is datetime.datetime:
                return self.error(
                    f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to be less than"
                    f" <{other.strftime('%Y-%m-%d %H:%M:%S')}>, but was not."
                )
            else:
                return self.error(f"Expected <{self.val}> to be less than <{other}>, but was not.")
        return self

    def is_less_than_or_equal_to(self, other) -> Self:
        """Asserts that val is numeric and is less than or equal to other.

        Args:
            other: the other date, expected to be greater than or equal to val

        Examples:
            Usage::

                assert_that(1).is_less_than_or_equal_to(0)
                assert_that(1).is_less_than_or_equal_to(1)
                assert_that(123.4).is_less_than_or_equal_to(100.0)

            For dates, behavior is identical to :meth:`~assertpy.date.DateMixin.is_before` *except* when equal::

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
        if self.val > other:
            if type(self.val) is datetime.datetime:
                return self.error(
                    f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to be less than or equal to"
                    f" <{other.strftime('%Y-%m-%d %H:%M:%S')}>, but was not."
                )
            else:
                return self.error(f"Expected <{self.val}> to be less than or equal to <{other}>, but was not.")
        return self

    def is_positive(self) -> Self:
        """Asserts that val is numeric and is greater than zero.

        Examples:
            Usage::

                assert_that(1).is_positive()
                assert_that(123.4).is_positive()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** positive
        """
        return self.is_greater_than(0)

    def is_negative(self) -> Self:
        """Asserts that val is numeric and is less than zero.

        Examples:
            Usage::

                assert_that(-1).is_negative()
                assert_that(-123.4).is_negative()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** negative
        """
        return self.is_less_than(0)

    def is_between(self, low, high) -> Self:
        """Asserts that val is numeric and is between low and high.

        Args:
            low: the low value
            high: the high value

        Examples:
            Usage::

                assert_that(1).is_between(0, 2)
                assert_that(123.4).is_between(111.1, 222.2)

            For dates, works as expected::

                import datetime

                today = datetime.datetime.now()
                middle = today - datetime.timedelta(hours=12)
                yesterday = today - datetime.timedelta(days=1)

                assert_that(middle).is_between(yesterday, today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** between low and high
        """
        val_type = type(self.val)
        self._validate_between_args(val_type, low, high)

        if self.val < low or self.val > high:
            if val_type is datetime.datetime:
                return self.error(
                    f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to be between"
                    f" <{low.strftime('%Y-%m-%d %H:%M:%S')}> and <{high.strftime('%Y-%m-%d %H:%M:%S')}>, but was not."
                )
            else:
                return self.error(f"Expected <{self.val}> to be between <{low}> and <{high}>, but was not.")
        return self

    def is_not_between(self, low, high) -> Self:
        """Asserts that val is numeric and is *not* between low and high.

        Args:
            low: the low value
            high: the high value

        Examples:
            Usage::

                assert_that(1).is_not_between(2, 3)
                assert_that(1.1).is_not_between(2.2, 3.3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** between low and high
        """
        val_type = type(self.val)
        self._validate_between_args(val_type, low, high)

        if self.val >= low and self.val <= high:
            if val_type is datetime.datetime:
                return self.error(
                    f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to not be between"
                    f" <{low.strftime('%Y-%m-%d %H:%M:%S')}> and <{high.strftime('%Y-%m-%d %H:%M:%S')}>, but was."
                )
            else:
                return self.error(f"Expected <{self.val}> to not be between <{low}> and <{high}>, but was.")
        return self

    def _validate_int(self):
        if isinstance(self.val, bool) or not isinstance(self.val, int):
            raise TypeError(f"val is not an integer, got {type(self.val).__name__}")

    def is_even(self) -> Self:
        """Asserts that val is an integer and is even.

        Examples:
            Usage::

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
            Usage::

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

    def is_divisible_by(self, divisor) -> Self:
        """Asserts that val is an integer and is divisible by divisor.

        Args:
            divisor: the divisor to check against (must be a non-zero integer)

        Examples:
            Usage::

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
            other: the other value, expected to be close to val within tolerance
            tolerance: the tolerance

        Examples:
            Usage::

                assert_that(123).is_close_to(100, 25)
                assert_that(123.4).is_close_to(123, 0.5)

            For dates, works as expected::

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

        if type(self.val) is not datetime.datetime and (math.isnan(self.val) or math.isnan(other)):
            return self.error(
                f"Expected <{self.val}> to be close to <{other}> within tolerance <{tolerance}>, but was not."
            )
        if self.val < (other - tolerance) or self.val > (other + tolerance):
            if type(self.val) is datetime.datetime:
                tolerance_seconds = tolerance.days * 86400 + tolerance.seconds + tolerance.microseconds / 1000000
                h, rem = divmod(tolerance_seconds, 3600)
                m, s = divmod(rem, 60)
                return self.error(
                    f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to be close to"
                    f" <{other.strftime('%Y-%m-%d %H:%M:%S')}> within tolerance"
                    f" <{int(h)}:{int(m):02d}:{int(s):02d}>, but was not."
                )
            else:
                return self.error(
                    f"Expected <{self.val}> to be close to <{other}> within tolerance <{tolerance}>, but was not."
                )
        return self

    def is_not_close_to(self, other, tolerance) -> Self:
        """Asserts that val is numeric and is *not* close to other within tolerance.

        Args:
            other: the other value
            tolerance: the tolerance

        Examples:
            Usage::

                assert_that(123).is_not_close_to(100, 22)
                assert_that(123.4).is_not_close_to(123, 0.1)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** close to other within tolerance
        """
        self._validate_close_to_args(self.val, other, tolerance)

        if self.val >= (other - tolerance) and self.val <= (other + tolerance):
            if type(self.val) is datetime.datetime:
                tolerance_seconds = tolerance.days * 86400 + tolerance.seconds + tolerance.microseconds / 1000000
                h, rem = divmod(tolerance_seconds, 3600)
                m, s = divmod(rem, 60)
                return self.error(
                    f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to not be close to"
                    f" <{other.strftime('%Y-%m-%d %H:%M:%S')}> within tolerance"
                    f" <{int(h)}:{int(m):02d}:{int(s):02d}>, but was."
                )
            else:
                return self.error(
                    f"Expected <{self.val}> to not be close to <{other}> within tolerance <{tolerance}>, but was."
                )
        return self
