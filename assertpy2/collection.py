from __future__ import annotations

import collections.abc
from typing import TYPE_CHECKING, Any, cast

from ._engine._introspection import is_mapping_like, materialized
from ._engine._membership import not_contained_in
from ._engine._mixin_base import _MixinBase
from ._engine._ordering import UnorderableError, first_out_of_order
from ._engine._require import argument, refuse, require_type, sized_len
from ._satisfies import _warn_vacuous
from .matchers import _is_matcher

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sized

    from ._engine._compat import Self
    from ._engine._introspection import MappingLike
    from .matchers import Matcher

__tracebackhide__ = True


class CollectionMixin(_MixinBase):
    """Collection assertions mixin."""

    def _as_list(self) -> list[Any]:
        """Returns val as a list, raising TypeError if val is not iterable."""
        require_type(self.val, collections.abc.Iterable, "iterable")
        return list(self.val)

    def is_iterable(self) -> Self:
        """Asserts that val is iterable.

        Examples:
            Usage:

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
            Usage:

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

    def is_subset_of(self, *supersets: object, allow_empty: bool = False) -> Self:
        """Asserts that val is iterable and a subset of the given superset (or supersets).

        Args:
            *supersets (object): the expected superset (or supersets)

        Examples:
            Usage:

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
        require_type(self.val, collections.abc.Iterable, "iterable")
        if len(supersets) == 0:
            raise ValueError("one or more superset args must be given")

        missing = []
        if is_mapping_like(self.val):
            # read whole before any superset is walked: one of them sharing this subject's iterator would leave nothing
            # here, and a subset of nothing is anything.  Pairs rather than keys, so a superset that reaches the subject
            # cannot answer for it either
            entries = [(key, self.val[key]) for key in self.val]
            superdict = {}
            for superset_index, superset in enumerate(supersets):
                self._require_dict_like(superset, check_values=False, name=f"arg #{superset_index + 1}")
                mapping = cast("MappingLike", superset)
                for key in mapping:
                    superdict.update({key: mapping[key]})

            walked = 0
            for key, value in entries:
                walked += 1
                if key not in superdict:
                    missing.append({key: value})  # bad key
                elif value != superdict[key]:
                    missing.append({key: value})  # bad val
            if missing:
                return self.error(
                    f"Expected <{self.val}> to be subset of <{superdict}>, "
                    f"but {self._fmt_items(missing)} {'was' if len(missing) == 1 else 'were'} missing.",
                    expected=superdict,
                )
            if not walked:
                _warn_vacuous("is_subset_of", allow_empty)
        else:
            walked = list(materialized(self.val))
            collected = []
            for superset in supersets:
                try:
                    # the `except` is what decides this, so the cast asserts nothing the code does not already handle
                    collected.extend(cast("Iterable[object]", superset))
                except TypeError:  # noqa: PERF203  # a non-iterable superset is treated as a single value
                    collected.append(superset)
            # the same core the matcher spelling uses: a bare `set()` reported a value whose hash disagrees with its
            # `==` as missing
            missing.extend(not_contained_in(walked, collected))
            try:
                # for the message only, not tied to the lookup above: the failure has always shown the superset as a set
                # where that was possible, and which shape the membership decision took is no reason to change that
                superset_values: object = set(collected)
            except TypeError:
                superset_values = collected
            if missing:
                return self.error(
                    f"Expected <{self.val}> to be subset of {self._fmt_items(superset_values)}, "
                    f"but {self._fmt_items(missing)} {'was' if len(missing) == 1 else 'were'} missing.",
                    expected=superset_values,
                )
            if not walked:
                _warn_vacuous("is_subset_of", allow_empty)

        return self

    def is_sorted(
        self,
        key: Callable[[Any], Any] = lambda item: item,
        reverse: bool = False,
        *,
        allow_empty: bool = False,
    ) -> Self:
        """Asserts that val is iterable and is sorted.

        Args:
            key (function): the one-arg function to extract the sort comparison key.  Defaults to
                ``lambda x: x`` to just compare items directly.
            reverse (bool): if ``True``, then comparison key is reversed.  Defaults to ``False``.

        Examples:
            Usage:

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
        require_type(self.val, collections.abc.Iterable, "iterable")
        if not callable(key):
            refuse(key, "callable", subject=argument("key"))

        walked = 0

        def _counted(items):
            nonlocal walked
            for item in items:
                walked += 1
                yield item

        broken = None
        try:
            broken = first_out_of_order(_counted(self.val), key=key, reverse=reverse)
        except UnorderableError:
            # reported about the collection, not left to Python's "'<' not supported between instances of 'str' and
            # 'int'", which is about the operator and names neither the assertion nor the value it was given
            unorderable = True
        else:
            unorderable = False
        if unorderable:
            refuse(self.val, "a collection whose items can be ordered against each other")
        if broken is not None:
            index, earlier, later = broken
            direction = " reverse" if reverse else ""
            return self.error(
                f"Expected <{self.val}> to be sorted{direction}, "
                f"but subset {self._fmt_items([earlier, later])} at index {index} is not."
            )
        if not walked:
            _warn_vacuous("is_sorted", allow_empty)
        return self

    def has_same_size_as(self, other: Sized) -> Self:
        """Asserts that val has the same length as other.

        Args:
            other (object): a sized object whose ``len()`` is compared with val's

        Examples:
            Usage:

                assert_that([1, 2, 3]).has_same_size_as((4, 5, 6))
                assert_that('foo').has_same_size_as([1, 2, 3])

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val and other do **not** have the same length
            TypeError: if other is not a sized object
        """
        # the subject first: this assertion is about it, and reading the operand first let the operand's
        # own `__len__` answer for both
        actual_len = sized_len(self.val)
        # `other` used to be left to `len()` itself, which answers "object of type 'int' has no len()":
        # about the builtin rather than the assertion, and naming neither operand
        other_len = sized_len(other, subject=argument("other"))
        if actual_len != other_len:
            return self.error(
                f"Expected <{self.val}> to have same size as <{other}> of length <{other_len}>,"
                f" but was length <{actual_len}>.",
                expected=other_len,
            )
        return self

    def has_size_greater_than(self, size: int) -> Self:
        """Asserts that val has a length strictly greater than the given size.

        Args:
            size: the size val's length must exceed

        Examples:
            Usage:

                assert_that([1, 2, 3]).has_size_greater_than(2)
                assert_that('foo').has_size_greater_than(1)
                assert_that({'a': 1, 'b': 2}).has_size_greater_than(1)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val's length is **not** greater than the given size
            TypeError: if the given arg is not an int
            ValueError: if the given arg is negative
        """
        if type(size) is not int:
            refuse(size, "an integer", subject=argument("size"))
        if size < 0:
            raise ValueError("given arg must be a positive int")
        actual = sized_len(self.val)
        if actual <= size:
            return self.error(
                f"Expected <{self.val}> to have size greater than <{size}>, but was <{actual}>.", expected=size
            )
        return self

    def has_size_less_than(self, size: int) -> Self:
        """Asserts that val has a length strictly less than the given size.

        Args:
            size: the size val's length must stay under

        Examples:
            Usage:

                assert_that([1, 2, 3]).has_size_less_than(4)
                assert_that('foo').has_size_less_than(5)
                assert_that({'a': 1, 'b': 2}).has_size_less_than(3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val's length is **not** less than the given size
            TypeError: if the given arg is not an int
            ValueError: if the given arg is negative
        """
        if type(size) is not int:
            refuse(size, "an integer", subject=argument("size"))
        if size < 0:
            raise ValueError("given arg must be a positive int")
        actual = sized_len(self.val)
        if actual >= size:
            return self.error(
                f"Expected <{self.val}> to have size less than <{size}>, but was <{actual}>.", expected=size
            )
        return self

    def has_size_between(self, low: int, high: int) -> Self:
        """Asserts that val has a length between low and high (both inclusive).

        Args:
            low: the inclusive lower size bound
            high: the inclusive upper size bound

        Examples:
            Usage:

                assert_that([1, 2, 3]).has_size_between(1, 5)
                assert_that('foo').has_size_between(3, 3)
                assert_that({'a': 1, 'b': 2}).has_size_between(0, 2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val's length is **not** between low and high
            TypeError: if a given arg is not an int
            ValueError: if a given arg is negative, or low is greater than high
        """
        if type(low) is not int:
            refuse(low, "an integer", subject=argument("low"))
        if type(high) is not int:
            refuse(high, "an integer", subject=argument("high"))
        if low < 0 or high < 0:
            raise ValueError("given args must be positive ints")
        if low > high:
            raise ValueError("given low arg must be less than given high arg")
        if not low <= sized_len(self.val) <= high:
            return self.error(
                f"Expected <{self.val}> to have size between <{low}> and <{high}>, but was <{sized_len(self.val)}>.",
                expected=(low, high),
            )
        return self

    def filtered_on(self, predicate: Matcher[Any] | Callable[[Any], bool]) -> Self:
        """Returns a new builder with elements matching the predicate.

        Args:
            predicate: callable or Matcher. If a Matcher, uses ``predicate.matches(item)``.

        Examples:
            Usage:

                assert_that([1, -2, 3]).filtered_on(lambda x: x > 0).is_length(2)
                assert_that(items).filtered_on(match.is_positive()).is_not_empty()

        Returns:
            AssertionBuilder: returns a new instance with the filtered list as val
        """
        require_type(self.val, collections.abc.Iterable, "iterable")
        # the protocol test every other matcher-taking method uses, rather than a `BaseMatcher` subclass check: a
        # custom matcher written against the documented shape was called as a plain function here
        matches = predicate.matches if _is_matcher(predicate) else cast("Callable[..., object]", predicate)
        # counted in the filtering pass: a generator is spent by it, so asking its length afterwards
        # made the note about a filter that emptied a non-empty source claim the source was empty
        seen = 0
        filtered = []
        for item in self.val:
            seen += 1
            if matches(item):
                filtered.append(item)
        return self.builder(
            filtered,
            self.description,
            self.kind,
            logger=self.logger,
            origin=f"filtered_on() kept {len(filtered)} of {seen} items",
        )

    def mapped(self, func: Callable[[Any], Any]) -> Self:
        """Returns a new builder with each element transformed by func.

        Args:
            func: callable applied to each element.

        Examples:
            Usage:

                assert_that(["a", "b"]).mapped(str.upper).contains("A")

        Returns:
            AssertionBuilder: returns a new instance with the mapped list as val
        """
        require_type(self.val, collections.abc.Iterable, "iterable")
        return self.builder([func(item) for item in self.val], self.description, self.kind, logger=self.logger)

    def flat_mapped(self, func: Callable[[Any], Iterable[Any]]) -> Self:
        """Returns a new builder with each element expanded and flattened by func.

        Args:
            func: callable returning an iterable for each element.

        Examples:
            Usage:

                assert_that(["ab", "cd"]).flat_mapped(list).contains("a", "c")

        Returns:
            AssertionBuilder: returns a new instance with the flattened list as val
        """
        require_type(self.val, collections.abc.Iterable, "iterable")
        return self.builder(
            [inner for item in self.val for inner in func(item)], self.description, self.kind, logger=self.logger
        )

    def first(self) -> Self:
        """Returns a new builder with the first element of val.

        Examples:
            Usage:

                assert_that([10, 20, 30]).first().is_equal_to(10)

        Returns:
            AssertionBuilder: returns a new instance with the first element as val

        Raises:
            ValueError: if val is empty
        """
        items = self._as_list()
        if not items:
            raise ValueError("Expected non-empty iterable, but was empty.")
        return self.builder(items[0], self.description, self.kind, logger=self.logger)

    def last(self) -> Self:
        """Returns a new builder with the last element of val.

        Examples:
            Usage:

                assert_that([10, 20, 30]).last().is_equal_to(30)

        Returns:
            AssertionBuilder: returns a new instance with the last element as val

        Raises:
            ValueError: if val is empty
        """
        items = self._as_list()
        if not items:
            raise ValueError("Expected non-empty iterable, but was empty.")
        return self.builder(items[-1], self.description, self.kind, logger=self.logger)

    def element(self, index: int) -> Self:
        """Returns a new builder with the element at the given index.

        Args:
            index: zero-based index.

        Examples:
            Usage:

                assert_that([10, 20, 30]).element(1).is_equal_to(20)

        Returns:
            AssertionBuilder: returns a new instance with the selected element as val

        Raises:
            IndexError: if index is out of range
        """
        items = self._as_list()
        if index < 0 or index >= len(items):
            raise IndexError(f"Expected index {index} to be in range [0, {len(items)}), but was out of range.")
        return self.builder(items[index], self.description, self.kind, logger=self.logger)

    def single(self) -> Self:
        """Returns a new builder with the only element of val.

        Examples:
            Usage:

                assert_that([42]).single().is_equal_to(42)

        Returns:
            AssertionBuilder: returns a new instance with the single element as val

        Raises:
            ValueError: if val is empty or has more than one element
        """
        items = self._as_list()
        if not items:
            raise ValueError("Expected iterable with single element, but was empty.")
        if len(items) > 1:
            raise ValueError(f"Expected iterable with single element, but had {len(items)} elements.")
        return self.builder(items[0], self.description, self.kind, logger=self.logger)
