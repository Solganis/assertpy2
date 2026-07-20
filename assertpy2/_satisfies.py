from __future__ import annotations

import collections.abc
import os
import warnings
from typing import TYPE_CHECKING, Any

from ._engine._diff import _walk_leaves
from ._engine._introspection import is_attrs_instance, is_model_dump_object
from ._engine._mixin_base import _MixinBase
from .errors import DiffEntry, DiffResult, VacuousAssertionWarning
from .matchers import IsNotNoneMatcher, Matcher, StructureMatcher, _apply_matcher, _describe_matcher, _is_matcher

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from ._engine._compat import Self

__tracebackhide__ = True


def _describe_unpaired(matcher, raised_count):
    """Describe an unpaired matcher, noting raised probes so a buggy predicate is not mistaken for a mismatch."""
    description = _describe_matcher(matcher)
    if raised_count:
        item_word = "item" if raised_count == 1 else "items"
        return f"{description} (probe raised TypeError on {raised_count} {item_word})"
    return description


def _max_bipartite_assignment(satisfied: list[list[bool]]) -> list[int | None]:
    """Pair each row with a distinct satisfying column via Kuhn's augmenting paths (None if unpairable)."""
    column_owner: dict[int, int] = {}

    def _augment(row: int, visited: set[int]) -> bool:
        for column, ok in enumerate(satisfied[row]):
            if ok and column not in visited:
                visited.add(column)
                if column not in column_owner or _augment(column_owner[column], visited):
                    column_owner[column] = row
                    return True
        return False

    for row in range(len(satisfied)):
        _augment(row, set())
    assignment: list[int | None] = [None] * len(satisfied)
    for column, row in column_owner.items():
        assignment[row] = column
    return assignment


_VACUOUS_GUARD: bool = False
"""Whether a universal assertion over an empty value warns.

Off by default: a suite running ``filterwarnings = ["error"]`` would otherwise fail on upgrade, and a
property-based test generates empty collections as a matter of course.  Turn it on with the pytest
``--assertpy2-vacuous`` flag or the ``ASSERTPY2_VACUOUS`` environment variable for other runners.
"""

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _guard_enabled() -> bool:
    return _VACUOUS_GUARD or os.environ.get("ASSERTPY2_VACUOUS", "").strip().lower() in _TRUTHY


def _warn_if_vacuous(name: str, value: object, allow_empty: bool) -> None:
    """Warn when a universal assertion is about to pass because there is nothing to quantify over.

    Called from each public entry point rather than from the shared implementation, so the name in the
    message is the one the caller used and ``stacklevel`` lands on their line rather than ours.
    """
    if allow_empty or not _guard_enabled():
        return
    try:
        empty = len(value) == 0  # ty: ignore[invalid-argument-type]  # guarded by the except below
    except Exception:  # a diagnostic must never crash the assertion it is watching
        # no usable len(): an unsized value (a one-shot iterable) or a broken __len__.  Either way,
        # stay out of the way rather than draining the value or surfacing its error as our own.
        return
    if empty:
        warnings.warn(
            f"{name}() passed over an empty value, so nothing was checked. Pass allow_empty=True if that is intended.",
            VacuousAssertionWarning,
            stacklevel=3,
        )


