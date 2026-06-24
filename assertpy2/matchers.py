from __future__ import annotations

import re
import threading
import uuid as _uuid_mod
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable


@runtime_checkable
class Matcher(Protocol):
    """Protocol for composable matcher objects."""

    def matches(self, value: Any) -> bool: ...

    def describe(self) -> str: ...

    def describe_mismatch(self, value: Any) -> str: ...


class BaseMatcher:
    """Abstract base for all matchers with operator support."""

    def matches(self, value: Any) -> bool:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError

    def describe_mismatch(self, value: Any) -> str:
        return f"was <{value}>"

    def __and__(self, other: Matcher) -> AllOfMatcher:
        left = list(self.matchers) if isinstance(self, AllOfMatcher) else [self]
        right = list(other.matchers) if isinstance(other, AllOfMatcher) else [other]
        return AllOfMatcher(*left, *right)

    def __or__(self, other: Matcher) -> AnyOfMatcher:
        left = list(self.matchers) if isinstance(self, AnyOfMatcher) else [self]
        right = list(other.matchers) if isinstance(other, AnyOfMatcher) else [other]
        return AnyOfMatcher(*left, *right)

    def __invert__(self) -> NotMatcher:
        return NotMatcher(self)

    def __eq__(self, other: object) -> bool:
        return self.matches(other)

    def __hash__(self) -> int:
        return id(self)

    def __repr__(self) -> str:
        return self.describe()


# --- Combinators ---


class AllOfMatcher(BaseMatcher):
    """Matches when all sub-matchers match (``&`` operator)."""

    def __init__(self, *matchers: Matcher):
        self.matchers = matchers

    def matches(self, value: Any) -> bool:
        return all(matcher.matches(value) for matcher in self.matchers)

    def describe(self) -> str:
        return f"({' and '.join(matcher.describe() for matcher in self.matchers)})"

    def describe_mismatch(self, value: Any) -> str:
        failed = [matcher for matcher in self.matchers if not matcher.matches(value)]
        return f"<{value}> did not satisfy: {', '.join(matcher.describe() for matcher in failed)}"


class AnyOfMatcher(BaseMatcher):
    """Matches when at least one sub-matcher matches (``|`` operator)."""

    def __init__(self, *matchers: Matcher):
        self.matchers = matchers

    def matches(self, value: Any) -> bool:
        return any(matcher.matches(value) for matcher in self.matchers)

    def describe(self) -> str:
        return f"({' or '.join(matcher.describe() for matcher in self.matchers)})"

    def describe_mismatch(self, value: Any) -> str:
        return f"<{value}> satisfied none of: {', '.join(matcher.describe() for matcher in self.matchers)}"


class NotMatcher(BaseMatcher):
    """Matches when the wrapped matcher does not match (``~`` operator)."""

    def __init__(self, matcher: Matcher):
        self.matcher = matcher

    def matches(self, value: Any) -> bool:
        return not self.matcher.matches(value)

    def describe(self) -> str:
        return f"not {self.matcher.describe()}"

    def describe_mismatch(self, value: Any) -> str:
        return f"<{value}> unexpectedly matched {self.matcher.describe()}"


# --- Value matchers ---


class EqualToMatcher(BaseMatcher):
    def __init__(self, expected: object):
        self.expected = expected

    def matches(self, value: Any) -> bool:
        return bool(value == self.expected)

    def describe(self) -> str:
        return f"a value equal to <{self.expected}>"


class GreaterThanMatcher(BaseMatcher):
    def __init__(self, boundary: object):
        self.boundary = boundary

    def matches(self, value: Any) -> bool:
        try:
            return bool(value > self.boundary)
        except TypeError:
            return False

    def describe(self) -> str:
        return f"a value greater than <{self.boundary}>"


class GreaterThanOrEqualToMatcher(BaseMatcher):
    def __init__(self, boundary: object):
        self.boundary = boundary

    def matches(self, value: Any) -> bool:
        try:
            return bool(value >= self.boundary)
        except TypeError:
            return False

    def describe(self) -> str:
        return f"a value greater than or equal to <{self.boundary}>"


class LessThanMatcher(BaseMatcher):
    def __init__(self, boundary: object):
        self.boundary = boundary

    def matches(self, value: Any) -> bool:
        try:
            return bool(value < self.boundary)
        except TypeError:
            return False

    def describe(self) -> str:
        return f"a value less than <{self.boundary}>"


