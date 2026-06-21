from __future__ import annotations

import collections.abc
from typing import TYPE_CHECKING, Any

from ._mixin_base import _MixinBase
from .matchers import BaseMatcher

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from ._compat import Self

__tracebackhide__ = True


class CollectionMixin(_MixinBase):
    """Collection assertions mixin."""

    def is_iterable(self) -> Self:
        """Asserts that val is iterable.

        Examples:
            Usage::

                assert_that('foo').is_iterable()
                assert_that(['a', 'b']).is_iterable()
                assert_that((1, 2, 3)).is_iterable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** iterable
        """
        if not isinstance(self.val, collections.abc.Iterable):
            return self.error("Expected iterable, but was not.")
        return self

    def is_not_iterable(self) -> Self:
        """Asserts that val is not iterable.

        Examples:
            Usage::

                assert_that(1).is_not_iterable()
                assert_that(123.4).is_not_iterable()
                assert_that(True).is_not_iterable()
                assert_that(None).is_not_iterable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** iterable
        """
        if isinstance(self.val, collections.abc.Iterable):
            return self.error("Expected not iterable, but was.")
        return self

    def is_subset_of(self, *supersets) -> Self:
        """Asserts that val is iterable and a subset of the given superset (or supersets).

        Args:
            *supersets: the expected superset (or supersets)

        Examples:
            Usage::

                assert_that('foo').is_subset_of('abcdefghijklmnopqrstuvwxyz')
                assert_that(['a', 'b']).is_subset_of(['a', 'b', 'c'])
                assert_that((1, 2, 3)).is_subset_of([1, 2, 3, 4])
                assert_that({'a': 1, 'b': 2}).is_subset_of({'a': 1, 'b': 2, 'c': 3})
                assert_that({'a', 'b'}).is_subset_of({'a', 'b', 'c'})

                # or multiple supersets (as comma-separated args)
                assert_that('aBc').is_subset_of('abc', 'ABC')
                assert_that((1, 2, 3)).is_subset_of([1, 3, 5], [2, 4, 6])

                assert_that({'a': 1, 'b': 2}).is_subset_of({'a': 1, 'c': 3})  # fails
                # Expected <{'a': 1, 'b': 2}> to be subset of <{'a': 1, 'c': 3}>, but <{'b': 2}> was missing.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** subset of given superset (or supersets)
        """
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        if len(supersets) == 0:
            raise ValueError("one or more superset args must be given")

        missing = []
        if hasattr(self.val, "keys") and callable(self.val.keys) and hasattr(self.val, "__getitem__"):
            superdict = {}
            for superset_index, superset in enumerate(supersets):
                self._check_dict_like(superset, check_values=False, name=f"arg #{superset_index + 1}")
                for key in superset:
                    superdict.update({key: superset[key]})

            for key in self.val:
                if key not in superdict:
                    missing.append({key: self.val[key]})  # bad key
                elif self.val[key] != superdict[key]:
                    missing.append({key: self.val[key]})  # bad val
            if missing:
                return self.error(
                    f"Expected <{self.val}> to be subset of {self._fmt_items(superdict)}, "
                    f"but {self._fmt_items(missing)} {'was' if len(missing) == 1 else 'were'} missing."
                )
        else:
            superset_values = set()
            for superset in supersets:
                try:
                    for key in superset:
                        superset_values.add(key)
                except TypeError:  # noqa: PERF203  # per-item fallback: a non-iterable superset is treated as a single value
                    superset_values.add(superset)

            missing.extend(item for item in self.val if item not in superset_values)
            if missing:
                return self.error(
                    f"Expected <{self.val}> to be subset of {self._fmt_items(superset_values)}, "
                    f"but {self._fmt_items(missing)} {'was' if len(missing) == 1 else 'were'} missing."
                )

        return self

    def is_sorted(self, key=lambda x: x, reverse=False) -> Self:
        """Asserts that val is iterable and is sorted.

        Args:
            key (function): the one-arg function to extract the sort comparison key.  Defaults to
                ``lambda x: x`` to just compare items directly.
            reverse (bool): if ``True``, then comparison key is reversed.  Defaults to ``False``.

        Examples:
            Usage::

                assert_that(['a', 'b', 'c']).is_sorted()
                assert_that((1, 2, 3)).is_sorted()

                # with a key function
                assert_that('aBc').is_sorted(key=str.lower)

                # reverse order
                assert_that(['c', 'b', 'a']).is_sorted(reverse=True)
                assert_that((3, 2, 1)).is_sorted(reverse=True)

                assert_that((1, 2, 3, 4, -5, 6)).is_sorted()  # fails
                # Expected <(1, 2, 3, 4, -5, 6)> to be sorted, but subset <4, -5> at index 3 is not.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** sorted
        """
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")

        previous = None
        for index, current in enumerate(self.val):
            if index > 0:
                if reverse:
                    if key(current) > key(previous):
                        return self.error(
                            f"Expected <{self.val}> to be sorted reverse, "
                            f"but subset {self._fmt_items([previous, current])} at index {index - 1} is not."
                        )
                else:
                    if key(current) < key(previous):
                        return self.error(
                            f"Expected <{self.val}> to be sorted, "
                            f"but subset {self._fmt_items([previous, current])} at index {index - 1} is not."
                        )
            previous = current

        return self

    def filtered_on(self, predicate: Callable[[Any], bool]) -> Self:
        """Returns a new builder with elements matching the predicate.

        Args:
            predicate: callable or Matcher. If a Matcher, uses ``predicate.matches(item)``.

        Examples:
            Usage::

                assert_that([1, -2, 3]).filtered_on(lambda x: x > 0).is_length(2)
                assert_that(items).filtered_on(match.is_positive()).is_not_empty()

        Returns:
            AssertionBuilder: returns a new instance with the filtered list as val
        """
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        if isinstance(predicate, BaseMatcher):
            filtered = [item for item in self.val if predicate.matches(item)]
        else:
            filtered = [item for item in self.val if predicate(item)]
        return self.builder(filtered, self.description, self.kind)

    def mapped(self, func: Callable[[Any], Any]) -> Self:
        """Returns a new builder with each element transformed by func.

        Args:
            func: callable applied to each element.

        Examples:
            Usage::

                assert_that(["a", "b"]).mapped(str.upper).contains("A")

        Returns:
            AssertionBuilder: returns a new instance with the mapped list as val
        """
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        return self.builder([func(item) for item in self.val], self.description, self.kind)

    def flat_mapped(self, func: Callable[[Any], Iterable[Any]]) -> Self:
        """Returns a new builder with each element expanded and flattened by func.

        Args:
            func: callable returning an iterable for each element.

        Examples:
            Usage::

                assert_that(["ab", "cd"]).flat_mapped(list).contains("a", "c")

        Returns:
            AssertionBuilder: returns a new instance with the flattened list as val
        """
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        return self.builder([inner for item in self.val for inner in func(item)], self.description, self.kind)

    def first(self) -> Self:
        """Returns a new builder with the first element of val.

        Examples:
            Usage::

                assert_that([10, 20, 30]).first().is_equal_to(10)

        Returns:
            AssertionBuilder: returns a new instance with the first element as val

        Raises:
            ValueError: if val is empty
        """
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        items = list(self.val)
        if not items:
            raise ValueError("Expected non-empty iterable, but was empty.")
        return self.builder(items[0], self.description, self.kind)

    def last(self) -> Self:
        """Returns a new builder with the last element of val.

        Examples:
            Usage::

                assert_that([10, 20, 30]).last().is_equal_to(30)

        Returns:
            AssertionBuilder: returns a new instance with the last element as val

        Raises:
            ValueError: if val is empty
        """
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        items = list(self.val)
        if not items:
            raise ValueError("Expected non-empty iterable, but was empty.")
        return self.builder(items[-1], self.description, self.kind)

    def element(self, index: int) -> Self:
        """Returns a new builder with the element at the given index.

        Args:
            index: zero-based index.

        Examples:
            Usage::

                assert_that([10, 20, 30]).element(1).is_equal_to(20)

        Returns:
            AssertionBuilder: returns a new instance with the selected element as val

        Raises:
            IndexError: if index is out of range
        """
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        items = list(self.val)
        if index < 0 or index >= len(items):
            raise IndexError(f"Expected index {index} to be in range [0, {len(items)}), but was out of range.")
        return self.builder(items[index], self.description, self.kind)

    def single(self) -> Self:
        """Returns a new builder with the only element of val.

        Examples:
            Usage::

                assert_that([42]).single().is_equal_to(42)

        Returns:
            AssertionBuilder: returns a new instance with the single element as val

        Raises:
            ValueError: if val is empty or has more than one element
        """
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        items = list(self.val)
        if not items:
            raise ValueError("Expected iterable with single element, but was empty.")
        if len(items) > 1:
            raise ValueError(f"Expected iterable with single element, but had {len(items)} elements.")
        return self.builder(items[0], self.description, self.kind)
