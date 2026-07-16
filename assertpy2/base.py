from __future__ import annotations

from typing import TYPE_CHECKING

from ._compare import (
    _ambiguous_array_operand,
    _array_equality_error,
    _build_compare_config,
    _guarded_equal,
    _guarded_not_equal,
    _node_decision,
)
from ._diff import _build_equality_diff
from ._introspection import is_namedtuple
from ._satisfies import SatisfiesMixin
from .errors import _disambiguated, _truncated

if TYPE_CHECKING:
    from ._compat import Self

__tracebackhide__ = True

# Atomic scalar types whose ``==`` yields a real bool and which cannot contain an array/frame-like:
# for these, ``is_equal_to`` skips the compare-config, array-operand guard, and dict-like dispatch.
# Containers (dict/list/tuple/set) are excluded - they may nest a numpy operand and need the guarded path.
_EQ_ATOMIC = frozenset({int, float, bool, complex, str, bytes, bytearray, type(None)})


class BaseMixin(SatisfiesMixin):
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
            ignore_null (bool): when ``True``, skip any named field the *expected* side leaves ``None``
                (a partial expected/template), at any depth.  Only the expected side is skipped, so an
                unexpectedly ``None`` actual field is still reported.  Defaults to ``False``.

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
        if not kwargs:
            if type(self.val) in _EQ_ATOMIC and type(other) in _EQ_ATOMIC:
                # atomic scalars: no array/dict-likeness, == yields a real bool - skip config/guards entirely
                if self.val != other:
                    actual_repr, expected_repr = _disambiguated(self.val, other)
                    return self.error(
                        f"Expected <{actual_repr}> to be equal to <{expected_repr}>, but was not.",
                        actual=self.val,
                        expected=other,
                        diff=_build_equality_diff(self.val, other),
                    )
                return self
            ignore = include = config = None
        else:
            ignore = kwargs.get("ignore")
            include = kwargs.get("include")
            config = _build_compare_config(
                kwargs.get("tolerance"), kwargs.get("comparators"), kwargs.get("ignore_null", False)
            )

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
                actual_repr, expected_repr = _disambiguated(self.val, other)
                diff = _build_equality_diff(self.val, other)
                return self.error(
                    f"Expected <{actual_repr}> to be equal to <{expected_repr}>, but was not.",
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

    def is_instance_of_any(self, *some_classes: type) -> Self:
        """Asserts that val is an instance of at least one of the given classes.

        Args:
            *some_classes: the candidate classes

        Examples:
            Usage:

                assert_that(1).is_instance_of_any(int, float)
                assert_that('foo').is_instance_of_any(str, bytes)
                assert_that(TimeoutError()).is_instance_of_any(OSError, ValueError)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** an instance of any of the given classes
            TypeError: if a given arg is not a class
            ValueError: if no classes are given
        """
        if len(some_classes) == 0:
            raise ValueError("one or more args must be given")
        try:
            if not isinstance(self.val, some_classes):
                type_name = self._type(self.val)
                class_names = ", ".join(some_class.__name__ for some_class in some_classes)
                return self.error(
                    f"Expected <{self.val}:{type_name}> to be instance of any of <{class_names}>, but was not."
                )
        except TypeError:
            raise TypeError("given args must all be classes") from None
        return self

    def is_subclass_of(self, some_class: type) -> Self:
        """Asserts that val is a class and is a subclass of the given class.

        Checks the class hierarchy using the ``issubclass()`` built-in, so a class counts as a
        subclass of itself.

        Args:
            some_class: the expected ancestor class

        Examples:
            Usage:

                assert_that(bool).is_subclass_of(int)
                assert_that(TimeoutError).is_subclass_of(OSError)

                class Base: pass
                class Derived(Base): pass

                assert_that(Derived).is_subclass_of(Base)
                assert_that(Derived).is_subclass_of(Derived)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** a subclass of the given class
            TypeError: if val or the given arg is not a class
        """
        if not isinstance(self.val, type):
            raise TypeError("val must be a class")
        try:
            if not issubclass(self.val, some_class):
                return self.error(
                    f"Expected <{self.val.__name__}> to be subclass of <{some_class.__name__}>, but was not."
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

    def is_length_between(self, low: int, high: int) -> Self:
        """Asserts that val's length is between low and high (both inclusive).

        Checks val's length using the ``len()`` built-in, like
        [`is_length()`][assertpy2.base.BaseMixin.is_length].  Identical to
        [`has_size_between()`][assertpy2.collection.CollectionMixin.has_size_between] apart from
        the error message wording.

        Args:
            low: the inclusive lower length bound
            high: the inclusive upper length bound

        Examples:
            Usage:

                assert_that('foo').is_length_between(1, 5)
                assert_that(['a', 'b']).is_length_between(2, 2)
                assert_that((1, 2, 3)).is_length_between(0, 3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val's length is **not** between low and high
            TypeError: if a given arg is not an int
            ValueError: if a given arg is negative, or low is greater than high
        """
        if type(low) is not int:
            raise TypeError("given low arg must be an int")
        if type(high) is not int:
            raise TypeError("given high arg must be an int")
        if low < 0 or high < 0:
            raise ValueError("given args must be positive ints")
        if low > high:
            raise ValueError("given low arg must be less than given high arg")
        if not low <= len(self.val) <= high:
            return self.error(
                f"Expected <{self.val}> to be of length between <{low}> and <{high}>, but was <{len(self.val)}>."
            )
        return self
