from __future__ import annotations

import collections.abc
from typing import TYPE_CHECKING

from ._mixin_base import _MixinBase
from .errors import DiffEntry, DiffResult
from .matchers import Matcher, StructureMatcher

if TYPE_CHECKING:
    from typing_extensions import Self

__tracebackhide__ = True


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

        Checks actual is equal to expected using the ``==`` operator. When val is *dict-like*,
        optionally ignore or include keys when checking equality.

        Args:
            other: the expected value
            **kwargs: see below

        Keyword Args:
            ignore: the dict key (or list of keys) to ignore
            include: the dict key (of list of keys) to include

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
                assert_that({'a': {'b': 2, 'c': 3, 'd': 4}}).is_equal_to({'a': {'d': 4}}, ignore=[('a', 'b'), ('a', 'c')])

            When the val is *dict-like*, only certain keys can be *included* when checking equality::

                # include a single key
                assert_that({'a': 1, 'b': 2}).is_equal_to({'a': 1}, include='a')

                # include multiple keys
                assert_that({'a': 1, 'b': 2, 'c': 3}).is_equal_to({'a': 1, 'b': 2}, include=['a', 'b'])

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
        if self._check_dict_like(self.val, check_values=False, return_as_bool=True) and self._check_dict_like(
            other, check_values=False, return_as_bool=True
        ):
            if self._dict_not_equal(self.val, other, ignore=kwargs.get("ignore"), include=kwargs.get("include")):
                self._dict_err(self.val, other, ignore=kwargs.get("ignore"), include=kwargs.get("include"))
        else:
            if self.val != other:
                return self.error(
                    f"Expected <{self.val}> to be equal to <{other}>, but was not.",
                    actual=self.val,
                    expected=other,
                    diff=DiffResult(kind="scalar", entries=[DiffEntry(path=".", actual=self.val, expected=other)]),
                )
        return self

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
                return self.error(f"Expected {matcher.describe()}, but {matcher.describe_mismatch(self.val)}.")
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
            for i, item in enumerate(self.val):
                if not matcher.matches(item):
                    return self.error(
                        f"Expected all items to satisfy {matcher.describe()}, but item at index {i} <{item}> did not:"
                        f" {matcher.describe_mismatch(item)}."
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

    def matches_structure(self, spec: dict) -> Self:
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
        if not matcher.matches(self.val):
            return self.error(
                f"Expected <{self.val}> to match structure {matcher.describe()}, but"
                f" {matcher.describe_mismatch(self.val)}."
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

    def _type(self, val):
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
            t = self._type(self.val)
            return self.error(f"Expected <{self.val}:{t}> to be of type <{some_type.__name__}>, but was not.")
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
                t = self._type(self.val)
                return self.error(
                    f"Expected <{self.val}:{t}> to be instance of class <{some_class.__name__}>, but was not."
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
