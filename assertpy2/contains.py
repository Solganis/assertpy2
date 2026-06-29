from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from ._mixin_base import _MixinBase
from .errors import DiffEntry, DiffResult
from .matchers import Matcher

if TYPE_CHECKING:
    from ._compat import Self

__tracebackhide__ = True


class ContainsMixin(_MixinBase):
    """Containment assertions mixin."""

    def contains(self, *items) -> Self:
        """Asserts that val contains the given item or items.

        Checks if the collection contains the given item or items using ``in`` operator.

        Args:
            *items: the item or items expected to be contained

        Examples:
            Usage::

                assert_that('foo').contains('f')
                assert_that('foo').contains('f', 'oo')
                assert_that(['a', 'b']).contains('b', 'a')
                assert_that((1, 2, 3)).contains(3, 2, 1)
                assert_that({'a': 1, 'b': 2}).contains('b', 'a')  # checks keys
                assert_that({'a', 'b'}).contains('b', 'a')
                assert_that([1, 2, 3]).is_type_of(list).contains(1, 2).does_not_contain(4, 5)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain the item or items

        Tip:
            Use the :meth:`~assertpy2.dict.DictMixin.contains_key` alias when working with
            *dict-like* objects to be self-documenting.

        See Also:
            :meth:`~assertpy2.string.StringMixin.contains_ignoring_case` - for case-insensitive string contains
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        elif len(items) == 1:
            item = items[0]
            if isinstance(item, Matcher):
                if not any(item.matches(value) for value in self.val):
                    diff = DiffResult(
                        kind="contains", entries=[DiffEntry(path="missing", actual=None, expected=item.describe())]
                    )
                    return self.error(
                        f"Expected <{self.val}> to contain item matching {item.describe()}, but did not.",
                        diff=diff,
                    )
            elif item not in self.val:
                diff = DiffResult(kind="contains", entries=[DiffEntry(path="missing", actual=None, expected=item)])
                if self._is_dict_like(self.val):
                    return self.error(f"Expected <{self.val}> to contain key <{item}>, but did not.", diff=diff)
                else:
                    return self.error(f"Expected <{self.val}> to contain item <{item}>, but did not.", diff=diff)
        else:
            missing = []
            for item in items:
                if isinstance(item, Matcher):
                    if not any(item.matches(value) for value in self.val):
                        missing.append(item)
                elif item not in self.val:
                    missing.append(item)
            if missing:
                missing_desc = [
                    missing_item.describe() if isinstance(missing_item, Matcher) else missing_item
                    for missing_item in missing
                ]
                diff = DiffResult(
                    kind="contains",
                    entries=[
                        DiffEntry(path="missing", actual=None, expected=missing_item) for missing_item in missing_desc
                    ],
                )
                if self._is_dict_like(self.val):
                    return self.error(
                        f"Expected <{self.val}> to contain keys {self._fmt_items(items)}, but did not contain"
                        f" key{'' if len(missing) == 1 else 's'} {self._fmt_items(missing_desc)}.",
                        diff=diff,
                    )
                else:
                    return self.error(
                        f"Expected <{self.val}> to contain items {self._fmt_items(items)},"
                        f" but did not contain {self._fmt_items(missing_desc)}.",
                        diff=diff,
                    )
        return self

    def does_not_contain(self, *items) -> Self:
        """Asserts that val does not contain the given item or items.

        Checks if the collection excludes the given item or items using ``in`` operator.

        Args:
            *items: the item or items expected to be excluded

        Examples:
            Usage::

                assert_that('foo').does_not_contain('x')
                assert_that(['a', 'b']).does_not_contain('x', 'y')
                assert_that((1, 2, 3)).does_not_contain(4, 5)
                assert_that({'a': 1, 'b': 2}).does_not_contain('x', 'y')  # checks keys
                assert_that({'a', 'b'}).does_not_contain('x', 'y')
                assert_that([1, 2, 3]).is_type_of(list).contains(1, 2).does_not_contain(4, 5)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** contain the item or items

        Tip:
            Use the :meth:`~assertpy2.dict.DictMixin.does_not_contain_key` alias when working with
            *dict-like* objects to be self-documenting.
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        elif len(items) == 1:
            if items[0] in self.val:
                return self.error(f"Expected <{self.val}> to not contain item <{items[0]}>, but did.")
        else:
            found = [item for item in items if item in self.val]
            if found:
                return self.error(
                    f"Expected <{self.val}> to not contain items {self._fmt_items(items)},"
                    f" but did contain {self._fmt_items(found)}."
                )
        return self

    def contains_only(self, *items) -> Self:
        """Asserts that val contains *only* the given item or items.

        Checks if the collection contains only the given item or items using ``in`` operator.

        Args:
            *items: the *only* item or items expected to be contained

        Examples:
            Usage::

                assert_that('foo').contains_only('f', 'o')
                assert_that(['a', 'a', 'b']).contains_only('a', 'b')
                assert_that((1, 1, 2)).contains_only(1, 2)
                assert_that({'a': 1, 'a': 2, 'b': 3}).contains_only('a', 'b')
                assert_that({'a', 'a', 'b'}).contains_only('a', 'b')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val contains anything **not** item or items
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        else:
            extra = [item for item in self.val if item not in items]
            if extra:
                return self.error(
                    f"Expected <{self.val}> to contain only {self._fmt_items(items)},"
                    f" but did contain {self._fmt_items(extra)}."
                )

            missing = [item for item in items if item not in self.val]
            if missing:
                return self.error(
                    f"Expected <{self.val}> to contain only {self._fmt_items(items)},"
                    f" but did not contain {self._fmt_items(missing)}."
                )
        return self

    def contains_sequence(self, *items) -> Self:
        """Asserts that val contains the given ordered sequence of items.

        Checks if the collection contains the given sequence of items using ``in`` operator.

        Args:
            *items: the sequence of items expected to be contained

        Examples:
            Usage::

                assert_that('foo').contains_sequence('f', 'o')
                assert_that('foo').contains_sequence('o', 'o')
                assert_that(['a', 'b', 'c']).contains_sequence('b', 'c')
                assert_that((1, 2, 3)).contains_sequence(1, 2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contains the given sequence of items
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        if isinstance(self.val, str):
            search_start = 0
            for item in items:
                if not isinstance(item, str):
                    raise TypeError("given args must be strings when val is a string")
                found_index = self.val.find(item, search_start)
                if found_index == -1:
                    return self.error(
                        f"Expected <{self.val}> to contain sequence {self._fmt_items(items)}, but did not."
                    )
                search_start = found_index + len(item)
            return self
        try:
            for i in range(len(self.val) - len(items) + 1):
                for j in range(len(items)):
                    if self.val[i + j] != items[j]:
                        break
                else:
                    return self
        except TypeError:
            raise TypeError("val is not iterable") from None
        return self.error(f"Expected <{self.val}> to contain sequence {self._fmt_items(items)}, but did not.")

    def contains_duplicates(self) -> Self:
        """Asserts that val is iterable and *does* contain duplicates.

        Examples:
            Usage::

                assert_that('foo').contains_duplicates()
                assert_that(['a', 'a', 'b']).contains_duplicates()
                assert_that((1, 1, 2)).contains_duplicates()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain any duplicates
        """
        try:
            if len(self.val) != len(set(self.val)):
                return self
        except TypeError:
            raise TypeError("val is not iterable") from None
        return self.error(f"Expected <{self.val}> to contain duplicates, but did not.")

    def does_not_contain_duplicates(self) -> Self:
        """Asserts that val is iterable and *does not* contain any duplicates.

        Examples:
            Usage::

                assert_that('fox').does_not_contain_duplicates()
                assert_that(['a', 'b', 'c']).does_not_contain_duplicates()
                assert_that((1, 2, 3)).does_not_contain_duplicates()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** contain duplicates
        """
        try:
            if len(self.val) == len(set(self.val)):
                return self
        except TypeError:
            raise TypeError("val is not iterable") from None
        return self.error(f"Expected <{self.val}> to not contain duplicates, but did.")

    def is_empty(self) -> Self:
        """Asserts that val is empty.

        Examples:
            Usage::

                assert_that('').is_empty()
                assert_that([]).is_empty()
                assert_that(()).is_empty()
                assert_that({}).is_empty()
                assert_that(set()).is_empty()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** empty
        """
        if len(self.val) != 0:
            if isinstance(self.val, str):
                return self.error(f"Expected <{self.val}> to be empty string, but was not.")
            else:
                return self.error(f"Expected <{self.val}> to be empty, but was not.")
        return self

    def is_not_empty(self) -> Self:
        """Asserts that val is *not* empty.

        Examples:
            Usage::

                assert_that('foo').is_not_empty()
                assert_that(['a', 'b']).is_not_empty()
                assert_that((1, 2, 3)).is_not_empty()
                assert_that({'a': 1, 'b': 2}).is_not_empty()
                assert_that({'a', 'b'}).is_not_empty()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** empty
        """
        if len(self.val) == 0:
            if isinstance(self.val, str):
                return self.error("Expected not empty string, but was empty.")
            else:
                return self.error("Expected not empty, but was empty.")
        return self

    def contains_exactly(self, *items) -> Self:
        """Asserts that val contains exactly the given items in the given order.

        Unlike :meth:`contains_only` (which ignores order) and :meth:`contains_sequence`
        (which allows extra items), this method requires exact count, items, and order.

        Args:
            *items: the items expected, in exact order

        Examples:
            Usage::

                assert_that([1, 2, 3]).contains_exactly(1, 2, 3)
                assert_that(['a', 'b']).contains_exactly('a', 'b')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain exactly the given items in order
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        try:
            val_list = list(self.val)
        except TypeError:
            raise TypeError("val is not iterable") from None
        if val_list != list(items):
            val_counts = Counter(val_list)
            item_counts = Counter(items)
            entries = [
                DiffEntry(path="extra", actual=item, expected=None)
                for item in sorted((val_counts - item_counts).elements(), key=repr)
            ]
            entries.extend(
                DiffEntry(path="missing", actual=None, expected=item)
                for item in sorted((item_counts - val_counts).elements(), key=repr)
            )
            diff = DiffResult(kind="contains", entries=entries) if entries else None
            return self.error(
                f"Expected <{self.val}> to contain exactly {self._fmt_items(items)}, but did not.",
                diff=diff,
            )
        return self

    def contains_in_order(self, *items) -> Self:
        """Asserts that val contains the given items in the given order (as a subsequence).

        Items must appear in the given order but do not need to be contiguous.
        Unlike :meth:`contains_sequence` which requires contiguous items.

        Args:
            *items: the items expected, in order (but not necessarily contiguous)

        Examples:
            Usage::

                assert_that([1, 5, 2, 8, 3]).contains_in_order(1, 2, 3)
                assert_that(['a', 'x', 'b', 'y', 'c']).contains_in_order('a', 'b', 'c')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain items in the given order
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        try:
            val_list = list(self.val)
        except TypeError:
            raise TypeError("val is not iterable") from None
        item_index = 0
        for element in val_list:
            if item_index < len(items) and element == items[item_index]:
                item_index += 1
        if item_index != len(items):
            return self.error(f"Expected <{self.val}> to contain {self._fmt_items(items)} in order, but did not.")
        return self

    def contains_only_once(self, *items: object) -> Self:
        """Asserts that val contains each given item exactly once.

        Each given item must appear in val with a count of exactly one: an item absent from val is
        reported as missing, an item occurring more than once is reported as duplicated.

        Args:
            *items: the items each expected to occur exactly once

        Examples:
            Usage:

                assert_that([1, 2, 3]).contains_only_once(1, 3)
                assert_that('foo').contains_only_once('f')

                assert_that([1, 2, 2, 3]).contains_only_once(2)  # fails (occurs twice)
                assert_that([1, 2, 3]).contains_only_once(4)  # fails (missing)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any given item is missing from val or occurs more than once
            TypeError: if val is not iterable
            ValueError: if no items are given
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        try:
            val_list = list(self.val)
        except TypeError:
            raise TypeError("val is not iterable") from None
        counts = Counter(val_list)
        missing = [item for item in items if counts[item] == 0]
        duplicated = [item for item in items if counts[item] > 1]
        if missing or duplicated:
            entries = [DiffEntry(path="missing", actual=None, expected=item) for item in missing]
            entries.extend(DiffEntry(path="duplicated", actual=counts[item], expected=item) for item in duplicated)
            problems = []
            if missing:
                problems.append(f"did not contain {self._fmt_items(missing)}")
            if duplicated:
                problems.append(f"contained {self._fmt_items(duplicated)} more than once")
            return self.error(
                f"Expected <{self.val}> to contain {self._fmt_items(items)} only once, but {' and '.join(problems)}.",
                diff=DiffResult(kind="contains", entries=entries),
            )
        return self

    def is_in(self, *items: object) -> Self:
        """Asserts that val is equal to one of the given items.

        Args:
            *items: the items expected to contain val

        Examples:
            Usage:

                assert_that('foo').is_in('foo', 'bar', 'baz')
                assert_that(1).is_in(0, 1, 2, 3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** in the given items
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        else:
            for item in items:
                if self.val == item:
                    return self
        return self.error(f"Expected <{self.val}> to be in {self._fmt_items(items)}, but was not.")

    def is_not_in(self, *items) -> Self:
        """Asserts that val is not equal to one of the given items.

        Args:
            *items: the items expected to exclude val

        Examples:
            Usage::

                assert_that('foo').is_not_in('bar', 'baz', 'box')
                assert_that(1).is_not_in(-1, -2, -3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** in the given items
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        else:
            for item in items:
                if self.val == item:
                    return self.error(f"Expected <{self.val}> to not be in {self._fmt_items(items)}, but was.")
        return self
