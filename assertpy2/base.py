from __future__ import annotations

import collections.abc
import dataclasses
from typing import TYPE_CHECKING, Any, Final

from ._introspection import is_model_dump_object, is_namedtuple
from ._mixin_base import _MixinBase
from .errors import DiffEntry, DiffResult
from .matchers import Matcher, StructureMatcher

if TYPE_CHECKING:
    from ._compat import Self

__tracebackhide__ = True

_SENTINEL: Final = object()


class BaseMixin(_MixinBase):
    """Base mixin."""

    def described_as(self, description) -> Self:
        """Describes the assertion.  On failure, the description is included in the error message.

        This is not an assertion itself.  But if the any of the following chained assertions fail,
        the description will be included in addition to the regular error message.

        Args:
            description: the error message description

        Examples:
            Usage::

                assert_that(1).described_as('error msg desc').is_equal_to(2)  # fails
                # [error msg desc] Expected <1> to be equal to <2>, but was not.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion
        """
        self.description = str(description)
        return self

    def is_equal_to(self, other, **kwargs) -> Self:
        """Asserts that val is equal to other.

        Checks actual is equal to expected using the ``==`` operator. When val is *dict-like*
        or has introspectable fields (dataclass, namedtuple, attrs, Pydantic model),
        optionally ignore or include keys/fields when checking equality.

        Args:
            other: the expected value
            **kwargs: see below

        Keyword Args:
            ignore: the key/field (or list of keys/fields) to ignore
            include: the key/field (or list of keys/fields) to include

        Examples:
            Usage::

                assert_that(1 + 2).is_equal_to(3)
                assert_that('foo').is_equal_to('foo')
                assert_that(123).is_equal_to(123)
                assert_that(123.4).is_equal_to(123.4)
                assert_that(['a', 'b']).is_equal_to(['a', 'b'])
                assert_that((1, 2, 3)).is_equal_to((1, 2, 3))
                assert_that({'a': 1, 'b': 2}).is_equal_to({'a': 1, 'b': 2})
                assert_that({'a', 'b'}).is_equal_to({'a', 'b'})

            When the val is *dict-like*, keys can optionally be *ignored* when checking equality::

                # ignore a single key
                assert_that({'a': 1, 'b': 2}).is_equal_to({'a': 1}, ignore='b')

                # ignore multiple keys
                assert_that({'a': 1, 'b': 2, 'c': 3}).is_equal_to({'a': 1}, ignore=['b', 'c'])

                # ignore nested keys
                assert_that({'a': {'b': 2, 'c': 3, 'd': 4}}).is_equal_to(
                    {'a': {'d': 4}}, ignore=[('a', 'b'), ('a', 'c')]
                )

            When the val is *dict-like*, only certain keys can be *included* when checking equality::

                # include a single key
                assert_that({'a': 1, 'b': 2}).is_equal_to({'a': 1}, include='a')

                # include multiple keys
                assert_that({'a': 1, 'b': 2, 'c': 3}).is_equal_to({'a': 1, 'b': 2}, include=['a', 'b'])

            Works with dataclasses, namedtuples, attrs, and Pydantic models::

                @dataclass
                class User:
                    id: int
                    name: str

                assert_that(User(id=1, name="Alice")).is_equal_to(User(id=99, name="Alice"), ignore="id")

            Compares lists of objects pairwise::

                actual = [User(id=1, name="Alice"), User(id=2, name="Bob")]
                expected = [User(id=99, name="Alice"), User(id=99, name="Bob")]
                assert_that(actual).is_equal_to(expected, ignore="id")

            Failure produces a nice error message::

                assert_that(1).is_equal_to(2)  # fails
                # Expected <1> to be equal to <2>, but was not.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual is **not** equal to expected

        Tip:
            Using :meth:`is_equal_to` with a ``float`` val is just asking for trouble. Instead, you'll
            always want to use *fuzzy* numeric assertions like :meth:`~assertpy.numeric.NumericMixin.is_close_to`
            or :meth:`~assertpy.numeric.NumericMixin.is_between`.

        See Also:
            :meth:`~assertpy.string.StringMixin.is_equal_to_ignoring_case` - for case-insensitive string equality
        """
        ignore = kwargs.get("ignore")
        include = kwargs.get("include")

        if self._is_dict_like(self.val, check_values=False) and self._is_dict_like(other, check_values=False):
            if self._dict_not_equal(self.val, other, ignore=ignore, include=include):
                self._dict_err(self.val, other, ignore=ignore, include=include)
        elif ignore or include:
            val_is_namedtuple = is_namedtuple(self.val)
            other_is_namedtuple = is_namedtuple(other)
            if (
                isinstance(self.val, (list, tuple))
                and isinstance(other, (list, tuple))
                and not val_is_namedtuple
                and not other_is_namedtuple
            ):
                self._seq_equal_with_filter(self.val, other, ignore=ignore, include=include)
            else:
                self._obj_equal_with_filter(self.val, other, ignore=ignore, include=include)
        else:
            if self.val != other:
                diff = self._build_equality_diff(self.val, other)
                return self.error(
                    f"Expected <{self.val}> to be equal to <{other}>, but was not.",
                    actual=self.val,
                    expected=other,
                    diff=diff,
                )
        return self

    def _obj_equal_with_filter(self, actual, expected, *, ignore=None, include=None):
        """Compare two objects by converting to dicts and applying ignore/include filters."""
        actual_dict = self._to_comparable_dict(actual)
        expected_dict = self._to_comparable_dict(expected)
        if actual_dict is None or expected_dict is None:
            raise TypeError(
                "ignore/include requires dict-like objects or objects with introspectable fields"
                " (dataclass, namedtuple, attrs, Pydantic model, or object with __dict__)"
            )
        if self._dict_not_equal(actual_dict, expected_dict, ignore=ignore, include=include):
            self._dict_err(actual_dict, expected_dict, ignore=ignore, include=include)

    def _seq_equal_with_filter(self, actual, expected, *, ignore=None, include=None):
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
                if self._dict_not_equal(actual_dict, expected_dict, ignore=ignore, include=include):
                    self._dict_err(actual_dict, expected_dict, ignore=ignore, include=include)
            elif actual_item != expected_item:
                return self.error(
                    f"Expected item at index <{index}> to be equal to <{expected_item}>, but was <{actual_item}>.",
                    actual=actual_item,
                    expected=expected_item,
                )

    @staticmethod
    def _build_equality_diff(
        actual: object, expected: object, *, _prefix: str = "", _seen: set[int] | None = None
    ) -> DiffResult:
        if _seen is None:
            _seen = set()
        pair_key = (id(actual), id(expected))
        if pair_key[0] in _seen or pair_key[1] in _seen:
            return DiffResult(
                kind="scalar",
                entries=[DiffEntry(path=_prefix or ".", actual="<circular ref>", expected="<circular ref>")],
            )
        _seen = _seen | {pair_key[0], pair_key[1]}

        def _field_entries(actual_value: object, expected_value: object, path: str) -> list[DiffEntry]:
            sub_entries = BaseMixin._sub_diff_entries(actual_value, expected_value, path, _seen=_seen)
            if sub_entries is not None:
                return sub_entries
            return [DiffEntry(path=path, actual=actual_value, expected=expected_value)]

        if is_namedtuple(actual) and is_namedtuple(expected):
            entries: list[DiffEntry] = []
            for field in actual._fields:
                actual_value = getattr(actual, field)
                expected_value = getattr(expected, field, _SENTINEL)
                path = f"{_prefix}.{field}"
                if expected_value is _SENTINEL:
                    entries.append(DiffEntry(path=path, actual=actual_value, expected=None))
                elif actual_value != expected_value:
                    entries.extend(_field_entries(actual_value, expected_value, path))
            entries.extend(
                DiffEntry(path=f"{_prefix}.{field}", actual=None, expected=getattr(expected, field))
                for field in expected._fields
                if not hasattr(actual, field)
            )
            return DiffResult(kind="namedtuple", entries=entries)
        if (
            dataclasses.is_dataclass(actual)
            and not isinstance(actual, type)
            and dataclasses.is_dataclass(expected)
            and not isinstance(expected, type)
        ):
            entries = []
            actual_names = {field.name for field in dataclasses.fields(actual)}
            expected_names = {field.name for field in dataclasses.fields(expected)}
            for field in sorted(actual_names | expected_names):
                path = f"{_prefix}.{field}"
                if field not in expected_names:
                    entries.append(DiffEntry(path=path, actual=getattr(actual, field), expected=None))
                elif field not in actual_names:
                    entries.append(DiffEntry(path=path, actual=None, expected=getattr(expected, field)))
                else:
                    actual_value = getattr(actual, field)
                    expected_value = getattr(expected, field)
                    if actual_value != expected_value:
                        entries.extend(_field_entries(actual_value, expected_value, path))
            return DiffResult(kind="dataclass", entries=entries)
        if is_model_dump_object(actual) and is_model_dump_object(expected):
            actual_dict = actual.model_dump()
            expected_dict = expected.model_dump()
            entries = []
            for key in sorted(set(actual_dict) | set(expected_dict)):
                path = f"{_prefix}.{key}" if _prefix else f".{key}"
                if key not in expected_dict:
                    entries.append(DiffEntry(path=path, actual=actual_dict[key], expected=None))
                elif key not in actual_dict:
                    entries.append(DiffEntry(path=path, actual=None, expected=expected_dict[key]))
                elif actual_dict[key] != expected_dict[key]:
                    sub_entries = BaseMixin._sub_diff_entries(actual_dict[key], expected_dict[key], path, _seen=_seen)
                    if sub_entries is not None:
                        entries.extend(sub_entries)
                    else:
                        entries.append(DiffEntry(path=path, actual=actual_dict[key], expected=expected_dict[key]))
            return DiffResult(kind="model", entries=entries)
        if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
            entries = []
            max_len = max(len(actual), len(expected))
            for i in range(max_len):
                path = f"{_prefix}[{i}]" if _prefix else f"[{i}]"
                if i >= len(actual):
                    entries.append(DiffEntry(path=path, actual=None, expected=expected[i]))
                elif i >= len(expected):
                    entries.append(DiffEntry(path=path, actual=actual[i], expected=None))
                elif actual[i] != expected[i]:
                    sub_entries = BaseMixin._sub_diff_entries(actual[i], expected[i], path, _seen=_seen)
                    if sub_entries:
                        entries.extend(sub_entries)
                    else:
                        entries.append(DiffEntry(path=path, actual=actual[i], expected=expected[i]))
            return DiffResult(kind="sequence", entries=entries)
        if isinstance(actual, (set, frozenset)) and isinstance(expected, (set, frozenset)):
            entries = []
            for item in sorted(actual - expected, key=repr):
                entries.append(DiffEntry(path="extra", actual=item, expected=None))
            for item in sorted(expected - actual, key=repr):
                entries.append(DiffEntry(path="missing", actual=None, expected=item))
            return DiffResult(kind="set", entries=entries)
        if isinstance(actual, str) and isinstance(expected, str):
            entries = []
            actual_lines = actual.splitlines()
            expected_lines = expected.splitlines()
            max_len = max(len(actual_lines), len(expected_lines))
            for i in range(max_len):
                if i >= len(actual_lines):
                    entries.append(DiffEntry(path=f"line {i + 1}", actual=None, expected=expected_lines[i]))
                elif i >= len(expected_lines):
                    entries.append(DiffEntry(path=f"line {i + 1}", actual=actual_lines[i], expected=None))
                elif actual_lines[i] != expected_lines[i]:
                    entries.append(DiffEntry(path=f"line {i + 1}", actual=actual_lines[i], expected=expected_lines[i]))
            if not entries:
                entries.append(DiffEntry(path=".", actual=actual, expected=expected))
            return DiffResult(kind="string", entries=entries)
        return DiffResult(kind="scalar", entries=[DiffEntry(path=_prefix or ".", actual=actual, expected=expected)])

    @staticmethod
    def _sub_diff_entries(
        actual: object, expected: object, prefix: str, *, _seen: set[int] | None = None
    ) -> list[DiffEntry] | None:
        if _seen is None:
            _seen = set()
        if id(actual) in _seen or id(expected) in _seen:
            return [DiffEntry(path=prefix, actual="<circular ref>", expected="<circular ref>")]

        if isinstance(actual, dict) and isinstance(expected, dict):
            child_seen = _seen | {id(actual), id(expected)}
            entries: list[DiffEntry] = []
            for key in sorted(set(actual) | set(expected), key=repr):
                path = f"{prefix}.{key}"
                if key not in expected:
                    entries.append(DiffEntry(path=path, actual=actual[key], expected=None))  # ty: ignore[invalid-argument-type]
                elif key not in actual:
                    entries.append(DiffEntry(path=path, actual=None, expected=expected[key]))  # ty: ignore[invalid-argument-type]
                elif actual[key] != expected[key]:  # ty: ignore[invalid-argument-type]
                    sub_entries = BaseMixin._sub_diff_entries(actual[key], expected[key], path, _seen=child_seen)  # ty: ignore[invalid-argument-type]
                    if sub_entries is not None:
                        entries.extend(sub_entries)
                    else:
                        entries.append(DiffEntry(path=path, actual=actual[key], expected=expected[key]))  # ty: ignore[invalid-argument-type]
            return entries or None
        if (
            dataclasses.is_dataclass(actual)
            and not isinstance(actual, type)
            and dataclasses.is_dataclass(expected)
            and not isinstance(expected, type)
        ):
            child_seen = _seen | {id(actual), id(expected)}
            entries = []
            for field in dataclasses.fields(actual):
                actual_value = getattr(actual, field.name)
                expected_value = getattr(expected, field.name, _SENTINEL)
                if expected_value is _SENTINEL:
                    entries.append(DiffEntry(path=f"{prefix}.{field.name}", actual=actual_value, expected=None))
                elif actual_value != expected_value:
                    sub_entries = BaseMixin._sub_diff_entries(
                        actual_value, expected_value, f"{prefix}.{field.name}", _seen=child_seen
                    )
                    if sub_entries is not None:
                        entries.extend(sub_entries)
                    else:
                        entries.append(
                            DiffEntry(path=f"{prefix}.{field.name}", actual=actual_value, expected=expected_value)
                        )
            return entries or None
        if is_namedtuple(actual) and is_namedtuple(expected):
            child_seen = _seen | {id(actual), id(expected)}
            entries = []
            for field_name in actual._fields:
                actual_value = getattr(actual, field_name)
                expected_value = getattr(expected, field_name, _SENTINEL)
                if expected_value is _SENTINEL:
                    entries.append(DiffEntry(path=f"{prefix}.{field_name}", actual=actual_value, expected=None))
                elif actual_value != expected_value:
                    sub_entries = BaseMixin._sub_diff_entries(
                        actual_value, expected_value, f"{prefix}.{field_name}", _seen=child_seen
                    )
                    if sub_entries is not None:
                        entries.extend(sub_entries)
                    else:
                        entries.append(
                            DiffEntry(path=f"{prefix}.{field_name}", actual=actual_value, expected=expected_value)
                        )
            for field_name in expected._fields:
                if not hasattr(actual, field_name):
                    entries.append(
                        DiffEntry(path=f"{prefix}.{field_name}", actual=None, expected=getattr(expected, field_name))
                    )
            return entries or None
        if is_model_dump_object(actual) and is_model_dump_object(expected):
            child_seen = _seen | {id(actual), id(expected)}
            actual_dict = actual.model_dump()
            expected_dict = expected.model_dump()
            entries = []
            for key in sorted(set(actual_dict) | set(expected_dict)):
                path = f"{prefix}.{key}"
                if key not in expected_dict:
                    entries.append(DiffEntry(path=path, actual=actual_dict[key], expected=None))
                elif key not in actual_dict:
                    entries.append(DiffEntry(path=path, actual=None, expected=expected_dict[key]))
                elif actual_dict[key] != expected_dict[key]:
                    sub_entries = BaseMixin._sub_diff_entries(
                        actual_dict[key], expected_dict[key], path, _seen=child_seen
                    )
                    if sub_entries is not None:
                        entries.extend(sub_entries)
                    else:
                        entries.append(DiffEntry(path=path, actual=actual_dict[key], expected=expected_dict[key]))
            return entries or None
        return None

    def satisfies(self, matcher) -> Self:
        """Asserts that val satisfies the given matcher.

        Args:
            matcher: a :class:`~assertpy2.matchers.Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers::

                from assertpy2 import match

                assert_that(7).satisfies(match.greater_than(5) & match.less_than(10))
                assert_that('hello').satisfies(match.starts_with('he'))

            Usage with callables::

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

    def each(self, matcher) -> Self:
        """Asserts that every item in val satisfies the given matcher.

        Args:
            matcher: a :class:`~assertpy2.matchers.Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers::

                from assertpy2 import match

                assert_that([1, 2, 3]).each(match.is_positive())
                assert_that([10, 20, 30]).each(match.between(1, 100))

            Usage with extracting::

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
        """Asserts that val is a dict matching the given structure specification.

        Each key in ``spec`` maps to either a :class:`~assertpy2.matchers.Matcher`, a raw value
        (checked via ``==``), or a nested ``dict`` for recursive matching.  Extra keys in val
        that are absent from the spec are allowed.

        Args:
            spec: a dict where values can be Matcher instances, raw values, or nested dicts

        Examples:
            Usage::

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
        if not isinstance(self.val, dict):
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
            Usage::

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
            Usage::

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

    def any_satisfy(self, matcher) -> Self:
        """Asserts that at least one item in val satisfies the given matcher.

        Args:
            matcher: a :class:`~assertpy2.matchers.Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers::

                from assertpy2 import match

                assert_that([1, -2, 3]).any_satisfy(match.is_negative())

            Usage with callables::

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

    def all_satisfy(self, matcher) -> Self:
        """Asserts that all items in val satisfy the given matcher.

        Semantic alias for :meth:`each`.

        Args:
            matcher: a :class:`~assertpy2.matchers.Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers::

                from assertpy2 import match

                assert_that([1, 2, 3]).all_satisfy(match.is_positive())

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any item does **not** satisfy the matcher
        """
        return self.each(matcher)

    def none_satisfy(self, matcher) -> Self:
        """Asserts that no item in val satisfies the given matcher.

        Args:
            matcher: a :class:`~assertpy2.matchers.Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers::

                from assertpy2 import match

                assert_that([1, 2, 3]).none_satisfy(match.is_negative())

            Usage with callables::

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

    def is_not_equal_to(self, other) -> Self:
        """Asserts that val is not equal to other.

        Checks actual is not equal to expected using the ``!=`` operator.

        Args:
            other: the expected value

        Examples:
            Usage::

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
        """
        if self.val == other:
            return self.error(f"Expected <{self.val}> to be not equal to <{other}>, but was.")
        return self

    def is_same_as(self, other) -> Self:
        """Asserts that val is identical to other.

        Checks actual is identical to expected using the ``is`` operator.

        Args:
            other: the expected value

        Examples:
            Basic types are identical::

                assert_that(1).is_same_as(1)
                assert_that('foo').is_same_as('foo')
                assert_that(123.4).is_same_as(123.4)

            As are immutables like ``tuple``::

                assert_that((1, 2, 3)).is_same_as((1, 2, 3))

            But mutable collections like ``list``, ``dict``, and ``set`` are not::

                # these all fail...
                assert_that(['a', 'b']).is_same_as(['a', 'b'])  # fails
                assert_that({'a': 1, 'b': 2}).is_same_as({'a': 1, 'b': 2})  # fails
                assert_that({'a', 'b'}).is_same_as({'a', 'b'})  # fails

            Unless they are the same object::

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

    def is_not_same_as(self, other) -> Self:
        """Asserts that val is not identical to other.

        Checks actual is not identical to expected using the ``is`` operator.

        Args:
            other: the expected value

        Examples:
            Usage::

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
            Usage::

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
            Usage::

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
            Usage::

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
            Usage::

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
            Usage::

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

    def is_instance_of(self, some_class) -> Self:
        """Asserts that val is an instance of the given class.

        Args:
            some_class: the expected class

        Examples:
            Usage::

                assert_that(1).is_instance_of(int)
                assert_that('foo').is_instance_of(str)
                assert_that(123.4).is_instance_of(float)
                assert_that(['a', 'b']).is_instance_of(list)
                assert_that((1, 2, 3)).is_instance_of(tuple)
                assert_that({'a': 1, 'b': 2}).is_instance_of(dict)
                assert_that({'a', 'b'}).is_instance_of(set)
                assert_that(True).is_instance_of(bool)

            With a user-defined class::

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
            Usage::

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
