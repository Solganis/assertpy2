from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from ._mixin_base import _MixinBase

if TYPE_CHECKING:
    from ._compat import Self

__tracebackhide__ = True


def _require_datetime(value: object, label: str) -> None:
    """Raise ``TypeError`` unless *value* is exactly a :class:`datetime.datetime`."""
    if not isinstance(value, datetime.datetime):
        raise TypeError(f"{label} must be datetime, but was type <{type(value).__name__}>")


class DateMixin(_MixinBase):
    """Date and time assertions mixin."""

    def is_before(self, other) -> Self:
        """Asserts that val is a date and is before other date.

        Args:
            other: the other date, expected to be after val

        Examples:
            Usage::

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(yesterday).is_before(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** before the given date

        See Also:
            :meth:`~assertpy.numeric.NumericMixin.is_less_than` - numeric assertion, but also works with datetime
            :meth:`~assertpy.numeric.NumericMixin.is_less_than_or_equal_to` - also works with datetime
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, "given arg")
        if self.val >= other:
            return self.error(
                f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to be before"
                f" <{other.strftime('%Y-%m-%d %H:%M:%S')}>, but was not."
            )
        return self

    def is_after(self, other) -> Self:
        """Asserts that val is a date and is after other date.

        Args:
            other: the other date, expected to be before val

        Examples:
            Usage::

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(today).is_after(yesterday)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** after the given date

        See Also:
            :meth:`~assertpy.numeric.NumericMixin.is_greater_than` - numeric assertion, but also works with datetime
            :meth:`~assertpy.numeric.NumericMixin.is_greater_than_or_equal_to` - also works with datetime
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, "given arg")
        if self.val <= other:
            return self.error(
                f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to be after"
                f" <{other.strftime('%Y-%m-%d %H:%M:%S')}>, but was not."
            )
        return self

    def is_before_or_equal_to(self, other) -> Self:
        """Asserts that val is a date and is before or equal to other date.

        Args:
            other: the other date, expected to be after or equal to val

        Examples:
            Usage::

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(yesterday).is_before_or_equal_to(today)
                assert_that(today).is_before_or_equal_to(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** before or equal to the given date
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, "given arg")
        if self.val > other:
            return self.error(
                f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to be before or equal to"
                f" <{other.strftime('%Y-%m-%d %H:%M:%S')}>, but was not."
            )
        return self

    def is_after_or_equal_to(self, other) -> Self:
        """Asserts that val is a date and is after or equal to other date.

        Args:
            other: the other date, expected to be before or equal to val

        Examples:
            Usage::

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(today).is_after_or_equal_to(yesterday)
                assert_that(today).is_after_or_equal_to(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** after or equal to the given date
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, "given arg")
        if self.val < other:
            return self.error(
                f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to be after or equal to"
                f" <{other.strftime('%Y-%m-%d %H:%M:%S')}>, but was not."
            )
        return self

    def is_equal_to_ignoring_milliseconds(self, other) -> Self:
        """Asserts that val is a date and is equal to other date to the second.

        Args:
            other: the other date, expected to be equal to the second

        Examples:
            Usage::

                import datetime

                d1 = datetime.datetime(2020, 1, 2, 3, 4, 5, 6)       # 2020-01-02 03:04:05.000006
                d2 = datetime.datetime(2020, 1, 2, 3, 4, 5, 777777)  # 2020-01-02 03:04:05.777777

                assert_that(d1).is_equal_to_ignoring_milliseconds(d2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** equal to the given date to the second
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, "given arg")
        if (
            self.val.date() != other.date()
            or self.val.hour != other.hour
            or self.val.minute != other.minute
            or self.val.second != other.second
        ):
            return self.error(
                f"Expected <{self.val.strftime('%Y-%m-%d %H:%M:%S')}> to be equal to"
                f" <{other.strftime('%Y-%m-%d %H:%M:%S')}>, but was not."
            )
        return self

    def is_equal_to_ignoring_seconds(self, other) -> Self:
        """Asserts that val is a date and is equal to other date to the minute.

        Args:
            other: the other date, expected to be equal to the minute

        Examples:
            Usage::

                import datetime

                d1 = datetime.datetime(2020, 1, 2, 3, 4, 5)   # 2020-01-02 03:04:05
                d2 = datetime.datetime(2020, 1, 2, 3, 4, 55)  # 2020-01-02 03:04:55

                assert_that(d1).is_equal_to_ignoring_seconds(d2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** equal to the given date to the minute
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, "given arg")
        if self.val.date() != other.date() or self.val.hour != other.hour or self.val.minute != other.minute:
            return self.error(
                f"Expected <{self.val.strftime('%Y-%m-%d %H:%M')}> to be equal to"
                f" <{other.strftime('%Y-%m-%d %H:%M')}>, but was not."
            )
        return self

    def is_equal_to_ignoring_time(self, other) -> Self:
        """Asserts that val is a date and is equal to other date ignoring time.

        Args:
            other: the other date, expected to be equal ignoring time

        Examples:
            Usage::

                import datetime

                d1 = datetime.datetime(2020, 1, 2, 3, 4, 5)     # 2020-01-02 03:04:05
                d2 = datetime.datetime(2020, 1, 2, 13, 44, 55)  # 2020-01-02 13:44:55

                assert_that(d1).is_equal_to_ignoring_time(d2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** equal to the given date ignoring time
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, "given arg")
        if self.val.date() != other.date():
            return self.error(
                f"Expected <{self.val.strftime('%Y-%m-%d')}> to be equal to"
                f" <{other.strftime('%Y-%m-%d')}>, but was not."
            )
        return self
