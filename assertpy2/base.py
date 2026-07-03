from __future__ import annotations

import collections.abc
from typing import TYPE_CHECKING, Any

from ._compare import (
    _ambiguous_array_operand,
    _array_equality_error,
    _build_compare_config,
    _guarded_equal,
    _guarded_not_equal,
    _node_decision,
)
from ._diff import _build_equality_diff, _walk_leaves
from ._introspection import is_model_dump_object, is_namedtuple
from ._mixin_base import _MixinBase
from .errors import DiffEntry, DiffResult, _truncated
from .matchers import IsNotNoneMatcher, Matcher, StructureMatcher, _apply_matcher, _describe_matcher

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from ._compat import Self

__tracebackhide__ = True


class BaseMixin(_MixinBase):
    """Base mixin."""

    def described_as(self, description: str) -> Self:
        """Describes the assertion.  On failure, the description is included in the error message.

        This is not an assertion itself.  But if the any of the following chained assertions fail,
        the description will be included in addition to the regular error message.

        Args:
            description: the error message description

        Examples:
            Usage:

                assert_that(1).described_as('error msg desc').is_equal_to(2)  # fails
                # [error msg desc] Expected <1> to be equal to <2>, but was not.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion
        """
        self.description = str(description)
        return self

    def is_equal_to(self, other: object, **kwargs: object) -> Self:
        """Asserts that val is equal to other.

        Checks actual is equal to expected using the ``==`` operator. When val is *dict-like*
        or has introspectable fields (dataclass, namedtuple, attrs, Pydantic model),
        optionally ignore or include keys/fields when checking equality.

        Args:
            other: the expected value
            **kwargs: see below

        Keyword Args:
            ignore (Hashable | list | set | frozenset | None): the key/field (or list/set/frozenset of
                keys/fields) to ignore.  Besides exact keys and nested-path tuples, a ``re.Pattern`` matches
                field names by regex and a ``type`` matches fields by value type.
            include (Hashable | list | set | frozenset | None): the key/field (or list/set/frozenset of
                keys/fields) to include.  Accepts the same ``re.Pattern`` / ``type`` specs as ``ignore``.
            tolerance (float | None): an absolute tolerance applied to every real-number leaf anywhere in
                the structure, so close floats compare equal (``abs(actual - expected) <= tolerance``).
            comparators (dict | None): a dict mapping a ``type`` or a field name to an
                ``(actual, expected) -> bool`` predicate that owns matching leaves; a field-name key wins
                over a type key.

        Examples:
            Usage:

                assert_that(1 + 2).is_equal_to(3)
                assert_that('foo').is_equal_to('foo')
                assert_that(123).is_equal_to(123)
                assert_that(123.4).is_equal_to(123.4)
                assert_that(['a', 'b']).is_equal_to(['a', 'b'])
                assert_that((1, 2, 3)).is_equal_to((1, 2, 3))
                assert_that({'a': 1, 'b': 2}).is_equal_to({'a': 1, 'b': 2})
                assert_that({'a', 'b'}).is_equal_to({'a', 'b'})

            When the val is *dict-like*, keys can optionally be *ignored* when checking equality:

                # ignore a single key
                assert_that({'a': 1, 'b': 2}).is_equal_to({'a': 1}, ignore='b')

                # ignore multiple keys
                assert_that({'a': 1, 'b': 2, 'c': 3}).is_equal_to({'a': 1}, ignore=['b', 'c'])

                # ignore nested keys
                assert_that({'a': {'b': 2, 'c': 3, 'd': 4}}).is_equal_to(
                    {'a': {'d': 4}}, ignore=[('a', 'b'), ('a', 'c')]
                )

            When the val is *dict-like*, only certain keys can be *included* when checking equality:

                # include a single key
                assert_that({'a': 1, 'b': 2}).is_equal_to({'a': 1}, include='a')

                # include multiple keys
                assert_that({'a': 1, 'b': 2, 'c': 3}).is_equal_to({'a': 1, 'b': 2}, include=['a', 'b'])

            Works with dataclasses, namedtuples, attrs, and Pydantic models:

                @dataclass
                class User:
                    id: int
                    name: str

                assert_that(User(id=1, name="Alice")).is_equal_to(User(id=99, name="Alice"), ignore="id")

            Compares lists of objects pairwise:

                actual = [User(id=1, name="Alice"), User(id=2, name="Bob")]
                expected = [User(id=99, name="Alice"), User(id=99, name="Bob")]
                assert_that(actual).is_equal_to(expected, ignore="id")

            Compare nested floats with an absolute tolerance, or supply custom comparators:

                assert_that({"price": 1.0001}).is_equal_to({"price": 1.0}, tolerance=0.001)

                # by type, or by field name (field name wins over type)
                assert_that(actual).is_equal_to(expected, comparators={float: lambda a, e: round(a, 2) == round(e, 2)})
                assert_that(actual).is_equal_to(expected, comparators={"name": lambda a, e: a.lower() == e.lower()})

            Ignore fields by regex or by type:

                import re

                assert_that(payload).is_equal_to(expected, ignore=re.compile(r"^_"))  # ignore private-ish keys
                assert_that(payload).is_equal_to(expected, ignore=float)               # ignore all float fields

            Failure produces a nice error message:

                assert_that(1).is_equal_to(2)  # fails
                # Expected <1> to be equal to <2>, but was not.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual is **not** equal to expected
            TypeError: if ``ignore``/``include`` is a one-shot or otherwise unsupported iterable, or is
                used on a value that is neither dict-like nor has introspectable fields; if ``tolerance`` is
                not a real number or ``comparators`` is not a dict of callables; or if val or other is (or
                contains, at any nesting depth) an element-wise array/frame-like (numpy/pandas/polars) whose
                ``==`` has no single truth value (compare the value's own equality, e.g.
                ``actual.equals(expected)``, instead)
            ValueError: if ``tolerance`` is ``NaN`` or negative

        Tip:
            Using [`is_equal_to()`][assertpy2.base.BaseMixin.is_equal_to] with a ``float`` val is just
            asking for trouble. Instead, you'll
            always want to use *fuzzy* numeric assertions
            like [`is_close_to()`][assertpy2.numeric.NumericMixin.is_close_to]
            or [`is_between()`][assertpy2.numeric.NumericMixin.is_between].

        See Also:
            [`is_equal_to_ignoring_case()`][assertpy2.string.StringMixin.is_equal_to_ignoring_case] -
                for case-insensitive string equality
        """
        ignore = kwargs.get("ignore")
        include = kwargs.get("include")
        config = _build_compare_config(kwargs.get("tolerance"), kwargs.get("comparators"))

        operand = _ambiguous_array_operand(self.val, other)
        if operand is not None:
            raise _array_equality_error("is_equal_to", operand)

        if self._is_dict_like(self.val, check_values=False) and self._is_dict_like(other, check_values=False):
            if self._dict_not_equal(self.val, other, ignore=ignore, include=include, config=config):
                self._dict_err(self.val, other, ignore=ignore, include=include, config=config)
        elif ignore or include:
            val_is_namedtuple = is_namedtuple(self.val)
            other_is_namedtuple = is_namedtuple(other)
            if (
                isinstance(self.val, (list, tuple))
                and isinstance(other, (list, tuple))
                and not val_is_namedtuple
                and not other_is_namedtuple
            ):
                self._seq_equal_with_filter(self.val, other, ignore=ignore, include=include, config=config)
            else:
                self._obj_equal_with_filter(self.val, other, ignore=ignore, include=include, config=config)
        elif config is not None:
            diff = _build_equality_diff(self.val, other, config=config)
            if diff.entries:
                return self.error(
                    f"Expected <{_truncated(str(self.val))}> to be equal to <{_truncated(str(other))}>, but was not.",
                    actual=self.val,
                    expected=other,
                    diff=diff,
                )
        else:
            if _guarded_not_equal(self.val, other):
                diff = _build_equality_diff(self.val, other)
                return self.error(
                    f"Expected <{_truncated(str(self.val))}> to be equal to <{_truncated(str(other))}>, but was not.",
                    actual=self.val,
                    expected=other,
                    diff=diff,
                )
        return self

    def _obj_equal_with_filter(self, actual, expected, *, ignore=None, include=None, config=None):
        """Compare two objects by converting to dicts and applying ignore/include filters."""
        actual_dict = self._to_comparable_dict(actual)
        expected_dict = self._to_comparable_dict(expected)
        if actual_dict is None or expected_dict is None:
            raise TypeError(
                "ignore/include requires dict-like objects or objects with introspectable fields"
                " (dataclass, namedtuple, attrs, Pydantic model, or object with __dict__)"
            )
        if self._dict_not_equal(actual_dict, expected_dict, ignore=ignore, include=include, config=config):
            self._dict_err(actual_dict, expected_dict, ignore=ignore, include=include, config=config)

    def _seq_equal_with_filter(self, actual, expected, *, ignore=None, include=None, config=None):
        """Compare two sequences pairwise, converting elements to dicts for ignore/include."""
        if len(actual) != len(expected):
            return self.error(
                f"Expected collection length <{len(expected)}>, but was <{len(actual)}>.",
                actual=actual,
                expected=expected,
            )
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected, strict=True)):
            actual_dict = self._to_comparable_dict(actual_item)
            expected_dict = self._to_comparable_dict(expected_item)
            if actual_dict is not None and expected_dict is not None:
                if self._dict_not_equal(actual_dict, expected_dict, ignore=ignore, include=include, config=config):
                    self._dict_err(actual_dict, expected_dict, ignore=ignore, include=include, config=config)
            elif _node_decision(actual_item, expected_item, config) != "equal":
                return self.error(
                    f"Expected item at index <{index}> to be equal to <{expected_item}>, but was <{actual_item}>.",
                    actual=actual_item,
                    expected=expected_item,
                )

    def all_fields_satisfy(self, matcher: Matcher | Callable[..., bool]) -> Self:
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
        if not isinstance(matcher, Matcher) and not callable(matcher):
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

    def has_no_none_fields(self) -> Self:
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
        return self.all_fields_satisfy(IsNotNoneMatcher())

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

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** satisfy the matcher
        """
        if isinstance(matcher, Matcher):
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
                return self.error(f"Expected <{self.val}> to satisfy <{matcher}>, but did not.")
        else:
            raise TypeError("given arg must be a Matcher or callable")
        return self

    def each(self, matcher: Matcher | Callable[..., bool]) -> Self:
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
        if not isinstance(self.val, collections.abc.Iterable):
            raise TypeError("val is not iterable")
        if isinstance(matcher, Matcher):
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
                        f"Expected all items to satisfy <{matcher}>, but item at index {i} <{item}> did not."
                    )
        else:
            raise TypeError("given arg must be a Matcher or callable")
        return self

    def matches_structure(self, spec: dict[Any, Any]) -> Self:
        """Asserts that val matches the given structure specification.

        ``val`` may be a dict or a pydantic-style model (anything exposing ``model_dump()``), which is
        normalized to its dict before matching.  Each key in ``spec`` maps to either a
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
        if not isinstance(self.val, dict) and not is_model_dump_object(self.val):
            raise TypeError("val must be a dict")
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
        if isinstance(matcher, Matcher):
            if not any(matcher.matches(item) for item in self.val):
                return self.error(f"Expected any item to satisfy {matcher.describe()}, but none did.")
        elif callable(matcher):
            if not any(matcher(item) for item in self.val):
                return self.error(f"Expected any item to satisfy <{matcher}>, but none did.")
        else:
            raise TypeError("given arg must be a Matcher or callable")
        return self

    def all_satisfy(self, matcher: Matcher | Callable[..., bool]) -> Self:
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
        return self.each(matcher)

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
        if isinstance(matcher, Matcher):
            for i, item in enumerate(self.val):
                if matcher.matches(item):
                    return self.error(
                        f"Expected no item to satisfy {matcher.describe()}, but item at index {i} <{item}> did."
                    )
        elif callable(matcher):
            for i, item in enumerate(self.val):
                if matcher(item):
                    return self.error(f"Expected no item to satisfy <{matcher}>, but item at index {i} <{item}> did.")
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

    def zip_satisfies(self, other: Iterable[object], predicate: Callable[..., bool]) -> Self:
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

    def is_not_equal_to(self, other: object) -> Self:
        """Asserts that val is not equal to other.

        Checks actual is not equal to expected using the ``!=`` operator.

        Args:
            other: the expected value

        Examples:
            Usage:

                assert_that(1 + 2).is_not_equal_to(4)
                assert_that('foo').is_not_equal_to('bar')
                assert_that(123).is_not_equal_to(456)
                assert_that(123.4).is_not_equal_to(567.8)
                assert_that(['a', 'b']).is_not_equal_to(['c', 'd'])
                assert_that((1, 2, 3)).is_not_equal_to((1, 2, 4))
                assert_that({'a': 1, 'b': 2}).is_not_equal_to({'a': 1, 'b': 3})
                assert_that({'a', 'b'}).is_not_equal_to({'a', 'x'})

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual **is** equal to expected
            TypeError: if val or other is (or contains, at any nesting depth) an element-wise
                array/frame-like (numpy/pandas/polars) whose ``==`` has no single truth value; compare
                the value's own equality instead
        """
        operand = _ambiguous_array_operand(self.val, other)
        if operand is not None:
            raise _array_equality_error("is_not_equal_to", operand)

        if _guarded_equal(self.val, other, method="is_not_equal_to"):
            return self.error(
                f"Expected <{_truncated(str(self.val))}> to be not equal to <{_truncated(str(other))}>, but was."
            )
        return self

    def is_same_as(self, other: object) -> Self:
        """Asserts that val is identical to other.

        Checks actual is identical to expected using the ``is`` operator.

        Args:
            other: the expected value

        Examples:
            Basic types are identical:

                assert_that(1).is_same_as(1)
                assert_that('foo').is_same_as('foo')
                assert_that(123.4).is_same_as(123.4)

            As are immutables like ``tuple``:

                assert_that((1, 2, 3)).is_same_as((1, 2, 3))

            But mutable collections like ``list``, ``dict``, and ``set`` are not:

                # these all fail...
                assert_that(['a', 'b']).is_same_as(['a', 'b'])  # fails
                assert_that({'a': 1, 'b': 2}).is_same_as({'a': 1, 'b': 2})  # fails
                assert_that({'a', 'b'}).is_same_as({'a', 'b'})  # fails

            Unless they are the same object:

                x = {'a': 1, 'b': 2}
                y = x
                assert_that(x).is_same_as(y)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual is **not** identical to expected
        """
        if self.val is not other:
            return self.error(f"Expected <{self.val}> to be identical to <{other}>, but was not.")
        return self

    def is_not_same_as(self, other: object) -> Self:
        """Asserts that val is not identical to other.

        Checks actual is not identical to expected using the ``is`` operator.

        Args:
            other: the expected value

        Examples:
            Usage:

                assert_that(1).is_not_same_as(2)
                assert_that('foo').is_not_same_as('bar')
                assert_that(123.4).is_not_same_as(567.8)
                assert_that((1, 2, 3)).is_not_same_as((1, 2, 4))

                # mutable collections, even if equal, are not identical...
                assert_that(['a', 'b']).is_not_same_as(['a', 'b'])
                assert_that({'a': 1, 'b': 2}).is_not_same_as({'a': 1, 'b': 2})
                assert_that({'a', 'b'}).is_not_same_as({'a', 'b'})

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual **is** identical to expected
        """
        if self.val is other:
            return self.error(f"Expected <{self.val}> to be not identical to <{other}>, but was.")
        return self

    def is_true(self) -> Self:
        """Asserts that val is true.

        Examples:
            Usage:

                assert_that(True).is_true()
                assert_that(1).is_true()
                assert_that('foo').is_true()
                assert_that(1.0).is_true()
                assert_that(['a', 'b']).is_true()
                assert_that((1, 2, 3)).is_true()
                assert_that({'a': 1, 'b': 2}).is_true()
                assert_that({'a', 'b'}).is_true()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** false
        """
        if not self.val:
            return self.error(f"Expected <{self.val}> to be <True>, but was not.")
        return self

    def is_false(self) -> Self:
        """Asserts that val is false.

        Examples:
            Usage:

                assert_that(False).is_false()
                assert_that(0).is_false()
                assert_that('').is_false()
                assert_that(0.0).is_false()
                assert_that([]).is_false()
                assert_that(()).is_false()
                assert_that({}).is_false()
                assert_that(set()).is_false()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** true
        """
        if self.val:
            return self.error(f"Expected <{self.val}> to be <False>, but was not.")
        return self

    def is_none(self) -> Self:
        """Asserts that val is none.

        Examples:
            Usage:

                assert_that(None).is_none()
                assert_that(print('hello world')).is_none()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** none
        """
        if self.val is not None:
            return self.error(f"Expected <{self.val}> to be <None>, but was not.")
        return self

    def is_not_none(self) -> Self:
        """Asserts that val is not none.

        Examples:
            Usage:

                assert_that(0).is_not_none()
                assert_that('foo').is_not_none()
                assert_that(False).is_not_none()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** none
        """
        if self.val is None:
            return self.error("Expected not <None>, but was.")
        return self

    @staticmethod
    def _type(val):
        if hasattr(val, "__name__"):
            return val.__name__
        return val.__class__.__name__

    def is_type_of(self, some_type) -> Self:
        """Asserts that val is of the given type.

        Args:
            some_type (type): the expected type

        Examples:
            Usage:

                assert_that(1).is_type_of(int)
                assert_that('foo').is_type_of(str)
                assert_that(123.4).is_type_of(float)
                assert_that(['a', 'b']).is_type_of(list)
                assert_that((1, 2, 3)).is_type_of(tuple)
                assert_that({'a': 1, 'b': 2}).is_type_of(dict)
                assert_that({'a', 'b'}).is_type_of(set)
                assert_that(True).is_type_of(bool)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** of the given type
        """
        if type(some_type) is not type and not issubclass(type(some_type), type):
            raise TypeError("given arg must be a type")
        if type(self.val) is not some_type:
            type_name = self._type(self.val)
            return self.error(f"Expected <{self.val}:{type_name}> to be of type <{some_type.__name__}>, but was not.")
        return self

    def is_instance_of(self, some_class: type) -> Self:
        """Asserts that val is an instance of the given class.

        Args:
            some_class: the expected class

        Examples:
            Usage:

                assert_that(1).is_instance_of(int)
                assert_that('foo').is_instance_of(str)
                assert_that(123.4).is_instance_of(float)
                assert_that(['a', 'b']).is_instance_of(list)
                assert_that((1, 2, 3)).is_instance_of(tuple)
                assert_that({'a': 1, 'b': 2}).is_instance_of(dict)
                assert_that({'a', 'b'}).is_instance_of(set)
                assert_that(True).is_instance_of(bool)

            With a user-defined class:

                class Foo: pass
                f = Foo()
                assert_that(f).is_instance_of(Foo)
                assert_that(f).is_instance_of(object)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** an instance of the given class
        """
        try:
            if not isinstance(self.val, some_class):
                type_name = self._type(self.val)
                return self.error(
                    f"Expected <{self.val}:{type_name}> to be instance of class <{some_class.__name__}>, but was not."
                )
        except TypeError:
            raise TypeError("given arg must be a class") from None
        return self

    def is_length(self, length) -> Self:
        """Asserts that val is the given length.

        Checks val is the given length using the ``len()`` built-in.

        Args:
            length (int): the expected length

        Examples:
            Usage:

                assert_that('foo').is_length(3)
                assert_that(['a', 'b']).is_length(2)
                assert_that((1, 2, 3)).is_length(3)
                assert_that({'a': 1, 'b': 2}).is_length(2)
                assert_that({'a', 'b'}).is_length(2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** the given length
        """
        if type(length) is not int:
            raise TypeError("given arg must be an int")
        if length < 0:
            raise ValueError("given arg must be a positive int")
        if len(self.val) != length:
            return self.error(f"Expected <{self.val}> to be of length <{length}>, but was <{len(self.val)}>.")
        return self
