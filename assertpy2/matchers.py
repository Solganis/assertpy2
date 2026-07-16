from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from ._matcher_impls import (
    AllOfMatcher,
    AnyOfMatcher,
    BetweenMatcher,
    CloseToMatcher,
    ContainsStringMatcher,
    EachMatcher,
    EndsWithMatcher,
    EqualToMatcher,
    GreaterThanMatcher,
    GreaterThanOrEqualToMatcher,
    HasLengthMatcher,
    HasPropertyMatcher,
    IgnoreMatcher,
    IsAfterMatcher,
    IsBeforeMatcher,
    IsCallableMatcher,
    IsDivisibleByMatcher,
    IsEmptyMatcher,
    IsEvenMatcher,
    IsFalsyMatcher,
    IsInMatcher,
    IsInstanceOfMatcher,
    IsNegativeMatcher,
    IsNoneMatcher,
    IsNonEmptyStringMatcher,
    IsNotEmptyMatcher,
    IsNotNoneMatcher,
    IsNowMatcher,
    IsOddMatcher,
    IsPositiveMatcher,
    IsTruthyMatcher,
    IsUuidMatcher,
    IsZeroMatcher,
    LessThanMatcher,
    LessThanOrEqualToMatcher,
    MatchesRegexMatcher,
    NotMatcher,
    StartsWithMatcher,
    StructureMatcher,
    _is_matcher,
)
from ._matcher_impls import (
    BaseMatcher as BaseMatcher,
)
from ._matcher_impls import (
    Matcher as Matcher,
)

if TYPE_CHECKING:
    from collections.abc import Callable


# --- Matcher application helpers ---


def _apply_matcher(matcher: Matcher | Callable[..., object], value: object) -> bool:
    """Evaluate a ``Matcher`` or one-arg callable against ``value``.

    Shared resolution for every assertion that accepts either a `Matcher` or a callable
    predicate, mirroring the dispatch in ``satisfies``/``each``: a `Matcher` is checked via
    ``matches``, a callable via its return value, and anything else raises ``TypeError``.
    """
    if _is_matcher(matcher):
        return matcher.matches(value)
    if callable(matcher):
        return bool(matcher(value))
    raise TypeError("given arg must be a Matcher or callable")


def _describe_callable(predicate: Callable[..., object]) -> str:
    """A readable, deterministic name for a predicate callable in a message.

    Avoids the ``<function <lambda> at 0x...>`` repr, whose address is noise that changes every run,
    while keeping a named function's name (the useful part) and still flagging a lambda as a lambda.
    """
    name = getattr(predicate, "__name__", None)
    if name == "<lambda>":
        return "a lambda predicate"
    if name:
        return f"predicate {name}()"
    return "the given predicate"


def _describe_matcher(matcher: Matcher | Callable[..., object]) -> str:
    """Describe a ``Matcher`` or callable for the "expected" half of an error or diff entry."""
    if _is_matcher(matcher):
        return matcher.describe()
    return _describe_callable(matcher)


# --- Custom matcher registry ---

_custom_matchers: dict[str, Callable[..., BaseMatcher]] = {}
_custom_matchers_lock = threading.Lock()


def register_matcher(name: str) -> Callable[[Callable[..., BaseMatcher]], Callable[..., BaseMatcher]]:
    """Register a custom matcher factory on the ``match`` namespace.

    Args:
        name: the name to register on ``match`` (e.g. ``"is_valid_email"``)

    Returns:
        A decorator that registers the wrapped function and returns it unchanged.

    Examples:
        Register a simple matcher:

            @register_matcher("is_valid_email")
            def is_valid_email():
                return match.matches_regex(r"^[\\w.-]+@[\\w.-]+\\.\\w+$")

            assert_that(email).satisfies(match.is_valid_email())

        Register a parametrised matcher:

            @register_matcher("has_status")
            def has_status(expected: str):
                return match.has_property("status", match.equal_to(expected))

            assert_that(order).satisfies(match.has_status("active"))
    """
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    if not name.isidentifier():
        raise ValueError(f"name must be a valid Python identifier, got {name!r}")

    def decorator(func: Callable[..., BaseMatcher]) -> Callable[..., BaseMatcher]:
        if not callable(func):
            raise TypeError("func must be callable")
        with _custom_matchers_lock:
            _custom_matchers[name] = func
        return func

    return decorator