class LessThanOrEqualToMatcher(BaseMatcher):
    def __init__(self, boundary: object):
        self.boundary = boundary

    def matches(self, value: Any) -> bool:
        try:
            return bool(value <= self.boundary)
        except TypeError:
            return False

    def describe(self) -> str:
        return f"a value less than or equal to <{self.boundary}>"


class BetweenMatcher(BaseMatcher):
    def __init__(self, low: object, high: object):
        self.low = low
        self.high = high

    def matches(self, value: Any) -> bool:
        try:
            return bool(self.low <= value <= self.high)
        except TypeError:
            return False

    def describe(self) -> str:
        return f"a value between <{self.low}> and <{self.high}>"


class CloseToMatcher(BaseMatcher):
    def __init__(self, expected: object, tolerance: object):
        self.expected = expected
        self.tolerance = tolerance

    def matches(self, value: Any) -> bool:
        try:
            return bool(abs(value - self.expected) <= self.tolerance)
        except TypeError:
            return False

    def describe(self) -> str:
        return f"a value within <{self.tolerance}> of <{self.expected}>"


# --- Type/identity matchers ---


class IsNoneMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        return value is None

    def describe(self) -> str:
        return "None"


class IsNotNoneMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        return value is not None

    def describe(self) -> str:
        return "a non-None value"


class IsInstanceOfMatcher(BaseMatcher):
    def __init__(self, expected_type: type):
        self.expected_type = expected_type

    def matches(self, value: Any) -> bool:
        return isinstance(value, self.expected_type)

    def describe(self) -> str:
        return f"an instance of <{self.expected_type.__name__}>"

    def describe_mismatch(self, value: Any) -> str:
        return f"was <{value}> of type <{type(value).__name__}>"


class IsTruthyMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        return bool(value)

    def describe(self) -> str:
        return "a truthy value"


class IsFalsyMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        return not bool(value)

    def describe(self) -> str:
        return "a falsy value"


# --- Collection matchers ---


class HasLengthMatcher(BaseMatcher):
    def __init__(self, expected_length: int):
        self.expected_length = expected_length

    def matches(self, value: Any) -> bool:
        try:
            return len(value) == self.expected_length
        except TypeError:
            return False

    def describe(self) -> str:
        return f"a value of length <{self.expected_length}>"

    def describe_mismatch(self, value: Any) -> str:
        try:
            return f"was <{value}> with length <{len(value)}>"
        except TypeError:
            return f"was <{value!r}>, which has no length"


class IsEmptyMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        try:
            return len(value) == 0
        except TypeError:
            return False

    def describe(self) -> str:
        return "an empty value"


class IsNotEmptyMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        try:
            return len(value) > 0
        except TypeError:
            return False

    def describe(self) -> str:
        return "a non-empty value"


# --- Numeric matchers ---


class IsPositiveMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        return bool(value > 0)

    def describe(self) -> str:
        return "a positive value"


class IsNegativeMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        return bool(value < 0)

    def describe(self) -> str:
        return "a negative value"


class IsZeroMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        return bool(value == 0)

    def describe(self) -> str:
        return "zero"


class IsEvenMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value % 2 == 0

    def describe(self) -> str:
        return "an even integer"

    def describe_mismatch(self, value: Any) -> str:
        if isinstance(value, bool) or not isinstance(value, int):
            return f"was <{value!r}> of type <{type(value).__name__}>, not an integer"
        return f"was <{value}>, which is odd"


class IsOddMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value % 2 != 0

    def describe(self) -> str:
        return "an odd integer"

    def describe_mismatch(self, value: Any) -> str:
        if isinstance(value, bool) or not isinstance(value, int):
            return f"was <{value!r}> of type <{type(value).__name__}>, not an integer"
        return f"was <{value}>, which is even"


