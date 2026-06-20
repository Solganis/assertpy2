from __future__ import annotations

import collections.abc
import re
from typing import TYPE_CHECKING

from ._mixin_base import _MixinBase

if TYPE_CHECKING:
    from ._compat import Self

__tracebackhide__ = True


class StringMixin(_MixinBase):
    """String assertions mixin."""

    def is_equal_to_ignoring_case(self, other) -> Self:
        """Asserts that val is a string and is case-insensitive equal to other.

        Checks actual is equal to expected using the ``==`` operator and ``str.lower()``.

        Args:
            other: the expected value

        Examples:
            Usage::

                assert_that('foo').is_equal_to_ignoring_case('FOO')
                assert_that('FOO').is_equal_to_ignoring_case('foo')
                assert_that('fOo').is_equal_to_ignoring_case('FoO')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual is **not** case-insensitive equal to expected
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if not isinstance(other, str):
            raise TypeError("given arg must be a string")
        if self.val.lower() != other.lower():
            return self.error(f"Expected <{self.val}> to be case-insensitive equal to <{other}>, but was not.")
        return self

    def contains_ignoring_case(self, *items) -> Self:
        """Asserts that val is string and contains the given item or items.

        Walks val and checks for item or items using the ``==`` operator and ``str.lower()``.

        Args:
            *items: the item or items expected to be contained

        Examples:
            Usage::

                assert_that('foo').contains_ignoring_case('F', 'oO')
                assert_that(['a', 'B']).contains_ignoring_case('A', 'b')
                assert_that({'a': 1, 'B': 2}).contains_ignoring_case('A', 'b')
                assert_that({'a', 'B'}).contains_ignoring_case('A', 'b')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain the case-insensitive item or items
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        if isinstance(self.val, str):
            if len(items) == 1:
                if not isinstance(items[0], str):
                    raise TypeError("given arg must be a string")
                if items[0].lower() not in self.val.lower():
                    return self.error(
                        f"Expected <{self.val}> to case-insensitive contain item <{items[0]}>, but did not."
                    )
            else:
                missing = []
                for item in items:
                    if not isinstance(item, str):
                        raise TypeError("given args must all be strings")
                    if item.lower() not in self.val.lower():
                        missing.append(item)
                if missing:
                    return self.error(
                        f"Expected <{self.val}> to case-insensitive contain items"
                        f" {self._fmt_items(items)}, but did not contain {self._fmt_items(missing)}."
                    )
        elif isinstance(self.val, collections.abc.Iterable):
            missing = []
            for item in items:
                if not isinstance(item, str):
                    raise TypeError("given args must all be strings")
                found = False
                for value in self.val:
                    if not isinstance(value, str):
                        raise TypeError("val items must all be strings")
                    if item.lower() == value.lower():
                        found = True
                        break
                if not found:
                    missing.append(item)
            if missing:
                return self.error(
                    f"Expected <{self.val}> to case-insensitive contain items"
                    f" {self._fmt_items(items)}, but did not contain {self._fmt_items(missing)}."
                )
        else:
            raise TypeError("val is not a string or iterable")
        return self

    def starts_with(self, prefix) -> Self:
        """Asserts that val is string or iterable and starts with prefix.

        Args:
            prefix: the prefix

        Examples:
            Usage::

                assert_that('foo').starts_with('fo')
                assert_that(['a', 'b', 'c']).starts_with('a')
                assert_that((1, 2, 3)).starts_with(1)
                assert_that(((1, 2), (3, 4), (5, 6))).starts_with((1, 2))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** start with prefix
        """
        if prefix is None:
            raise TypeError("given prefix arg must not be none")
        if isinstance(self.val, str):
            if not isinstance(prefix, str):
                raise TypeError("given prefix arg must be a string")
            if len(prefix) == 0:
                raise ValueError("given prefix arg must not be empty")
            if not self.val.startswith(prefix):
                return self.error(f"Expected <{self.val}> to start with <{prefix}>, but did not.")
        elif isinstance(self.val, collections.abc.Iterable):
            if len(self.val) == 0:
                raise ValueError("val must not be empty")
            first = next(iter(self.val))
            if first != prefix:
                return self.error(f"Expected {self.val} to start with <{prefix}>, but did not.")
        else:
            raise TypeError("val is not a string or iterable")
        return self

    def ends_with(self, suffix) -> Self:
        """Asserts that val is string or iterable and ends with suffix.

        Args:
            suffix: the suffix

        Examples:
            Usage::

                assert_that('foo').ends_with('oo')
                assert_that(['a', 'b', 'c']).ends_with('c')
                assert_that((1, 2, 3)).ends_with(3)
                assert_that(((1, 2), (3, 4), (5, 6))).ends_with((5, 6))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** end with suffix
        """
        if suffix is None:
            raise TypeError("given suffix arg must not be none")
        if isinstance(self.val, str):
            if not isinstance(suffix, str):
                raise TypeError("given suffix arg must be a string")
            if len(suffix) == 0:
                raise ValueError("given suffix arg must not be empty")
            if not self.val.endswith(suffix):
                return self.error(f"Expected <{self.val}> to end with <{suffix}>, but did not.")
        elif isinstance(self.val, collections.abc.Iterable):
            if len(self.val) == 0:
                raise ValueError("val must not be empty")
            items = list(self.val)
            if items[-1] != suffix:
                return self.error(f"Expected {self.val} to end with <{suffix}>, but did not.")
        else:
            raise TypeError("val is not a string or iterable")
        return self

    def matches(self, pattern) -> Self:
        """Asserts that val is string and matches the given regex pattern.

        Args:
            pattern (str): the regular expression pattern, as raw string (aka prefixed with ``r``)

        Examples:
            Usage::

                assert_that('foo').matches(r'\\w')
                assert_that('123-456-7890').matches(r'\\d{3}-\\d{3}-\\d{4}')

            Match is partial unless anchored, so these assertion pass::

                assert_that('foo').matches(r'\\w')
                assert_that('foo').matches(r'oo')
                assert_that('foo').matches(r'\\w{2}')

            To match the entire string, just use an anchored regex pattern where ``^`` and ``$``
            match the start and end of line and ``\\A`` and ``\\Z`` match the start and end of string::

                assert_that('foo').matches(r'^\\w{3}$')
                assert_that('foo').matches(r'\\A\\w{3}\\Z')

            And regex flags, such as ``re.MULTILINE`` and ``re.DOTALL``, can only be applied via
            *inline modifiers*, such as ``(?m)`` and ``(?s)``::

                s = '''bar
                foo
                baz'''

                # using multiline (?m)
                assert_that(s).matches(r'(?m)^foo$')

                # using dotall (?s)
                assert_that(s).matches(r'(?s)b(.*)z')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** match pattern

        Tip:
            Regular expressions are tricky.  Be sure to use raw strings (aka prefixed with ``r``).
            Also, note that the :meth:`matches` assertion passes for partial matches (as does the
            underlying ``re.match`` method).  So, if you need to match the entire string, you must
            include anchors in the regex pattern.
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if not isinstance(pattern, str):
            raise TypeError("given pattern arg must be a string")
        if len(pattern) == 0:
            raise ValueError("given pattern arg must not be empty")
        if re.search(pattern, self.val) is None:
            return self.error(f"Expected <{self.val}> to match pattern <{pattern}>, but did not.")
        return self

    def does_not_match(self, pattern) -> Self:
        """Asserts that val is string and does not match the given regex pattern.

        Args:
            pattern (str): the regular expression pattern, as raw string (aka prefixed with ``r``)

        Examples:
            Usage::

                assert_that('foo').does_not_match(r'\\d+')
                assert_that('123').does_not_match(r'\\w+')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** match pattern

        See Also:
            :meth:`matches` - for more about regex patterns
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if not isinstance(pattern, str):
            raise TypeError("given pattern arg must be a string")
        if len(pattern) == 0:
            raise ValueError("given pattern arg must not be empty")
        if re.search(pattern, self.val) is not None:
            return self.error(f"Expected <{self.val}> to not match pattern <{pattern}>, but did.")
        return self

    def is_alpha(self) -> Self:
        """Asserts that val is non-empty string and all characters are alphabetic (using ``str.isalpha()``).

        Examples:
            Usage::

                assert_that('foo').is_alpha()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** alphabetic
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if len(self.val) == 0:
            raise ValueError("val is empty")
        if not self.val.isalpha():
            return self.error(f"Expected <{self.val}> to contain only alphabetic chars, but did not.")
        return self

    def is_digit(self) -> Self:
        """Asserts that val is non-empty string and all characters are digits (using ``str.isdigit()``).

        Examples:
            Usage::

                assert_that('1234567890').is_digit()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** digits
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if len(self.val) == 0:
            raise ValueError("val is empty")
        if not self.val.isdigit():
            return self.error(f"Expected <{self.val}> to contain only digits, but did not.")
        return self

    def is_lower(self) -> Self:
        """Asserts that val is non-empty string and all characters are lowercase (using ``str.lower()``).

        Examples:
            Usage::

                assert_that('foo').is_lower()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** lowercase
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if len(self.val) == 0:
            raise ValueError("val is empty")
        if self.val != self.val.lower():
            return self.error(f"Expected <{self.val}> to contain only lowercase chars, but did not.")
        return self

    def is_upper(self) -> Self:
        """Asserts that val is non-empty string and all characters are uppercase (using ``str.upper()``).

        Examples:
            Usage::

                assert_that('FOO').is_upper()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** uppercase
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if len(self.val) == 0:
            raise ValueError("val is empty")
        if self.val != self.val.upper():
            return self.error(f"Expected <{self.val}> to contain only uppercase chars, but did not.")
        return self

    def is_alphanumeric(self) -> Self:
        """Asserts that val is non-empty string and all characters are alphanumeric (using ``str.isalnum()``).

        Examples:
            Usage::

                assert_that('abc123').is_alphanumeric()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** alphanumeric
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if len(self.val) == 0:
            raise ValueError("val is empty")
        if not self.val.isalnum():
            return self.error(f"Expected <{self.val}> to contain only alphanumeric chars, but did not.")
        return self

    def is_whitespace(self) -> Self:
        """Asserts that val is non-empty string and all characters are whitespace (using ``str.isspace()``).

        Examples:
            Usage::

                assert_that('  ').is_whitespace()
                assert_that('\\t\\n').is_whitespace()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** whitespace
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if len(self.val) == 0:
            raise ValueError("val is empty")
        if not self.val.isspace():
            return self.error(f"Expected <{self.val}> to contain only whitespace, but did not.")
        return self

    def contains_any_of(self, *items) -> Self:
        """Asserts that val is a string and contains at least one of the given items.

        Args:
            *items: the items, at least one of which is expected to be contained

        Examples:
            Usage::

                assert_that('foobar').contains_any_of('foo', 'xxx')
                assert_that('foobar').contains_any_of('xxx', 'bar')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain any of the items
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        for item in items:
            if not isinstance(item, str):
                raise TypeError("given args must all be strings")
        if not any(item in self.val for item in items):
            return self.error(f"Expected <{self.val}> to contain any of {self._fmt_items(items)}, but did not.")
        return self

    def contains_none_of(self, *items) -> Self:
        """Asserts that val is a string and contains none of the given items.

        Args:
            *items: the items, none of which should be contained

        Examples:
            Usage::

                assert_that('foobar').contains_none_of('xxx', 'yyy')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** contain any of the items
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        for item in items:
            if not isinstance(item, str):
                raise TypeError("given args must all be strings")
        found = [item for item in items if item in self.val]
        if found:
            return self.error(
                f"Expected <{self.val}> to contain none of {self._fmt_items(items)},"
                f" but did contain {self._fmt_items(found)}."
            )
        return self

    def is_unicode(self) -> Self:
        """Asserts that val is a unicode string.

        Examples:
            Usage::

                assert_that(u'foo').is_unicode()  # python 2
                assert_that('foo').is_unicode()   # python 3

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** a unicode string
        """
        if not isinstance(self.val, str):
            return self.error(f"Expected <{self.val}> to be unicode, but was <{type(self.val).__name__}>.")
        return self

    def extracting_group(self, pattern: str, group: int | str = 0) -> Self:
        """Search val for ``pattern`` and return a new builder whose val is the captured group.

        Args:
            pattern: the regular expression pattern (must contain at least one group)
            group: the group index (int) or name (str) to extract. Defaults to ``0``
                (the entire match).

        Examples:
            Usage with positional groups::

                assert_that("status=200 path=/api").extracting_group(r"status=(\\d+)", 1).is_equal_to("200")

            Usage with named groups::

                assert_that("2024-01-15 ERROR").extracting_group(
                    r"(?P<level>\\w+)$", "level"
                ).is_equal_to("ERROR")

        Returns:
            AssertionBuilder: a **new** builder whose val is the extracted group string

        Raises:
            TypeError: if val is not a string or pattern is not a string
            ValueError: if pattern is empty
            AssertionError: if the pattern does not match val or the group does not exist
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if not isinstance(pattern, str):
            raise TypeError("given pattern arg must be a string")
        if len(pattern) == 0:
            raise ValueError("given pattern arg must not be empty")
        match_obj = re.search(pattern, self.val)
        if match_obj is None:
            return self.error(f"Expected <{self.val}> to match pattern <{pattern}>, but did not.")
        try:
            extracted = match_obj.group(group)
        except IndexError:
            return self.error(f"Expected pattern <{pattern}> to have group <{group}>, but it does not.")
        if extracted is None:
            return self.error(
                f"Expected group <{group}> of pattern <{pattern}> to be matched in <{self.val}>, but it was not."
            )
        return self.builder(extracted, self.description, self.kind)

    def matches_with_groups(self, pattern: str) -> Self:
        """Search val for ``pattern`` and return a new builder whose val is the tuple of all groups.

        If the pattern contains **named** groups, the builder val is a ``dict``
        of ``{name: value}`` for all named groups.  Otherwise it is the
        ``tuple`` returned by ``Match.groups()``.

        Args:
            pattern: the regular expression pattern with one or more groups

        Examples:
            Positional groups::

                assert_that("2024-01-15 ERROR").matches_with_groups(
                    r"(\\d{4}-\\d{2}-\\d{2}) (\\w+)"
                ).is_length(2)

            Named groups::

                assert_that("status=200").matches_with_groups(
                    r"(?P<key>\\w+)=(?P<val>\\w+)"
                ).contains_key("key").contains_key("val")

        Returns:
            AssertionBuilder: a **new** builder whose val is the groups tuple or groupdict

        Raises:
            TypeError: if val is not a string or pattern is not a string
            ValueError: if pattern is empty
            AssertionError: if the pattern does not match val
        """
        if not isinstance(self.val, str):
            raise TypeError("val is not a string")
        if not isinstance(pattern, str):
            raise TypeError("given pattern arg must be a string")
        if len(pattern) == 0:
            raise ValueError("given pattern arg must not be empty")
        match_obj = re.search(pattern, self.val)
        if match_obj is None:
            return self.error(f"Expected <{self.val}> to match pattern <{pattern}>, but did not.")
        groupdict = match_obj.groupdict()
        result = groupdict if groupdict else match_obj.groups()
        return self.builder(result, self.description, self.kind)