def unregister_matcher(name: str) -> None:
    """Remove a previously registered custom matcher.

    Args:
        name: the matcher name to remove

    Raises:
        KeyError: if the name is not registered
    """
    with _custom_matchers_lock:
        if name not in _custom_matchers:
            raise KeyError(f"no custom matcher registered with name {name!r}")
        del _custom_matchers[name]


def clear_custom_matchers() -> None:
    """Remove all registered custom matchers."""
    with _custom_matchers_lock:
        _custom_matchers.clear()


# --- Namespace ---


class _MatchNamespace:
    """Factory namespace for creating matcher instances.

    Usage:

        from assertpy2 import match

        assert_that(value).satisfies(match.greater_than(5) & match.less_than(10))
        assert_that(items).each(match.is_positive())
    """

    @staticmethod
    def equal_to(expected: object) -> EqualToMatcher:
        """Matcher for a value equal to ``expected``."""
        return EqualToMatcher(expected)

    @staticmethod
    def greater_than(val: object) -> GreaterThanMatcher:
        """Matcher for a value greater than ``val``."""
        return GreaterThanMatcher(val)

    @staticmethod
    def greater_than_or_equal_to(val: object) -> GreaterThanOrEqualToMatcher:
        """Matcher for a value greater than or equal to ``val``."""
        return GreaterThanOrEqualToMatcher(val)

    @staticmethod
    def less_than(val: object) -> LessThanMatcher:
        """Matcher for a value less than ``val``."""
        return LessThanMatcher(val)

    @staticmethod
    def less_than_or_equal_to(val: object) -> LessThanOrEqualToMatcher:
        """Matcher for a value less than or equal to ``val``."""
        return LessThanOrEqualToMatcher(val)

    @staticmethod
    def between(low: object, high: object) -> BetweenMatcher:
        """Matcher for a value in the inclusive range ``low`` to ``high``."""
        return BetweenMatcher(low, high)

    @staticmethod
    def close_to(expected: object, tolerance: object) -> CloseToMatcher:
        """Matcher for a value within ``tolerance`` of ``expected`` (``abs(value - expected) <= tolerance``).

        Args:
            expected: the target value
            tolerance: the maximum allowed absolute difference from ``expected``
        """
        return CloseToMatcher(expected, tolerance)

    @staticmethod
    def is_none() -> IsNoneMatcher:
        """Matcher for ``None``."""
        return IsNoneMatcher()

    @staticmethod
    def is_not_none() -> IsNotNoneMatcher:
        """Matcher for any value that is not ``None``."""
        return IsNotNoneMatcher()

    @staticmethod
    def is_instance_of(expected_type: type) -> IsInstanceOfMatcher:
        """Matcher for an instance of ``expected_type`` (via ``isinstance``)."""
        return IsInstanceOfMatcher(expected_type)

    @staticmethod
    def is_truthy() -> IsTruthyMatcher:
        """Matcher for a truthy value."""
        return IsTruthyMatcher()

    @staticmethod
    def is_falsy() -> IsFalsyMatcher:
        """Matcher for a falsy value."""
        return IsFalsyMatcher()

    @staticmethod
    def has_length(length: int) -> HasLengthMatcher:
        """Matcher for a value whose ``len()`` equals ``length``."""
        return HasLengthMatcher(length)

    @staticmethod
    def is_empty() -> IsEmptyMatcher:
        """Matcher for an empty value (``len() == 0``)."""
        return IsEmptyMatcher()

    @staticmethod
    def is_not_empty() -> IsNotEmptyMatcher:
        """Matcher for a non-empty value (``len() > 0``)."""
        return IsNotEmptyMatcher()

    @staticmethod
    def is_positive() -> IsPositiveMatcher:
        """Matcher for a value greater than zero."""
        return IsPositiveMatcher()

    @staticmethod
    def is_negative() -> IsNegativeMatcher:
        """Matcher for a value less than zero."""
        return IsNegativeMatcher()

    @staticmethod
    def is_zero() -> IsZeroMatcher:
        """Matcher for a value equal to zero."""
        return IsZeroMatcher()

    @staticmethod
    def is_even() -> IsEvenMatcher:
        """Matcher for an even integer."""
        return IsEvenMatcher()

    @staticmethod
    def is_odd() -> IsOddMatcher:
        """Matcher for an odd integer."""
        return IsOddMatcher()

    @staticmethod
    def is_divisible_by(divisor: int) -> IsDivisibleByMatcher:
        """Matcher for an integer divisible by ``divisor``."""
        return IsDivisibleByMatcher(divisor)

    @staticmethod
    def is_callable() -> IsCallableMatcher:
        """Matcher for a callable object."""
        return IsCallableMatcher()

    @staticmethod
    def is_in(*values: object) -> IsInMatcher:
        """Matcher for a value present in ``values``.

        Args:
            *values: the candidate values; the matched value must equal one of them
        """
        return IsInMatcher(*values)

    @staticmethod
    def has_property(name: str, matcher: Matcher | None = None) -> HasPropertyMatcher:
        """Matcher for an object with attribute ``name``, optionally matching ``matcher``.

        Args:
            name: the attribute name the object must have
            matcher: optional matcher the attribute value must satisfy; if ``None``,
                only the presence of the attribute is checked
        """
        return HasPropertyMatcher(name, matcher)

    @staticmethod
    def contains_string(substring: str) -> ContainsStringMatcher:
        """Matcher for a string containing ``substring``."""
        return ContainsStringMatcher(substring)

    @staticmethod
    def matches_regex(pattern: str) -> MatchesRegexMatcher:
        """Matcher for a string in which ``pattern`` is found (``re.search``)."""
        return MatchesRegexMatcher(pattern)

    @staticmethod
    def starts_with(prefix: str) -> StartsWithMatcher:
        """Matcher for a string starting with ``prefix``."""
        return StartsWithMatcher(prefix)

    @staticmethod
    def ends_with(suffix: str) -> EndsWithMatcher:
        """Matcher for a string ending with ``suffix``."""
        return EndsWithMatcher(suffix)

    @staticmethod
    def all_of(*matchers: Matcher) -> AllOfMatcher:
        """Matcher that holds when every one of ``matchers`` matches (the ``&`` operator)."""
        return AllOfMatcher(*matchers)

    @staticmethod
    def any_of(*matchers: Matcher) -> AnyOfMatcher:
        """Matcher that holds when at least one of ``matchers`` matches (the ``|`` operator)."""
        return AnyOfMatcher(*matchers)

    @staticmethod
    def not_(matcher: Matcher) -> NotMatcher:
        """Matcher that inverts ``matcher`` (the ``~`` operator)."""
        return NotMatcher(matcher)

    @staticmethod
    def ignore() -> IgnoreMatcher:
        """Matcher that accepts anything; useful as a placeholder in ``structure`` specs."""
        return IgnoreMatcher()

    @staticmethod
    def is_uuid() -> IsUuidMatcher:
        """Matcher for a string parseable as a UUID."""
        return IsUuidMatcher()

    @staticmethod
    def is_non_empty_string() -> IsNonEmptyStringMatcher:
        """Matcher for a non-empty string."""
        return IsNonEmptyStringMatcher()

    @staticmethod
    def is_now(delta: float | timedelta = 2.0) -> IsNowMatcher:
        """Matcher for a ``datetime`` within ``delta`` of the current time.

        Args:
            delta: tolerance as seconds (a number) or a ``timedelta``; defaults to 2 seconds. Naive and
                timezone-aware values are both handled (compared against ``now`` in the same awareness).
        """
        return IsNowMatcher(delta if isinstance(delta, timedelta) else timedelta(seconds=delta))

    @staticmethod
    def is_before(other: datetime) -> IsBeforeMatcher:
        """Matcher for a ``datetime`` strictly before ``other`` (a non-comparable value never matches)."""
        return IsBeforeMatcher(other)

    @staticmethod
    def is_after(other: datetime) -> IsAfterMatcher:
        """Matcher for a ``datetime`` strictly after ``other`` (a non-comparable value never matches)."""
        return IsAfterMatcher(other)

    @staticmethod
    def each_item(matcher: Matcher) -> EachMatcher:
        """Matcher for an iterable whose every item matches ``matcher``.

        Args:
            matcher: the matcher each item of the iterable must satisfy; a non-iterable
                value never matches
        """
        return EachMatcher(matcher)

    @staticmethod
    def structure(spec: dict[Any, Any]) -> StructureMatcher:
        """Matcher for a dict matching ``spec``.

        Args:
            spec: dict whose values are matchers, raw values (compared with ``==``),
                or nested dict specs. Keys present in the value but absent from the spec are ignored.

        Examples:
            Usage:

                assert_that(user).satisfies(
                    match.structure({"id": match.is_instance_of(int), "name": "Alice"})
                )
        """
        return StructureMatcher(spec)

    def __getattr__(self, name: str) -> Callable[..., BaseMatcher]:
        with _custom_matchers_lock:
            try:
                factory = _custom_matchers[name]
            except KeyError:
                raise AttributeError(f"match has no matcher {name!r}") from None
        return factory


match = _MatchNamespace()