class SatisfiesMixin(_MixinBase):
    """Predicate and matcher-application assertions: satisfies / each / *_satisfy / matches_structure."""

    def all_fields_satisfy(self, matcher: Matcher | Callable[..., bool], *, allow_empty: bool = False) -> Self:
        """Asserts that every scalar leaf in val's object graph satisfies the given matcher.

        Walks val recursively (mappings, dataclasses, namedtuples, Pydantic models, lists, tuples) and
        applies the matcher to each leaf value, reporting the path of every leaf that does not satisfy it.
        Scalars, strings, sets and opaque objects are treated as single leaves.

        Args:
            matcher: a `Matcher` or callable predicate applied to every leaf

        Examples:
            Usage:

                from assertpy2 import match

                assert_that({"a": 1, "nested": {"b": 2}}).all_fields_satisfy(match.is_positive())
                assert_that([1, [2, 3]]).all_fields_satisfy(lambda x: x > 0)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any leaf does **not** satisfy the matcher
            TypeError: if matcher is neither a Matcher nor callable
        """
        _warn_if_vacuous("all_fields_satisfy", self.val, allow_empty)
        if not _is_matcher(matcher) and not callable(matcher):
            raise TypeError("given arg must be a Matcher or callable")
        description = _describe_matcher(matcher)
        failures = [
            DiffEntry(path=path, actual=leaf, expected=description)
            for path, leaf in _walk_leaves(self.val)
            if not _apply_matcher(matcher, leaf)
        ]
        if failures:
            count = len(failures)
            field_word = "field" if count == 1 else "fields"
            return self.error(
                f"Expected all fields to satisfy {description}, but {count} {field_word} did not.",
                actual=self.val,
                expected=description,
                diff=DiffResult(kind="match", entries=failures),
            )
        return self

    def has_no_none_fields(self, *, allow_empty: bool = False) -> Self:
        """Asserts that no scalar leaf in val's object graph is ``None``.

        Convenience wrapper over `all_fields_satisfy()` with a not-``None`` matcher; reports the path
        of every ``None`` leaf found anywhere in the graph.

        Examples:
            Usage:

                assert_that({"id": 1, "profile": {"name": "Alice"}}).has_no_none_fields()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any leaf **is** ``None``
        """
        _warn_if_vacuous("has_no_none_fields", self.val, allow_empty)
        return self.all_fields_satisfy(IsNotNoneMatcher(), allow_empty=True)

    def satisfies(self, matcher: Matcher | Callable[..., bool]) -> Self:
        """Asserts that val satisfies the given matcher.

        Args:
            matcher: a `Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers:

                from assertpy2 import match

                assert_that(7).satisfies(match.greater_than(5) & match.less_than(10))
                assert_that('hello').satisfies(match.starts_with('he'))

            Usage with callables:

                assert_that(42).satisfies(lambda x: x % 2 == 0)

            When the callable is typed with ``TypeIs`` it also *narrows* the chain to the guarded type
            (refinement narrowing), so ``.value`` hands the value back typed - see
            [Type Safety](../concepts/type-safety.md#refinement-narrowing-with-a-typeis-predicate-advanced) for
            checker support (advanced; not yet in PyCharm).

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** satisfy the matcher
        """
        if _is_matcher(matcher):
            if not matcher.matches(self.val):
                description = matcher.describe()
                return self.error(
                    f"Expected {description}, but {matcher.describe_mismatch(self.val)}.",
                    actual=self.val,
                    expected=description,
                    diff=DiffResult(kind="match", entries=[DiffEntry(path=".", actual=self.val, expected=description)]),
                )
        elif callable(matcher):
            if not matcher(self.val):
                return self.error(f"Expected <{self.val}> to satisfy {_describe_matcher(matcher)}, but did not.")
        else:
            raise TypeError("given arg must be a Matcher or callable")
        return self

    def each(self, matcher: Matcher | Callable[..., bool], *, allow_empty: bool = False) -> Self:
        """Asserts that every item in val satisfies the given matcher.

        Args:
            matcher: a `Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers:

                from assertpy2 import match

                assert_that([1, 2, 3]).each(match.is_positive())
                assert_that([10, 20, 30]).each(match.between(1, 100))

            Usage with extracting:

                assert_that(users).extracting('age').each(match.between(18, 120))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any item does **not** satisfy the matcher
        """
        _warn_if_vacuous("each", self.val, allow_empty)
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        if _is_matcher(matcher):
            description = matcher.describe()
            for i, item in enumerate(self.val):
                if not matcher.matches(item):
                    return self.error(
                        f"Expected all items to satisfy {description}, but item at index {i} <{item}> did not:"
                        f" {matcher.describe_mismatch(item)}.",
                        actual=item,
                        expected=description,
                        diff=DiffResult(
                            kind="match", entries=[DiffEntry(path=f"[{i}]", actual=item, expected=description)]
                        ),
                    )
        elif callable(matcher):
            for i, item in enumerate(self.val):
                if not matcher(item):
                    return self.error(
                        f"Expected all items to satisfy {_describe_matcher(matcher)},"
                        f" but item at index {i} <{item}> did not."
                    )
        else:
            raise TypeError("given arg must be a Matcher or callable")
        return self

    def matches_structure(self, spec: dict[Any, Any]) -> Self:
        """Asserts that val matches the given structure specification.

        ``val`` may be a dict, a pydantic-style model (anything exposing ``model_dump()``), or an
        ``attrs`` instance, which is normalized to its dict before matching.  Each key in ``spec`` maps to either a
        `Matcher`, a raw value (checked via ``==``), or a nested ``dict``
        for recursive matching.  Extra keys in val that are absent from the spec are allowed.

        Args:
            spec: a dict where values can be Matcher instances, raw values, or nested dicts

        Examples:
            Usage:

                from assertpy2 import assert_that, match

                user = {"name": "Alice", "age": 30, "id": "550e8400-e29b-41d4-a716-446655440000"}
                assert_that(user).matches_structure({
                    "name": match.is_non_empty_string(),
                    "age": match.between(18, 120),
                    "id": match.is_uuid(),
                })

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** match the structure spec
        """
        if not isinstance(self.val, dict) and not is_model_dump_object(self.val) and not is_attrs_instance(self.val):
            raise TypeError("val must be a dict, a pydantic-style model, or an attrs instance")
        if not isinstance(spec, dict):
            raise TypeError("given arg must be a dict")
        matcher = StructureMatcher(spec)
        mismatches = matcher.collect_mismatches(self.val)
        if mismatches:
            entries = [
                DiffEntry(path=path, actual=actual, expected=description) for path, actual, description in mismatches
            ]
            return self.error(
                f"Expected <{self.val}> to match structure {matcher.describe()}, but"
                f" {matcher.describe_mismatch(self.val)}.",
                actual=self.val,
                expected=spec,
                diff=DiffResult(kind="match", entries=entries),
            )
        return self

    def is_callable(self) -> Self:
        """Asserts that val is callable.

        Examples:
            Usage:

                assert_that(lambda: None).is_callable()
                assert_that(print).is_callable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** callable
        """
        if not callable(self.val):
            return self.error(f"Expected <{self.val}> to be callable, but was not.")
        return self

    def is_not_callable(self) -> Self:
        """Asserts that val is not callable.

        Examples:
            Usage:

                assert_that(42).is_not_callable()
                assert_that('foo').is_not_callable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** callable
        """
        if callable(self.val):
            return self.error(f"Expected <{self.val}> to not be callable, but was.")
        return self

    def any_satisfy(self, matcher: Matcher | Callable[..., bool]) -> Self:
        """Asserts that at least one item in val satisfies the given matcher.

        Args:
            matcher: a `Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers:

                from assertpy2 import match

                assert_that([1, -2, 3]).any_satisfy(match.is_negative())

            Usage with callables:

                assert_that([1, 2, 3]).any_satisfy(lambda x: x > 2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if no item satisfies the matcher
        """
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        if _is_matcher(matcher):
            if not any(matcher.matches(item) for item in self.val):
                return self.error(f"Expected any item to satisfy {matcher.describe()}, but none did.")
        elif callable(matcher):
            if not any(matcher(item) for item in self.val):
                return self.error(f"Expected any item to satisfy {_describe_matcher(matcher)}, but none did.")
        else:
            raise TypeError("given arg must be a Matcher or callable")
        return self

    def all_satisfy(self, matcher: Matcher | Callable[..., bool], *, allow_empty: bool = False) -> Self:
        """Asserts that all items in val satisfy the given matcher.

        Semantic alias for [`each()`][assertpy2.base.BaseMixin.each].

        Args:
            matcher: a `Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers:

                from assertpy2 import match

                assert_that([1, 2, 3]).all_satisfy(match.is_positive())

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any item does **not** satisfy the matcher
        """
        _warn_if_vacuous("all_satisfy", self.val, allow_empty)
        return self.each(matcher, allow_empty=True)

    def none_satisfy(self, matcher: Matcher | Callable[..., bool]) -> Self:
        """Asserts that no item in val satisfies the given matcher.

        Args:
            matcher: a `Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers:

                from assertpy2 import match

                assert_that([1, 2, 3]).none_satisfy(match.is_negative())

            Usage with callables:

                assert_that([1, 2, 3]).none_satisfy(lambda x: x < 0)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any item satisfies the matcher
        """
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        if _is_matcher(matcher):
            for i, item in enumerate(self.val):
                if matcher.matches(item):
                    return self.error(
                        f"Expected no item to satisfy {matcher.describe()}, but item at index {i} <{item}> did."
                    )
        elif callable(matcher):
            for i, item in enumerate(self.val):
                if matcher(item):
                    return self.error(
                        f"Expected no item to satisfy {_describe_matcher(matcher)}, but item at index {i} <{item}> did."
                    )
        else:
            raise TypeError("given arg must be a Matcher or callable")
        return self

    def satisfies_exactly(self, *matchers: Matcher | Callable[..., bool]) -> Self:
        """Asserts that val has exactly one item per matcher, each satisfying the matcher at its position.

        Unlike [`each()`][assertpy2.base.BaseMixin.each] (one matcher applied to every item), this
        pairs the i-th item with the
        i-th matcher and additionally requires the lengths to match.  Every positional mismatch is
        reported, not just the first.

        Args:
            *matchers: one `Matcher` or callable predicate per expected item,
                applied in order

        Examples:
            Usage:

                from assertpy2 import match

                assert_that([1, "foo", 3.0]).satisfies_exactly(
                    match.is_odd(), match.is_instance_of(str), match.is_positive()
                )
                assert_that([2, 4]).satisfies_exactly(lambda x: x == 2, lambda x: x == 4)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the length differs, or any item does **not** satisfy its matcher
            TypeError: if val is not iterable, or a given arg is neither a Matcher nor callable
            ValueError: if no matchers are given
        """
        if len(matchers) == 0:
            raise ValueError("one or more args must be given")
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        items = list(self.val)
        if len(items) != len(matchers):
            return self.error(
                f"Expected collection length <{len(matchers)}>, but was <{len(items)}>.",
                actual=self.val,
                expected=[_describe_matcher(matcher) for matcher in matchers],
            )
        entries = [
            DiffEntry(path=f"[{index}]", actual=item, expected=_describe_matcher(matcher))
            for index, (item, matcher) in enumerate(zip(items, matchers, strict=True))
            if not _apply_matcher(matcher, item)
        ]
        if entries:
            failed = "item" if len(entries) == 1 else "items"
            return self.error(
                f"Expected items to satisfy the given matchers in order, but {len(entries)} {failed} did not.",
                actual=self.val,
                expected=[_describe_matcher(matcher) for matcher in matchers],
                diff=DiffResult(kind="match", entries=entries),
            )
        return self

    def satisfies_exactly_in_any_order(self, *matchers: Matcher | Callable[..., bool]) -> Self:
        """Asserts that the items and the given matchers can be paired one-to-one, in any order.

        Like [`satisfies_exactly()`][assertpy2.base.BaseMixin.satisfies_exactly] but ignoring
        positions: passes when some one-to-one assignment pairs every item with a distinct matcher
        it satisfies.  The lengths must still match, and no matcher may be reused for two items.

        Since every matcher is probed against every item, a probe that raises ``TypeError`` (a
        type-incompatible comparison on a mixed collection, like ``is_positive()`` meeting a string)
        counts as a non-match instead of crashing the pairing.  On failure, an unpaired matcher whose
        probes raised is annotated with the raise count in the diff, so a buggy predicate is not
        mistaken for an ordinary mismatch.

        Args:
            *matchers: one `Matcher` or callable predicate per expected item, in any order

        Examples:
            Usage:

                from assertpy2 import match

                assert_that(["foo", 3]).satisfies_exactly_in_any_order(
                    match.is_odd(), match.is_instance_of(str)
                )
                assert_that([2, 1]).satisfies_exactly_in_any_order(lambda x: x == 1, lambda x: x == 2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the length differs, or no one-to-one pairing satisfies all matchers
            TypeError: if val is not iterable, or a given arg is neither a Matcher nor callable
            ValueError: if no matchers are given
        """
        if len(matchers) == 0:
            raise ValueError("one or more args must be given")
        for matcher in matchers:
            if not _is_matcher(matcher) and not callable(matcher):
                raise TypeError("given arg must be a Matcher or callable")
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        items = list(self.val)
        if len(items) != len(matchers):
            return self.error(
                f"Expected collection length <{len(matchers)}>, but was <{len(items)}>.",
                actual=self.val,
                expected=[_describe_matcher(matcher) for matcher in matchers],
            )
        raised_counts = [0] * len(matchers)
        satisfied = []
        for item in items:
            row = []
            for column, matcher in enumerate(matchers):
                try:
                    row.append(_apply_matcher(matcher, item))
                except TypeError:  # noqa: PERF203  # every probe may raise independently on a mixed collection
                    raised_counts[column] += 1
                    row.append(False)
            satisfied.append(row)
        assignment = _max_bipartite_assignment(satisfied)
        unpaired_items = [index for index, column in enumerate(assignment) if column is None]
        if unpaired_items:
            paired_columns = {column for column in assignment if column is not None}
            entries = [DiffEntry(path="extra", actual=items[index], expected=None) for index in unpaired_items]
            entries.extend(
                DiffEntry(path="missing", actual=None, expected=_describe_unpaired(matcher, raised_counts[column]))
                for column, matcher in enumerate(matchers)
                if column not in paired_columns
            )
            failed = "item" if len(unpaired_items) == 1 else "items"
            return self.error(
                f"Expected items to satisfy the given matchers in any order,"
                f" but no pairing covers {len(unpaired_items)} {failed}.",
                actual=self.val,
                expected=[_describe_matcher(matcher) for matcher in matchers],
                diff=DiffResult(kind="contains", entries=entries),
            )
        return self

    def zip_satisfies(
        self, other: Iterable[object], predicate: Callable[..., bool], *, allow_empty: bool = False
    ) -> Self:
        """Asserts that each pair from zipping val with other satisfies the two-arg predicate.

        Pairs the i-th item of val with the i-th item of ``other`` and checks ``predicate(a, b)``.
        The two iterables must have equal length.  Every failing pair is reported.

        Args:
            other: the iterable to zip with val
            predicate: a two-arg callable returning a bool, applied to each ``(val_item, other_item)`` pair

        Examples:
            Usage:

                assert_that([1, 2, 3]).zip_satisfies([2, 4, 6], lambda a, b: b == a * 2)
                assert_that(["a", "bb"]).zip_satisfies([1, 2], lambda s, n: len(s) == n)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the lengths differ, or any pair does **not** satisfy the predicate
            TypeError: if val or other is not iterable, or predicate is not callable
        """
        _warn_if_vacuous("zip_satisfies", self.val, allow_empty)
        if not callable(predicate):
            raise TypeError("given predicate must be callable")
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        if not isinstance(other, collections.abc.Iterable):
            raise TypeError("given arg must be iterable")
        val_items = list(self.val)
        other_items = list(other)
        if len(val_items) != len(other_items):
            return self.error(
                f"Expected collection length <{len(other_items)}>, but was <{len(val_items)}>.",
                actual=self.val,
                expected=other,
            )
        entries = [
            DiffEntry(path=f"[{index}]", actual=val_item, expected=other_item)
            for index, (val_item, other_item) in enumerate(zip(val_items, other_items, strict=True))
            if not predicate(val_item, other_item)
        ]
        if entries:
            failed = "pair" if len(entries) == 1 else "pairs"
            return self.error(
                f"Expected paired items to satisfy <{predicate}>, but {len(entries)} {failed} did not.",
                actual=self.val,
                expected=other,
                diff=DiffResult(kind="match", entries=entries),
            )
        return self