class IsDivisibleByMatcher(BaseMatcher):
    def __init__(self, divisor: int):
        if divisor == 0:
            raise ValueError("given divisor arg must not be zero")
        self.divisor = divisor

    def matches(self, value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value % self.divisor == 0

    def describe(self) -> str:
        return f"an integer divisible by <{self.divisor}>"

    def describe_mismatch(self, value: Any) -> str:
        if isinstance(value, bool) or not isinstance(value, int):
            return f"was <{value!r}> of type <{type(value).__name__}>, not an integer"
        return f"was <{value}>, which has remainder <{value % self.divisor}>"


class IsCallableMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        return callable(value)

    def describe(self) -> str:
        return "a callable"

    def describe_mismatch(self, value: Any) -> str:
        return f"was <{value!r}> of type <{type(value).__name__}>, which is not callable"


class IsInMatcher(BaseMatcher):
    def __init__(self, *values: object):
        self.values = values

    def matches(self, value: Any) -> bool:
        return value in self.values

    def describe(self) -> str:
        return f"a value in <{self.values}>"

    def describe_mismatch(self, value: Any) -> str:
        return f"was <{value!r}>, which is not in <{self.values}>"


class HasPropertyMatcher(BaseMatcher):
    def __init__(self, name: str, matcher: Matcher | None = None):
        self.name = name
        self.matcher = matcher

    def matches(self, value: Any) -> bool:
        if not hasattr(value, self.name):
            return False
        if self.matcher is not None:
            return self.matcher.matches(getattr(value, self.name))
        return True

    def describe(self) -> str:
        if self.matcher is not None:
            return f"an object with property <{self.name}> matching {self.matcher.describe()}"
        return f"an object with property <{self.name}>"

    def describe_mismatch(self, value: Any) -> str:
        if not hasattr(value, self.name):
            return f"<{value!r}> has no property <{self.name}>"
        if self.matcher is not None:
            actual = getattr(value, self.name)
            return f"property <{self.name}> was <{actual!r}>, {self.matcher.describe_mismatch(actual)}"
        return f"was <{value!r}>"


# --- String matchers ---


class ContainsStringMatcher(BaseMatcher):
    def __init__(self, substring: str):
        self.substring = substring

    def matches(self, value: Any) -> bool:
        return isinstance(value, str) and self.substring in value

    def describe(self) -> str:
        return f"a string containing <{self.substring}>"


class MatchesRegexMatcher(BaseMatcher):
    def __init__(self, pattern: str):
        self.pattern = pattern

    def matches(self, value: Any) -> bool:
        return isinstance(value, str) and re.search(self.pattern, value) is not None

    def describe(self) -> str:
        return f"a string matching pattern <{self.pattern}>"


class StartsWithMatcher(BaseMatcher):
    def __init__(self, prefix: str):
        self.prefix = prefix

    def matches(self, value: Any) -> bool:
        return isinstance(value, str) and value.startswith(self.prefix)

    def describe(self) -> str:
        return f"a string starting with <{self.prefix}>"


class EndsWithMatcher(BaseMatcher):
    def __init__(self, suffix: str):
        self.suffix = suffix

    def matches(self, value: Any) -> bool:
        return isinstance(value, str) and value.endswith(self.suffix)

    def describe(self) -> str:
        return f"a string ending with <{self.suffix}>"


# --- Structural matchers ---


class IgnoreMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        return True

    def describe(self) -> str:
        return "anything (ignored)"


class IsUuidMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        try:
            _uuid_mod.UUID(value)
        except ValueError:
            return False
        return True

    def describe(self) -> str:
        return "a valid UUID string"


class IsNonEmptyStringMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        return isinstance(value, str) and len(value) > 0

    def describe(self) -> str:
        return "a non-empty string"


class EachMatcher(BaseMatcher):
    """Matches when every item in an iterable satisfies the wrapped matcher."""

    def __init__(self, matcher: Matcher):
        self.matcher = matcher

    def matches(self, value: Any) -> bool:
        try:
            return all(self.matcher.matches(item) for item in value)
        except TypeError:
            return False

    def describe(self) -> str:
        return f"each item matching {self.matcher.describe()}"

    def describe_mismatch(self, value: Any) -> str:
        try:
            for i, item in enumerate(value):
                if not self.matcher.matches(item):
                    return f"item at index {i} <{item}> did not match {self.matcher.describe()}"
        except TypeError:
            return f"was not iterable: <{value}>"
        return f"was <{value}>"


class _MissingSentinel:
    """Placeholder recorded for a spec key absent from the value during structural matching."""

    def __repr__(self) -> str:
        return "<missing>"


_MISSING: Final = _MissingSentinel()


def _describe_spec_value(value: object) -> str:
    """Describe a single structure-spec value (matcher, nested dict spec, or raw value)."""
    if isinstance(value, Matcher):
        return value.describe()
    if isinstance(value, dict):
        parts = [f"{key}: {_describe_spec_value(sub_value)}" for key, sub_value in value.items()]
        return f"{{{', '.join(parts)}}}"
    return f"<{value}>"


class StructureMatcher(BaseMatcher):
    """Matches dicts against a structure spec where values are matchers, raw values, or nested dicts."""

    def __init__(self, spec: dict[Any, Any]):
        self._spec = spec

    def matches(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        return self._match_recursive(value, self._spec, "", set()) is None

    def describe(self) -> str:
        return f"a dict matching structure {_describe_spec_value(self._spec)}"

    def describe_mismatch(self, value: Any) -> str:
        if not isinstance(value, dict):
            return f"was not a dict: <{value}>"
        error = self._match_recursive(value, self._spec, "", set())
        if error:
            return error
        return f"was <{value}>"

    def _match_recursive(
        self, value: dict[Any, Any], spec: dict[Any, Any], path: str, seen: set[tuple[int, int]]
    ) -> str | None:
        pair_id = (id(value), id(spec))
        if pair_id in seen:
            return f"circular reference detected at <{path or 'root'}>"
        seen.add(pair_id)
        for key, expected in spec.items():
            current_path = f"{path}.{key}" if path else str(key)
            if key not in value:
                return f"missing key <{current_path}>"
            actual = value[key]
            if isinstance(expected, StructureMatcher):
                if not isinstance(actual, dict):
                    return f"at <{current_path}>: expected a dict, but was <{actual}>"
                error = self._match_recursive(actual, expected._spec, current_path, seen)
                if error:
                    return error
            elif isinstance(expected, Matcher):
                if not expected.matches(actual):
                    return (
                        f"at <{current_path}>: expected {expected.describe()}, but {expected.describe_mismatch(actual)}"
                    )
            elif isinstance(expected, dict):
                if not isinstance(actual, dict):
                    return f"at <{current_path}>: expected a dict, but was <{actual}>"
                error = self._match_recursive(actual, expected, current_path, seen)
                if error:
                    return error
            elif actual != expected:
                return f"at <{current_path}>: expected <{expected}>, but was <{actual}>"
        return None

    def collect_mismatches(self, value: dict[Any, Any]) -> list[tuple[str, object, str]]:
        """Collect every structural mismatch as ``(path, actual, expected_description)``.

        Unlike :meth:`describe_mismatch`, this does not stop at the first failure and joins nested
        paths, so callers can build a path-level :class:`~assertpy2.errors.DiffResult`.
        """
        return self._collect(value, self._spec, "", set())

    def _collect(
        self, value: dict[Any, Any], spec: dict[Any, Any], path: str, seen: set[tuple[int, int]]
    ) -> list[tuple[str, object, str]]:
        pair_id = (id(value), id(spec))
        if pair_id in seen:
            return [(path or "root", "<circular ref>", "<circular ref>")]
        seen = seen | {pair_id}
        mismatches: list[tuple[str, object, str]] = []
        for key, expected in spec.items():
            current_path = f"{path}.{key}" if path else str(key)
            if key not in value:
                mismatches.append((current_path, _MISSING, _describe_spec_value(expected)))
                continue
            actual = value[key]
            if isinstance(expected, StructureMatcher) and isinstance(actual, dict):
                mismatches.extend(self._collect(actual, expected._spec, current_path, seen))
            elif isinstance(expected, Matcher):
                if not expected.matches(actual):
                    mismatches.append((current_path, actual, expected.describe()))
            elif isinstance(expected, dict):
                if isinstance(actual, dict):
                    mismatches.extend(self._collect(actual, expected, current_path, seen))
                else:
                    mismatches.append((current_path, actual, "a dict"))
            elif actual != expected:
                mismatches.append((current_path, actual, f"<{expected}>"))
        return mismatches


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
        Register a simple matcher::

            @register_matcher("is_valid_email")
            def is_valid_email():
                return match.matches_regex(r"^[\\w.-]+@[\\w.-]+\\.\\w+$")

            assert_that(email).satisfies(match.is_valid_email())

        Register a parametrised matcher::

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

    Usage::

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
            Usage::

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
