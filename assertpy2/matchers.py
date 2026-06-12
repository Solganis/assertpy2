from __future__ import annotations

import re
import uuid as _uuid_mod
from typing import Protocol, runtime_checkable


@runtime_checkable
class Matcher(Protocol):
    """Protocol for composable matcher objects."""

    def matches(self, value: object) -> bool: ...

    def describe(self) -> str: ...

    def describe_mismatch(self, value: object) -> str: ...


class BaseMatcher:
    """Abstract base for all matchers with operator support."""

    def matches(self, value: object) -> bool:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError

    def describe_mismatch(self, value: object) -> str:
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

    def __repr__(self) -> str:
        return self.describe()


# --- Combinators ---


class AllOfMatcher(BaseMatcher):
    """Matches when all sub-matchers match (``&`` operator)."""

    def __init__(self, *matchers: Matcher):
        self.matchers = matchers

    def matches(self, value: object) -> bool:
        return all(m.matches(value) for m in self.matchers)

    def describe(self) -> str:
        return f"({' and '.join(m.describe() for m in self.matchers)})"

    def describe_mismatch(self, value: object) -> str:
        failed = [m for m in self.matchers if not m.matches(value)]
        return f"<{value}> did not satisfy: {', '.join(m.describe() for m in failed)}"


class AnyOfMatcher(BaseMatcher):
    """Matches when at least one sub-matcher matches (``|`` operator)."""

    def __init__(self, *matchers: Matcher):
        self.matchers = matchers

    def matches(self, value: object) -> bool:
        return any(m.matches(value) for m in self.matchers)

    def describe(self) -> str:
        return f"({' or '.join(m.describe() for m in self.matchers)})"

    def describe_mismatch(self, value: object) -> str:
        return f"<{value}> satisfied none of: {', '.join(m.describe() for m in self.matchers)}"


class NotMatcher(BaseMatcher):
    """Matches when the wrapped matcher does not match (``~`` operator)."""

    def __init__(self, matcher: Matcher):
        self.matcher = matcher

    def matches(self, value: object) -> bool:
        return not self.matcher.matches(value)

    def describe(self) -> str:
        return f"not {self.matcher.describe()}"

    def describe_mismatch(self, value: object) -> str:
        return f"<{value}> unexpectedly matched {self.matcher.describe()}"


# --- Value matchers ---


class EqualToMatcher(BaseMatcher):
    def __init__(self, expected: object):
        self.expected = expected

    def matches(self, value: object) -> bool:
        return value == self.expected

    def describe(self) -> str:
        return f"a value equal to <{self.expected}>"


class GreaterThanMatcher(BaseMatcher):
    def __init__(self, boundary: object):
        self.boundary = boundary

    def matches(self, value: object) -> bool:
        return value > self.boundary

    def describe(self) -> str:
        return f"a value greater than <{self.boundary}>"


class GreaterThanOrEqualToMatcher(BaseMatcher):
    def __init__(self, boundary: object):
        self.boundary = boundary

    def matches(self, value: object) -> bool:
        return value >= self.boundary

    def describe(self) -> str:
        return f"a value greater than or equal to <{self.boundary}>"


class LessThanMatcher(BaseMatcher):
    def __init__(self, boundary: object):
        self.boundary = boundary

    def matches(self, value: object) -> bool:
        return value < self.boundary

    def describe(self) -> str:
        return f"a value less than <{self.boundary}>"


class LessThanOrEqualToMatcher(BaseMatcher):
    def __init__(self, boundary: object):
        self.boundary = boundary

    def matches(self, value: object) -> bool:
        return value <= self.boundary

    def describe(self) -> str:
        return f"a value less than or equal to <{self.boundary}>"


class BetweenMatcher(BaseMatcher):
    def __init__(self, low: object, high: object):
        self.low = low
        self.high = high

    def matches(self, value: object) -> bool:
        return self.low <= value <= self.high

    def describe(self) -> str:
        return f"a value between <{self.low}> and <{self.high}>"


class CloseToMatcher(BaseMatcher):
    def __init__(self, expected: object, tolerance: object):
        self.expected = expected
        self.tolerance = tolerance

    def matches(self, value: object) -> bool:
        return abs(value - self.expected) <= self.tolerance

    def describe(self) -> str:
        return f"a value within <{self.tolerance}> of <{self.expected}>"


# --- Type/identity matchers ---


class IsNoneMatcher(BaseMatcher):
    def matches(self, value: object) -> bool:
        return value is None

    def describe(self) -> str:
        return "None"


class IsNotNoneMatcher(BaseMatcher):
    def matches(self, value: object) -> bool:
        return value is not None

    def describe(self) -> str:
        return "a non-None value"


class IsInstanceOfMatcher(BaseMatcher):
    def __init__(self, expected_type: type):
        self.expected_type = expected_type

    def matches(self, value: object) -> bool:
        return isinstance(value, self.expected_type)

    def describe(self) -> str:
        return f"an instance of <{self.expected_type.__name__}>"

    def describe_mismatch(self, value: object) -> str:
        return f"was <{value}> of type <{type(value).__name__}>"


class IsTruthyMatcher(BaseMatcher):
    def matches(self, value: object) -> bool:
        return bool(value)

    def describe(self) -> str:
        return "a truthy value"


class IsFalsyMatcher(BaseMatcher):
    def matches(self, value: object) -> bool:
        return not bool(value)

    def describe(self) -> str:
        return "a falsy value"


# --- Collection matchers ---


class HasLengthMatcher(BaseMatcher):
    def __init__(self, expected_length: int):
        self.expected_length = expected_length

    def matches(self, value: object) -> bool:
        return len(value) == self.expected_length

    def describe(self) -> str:
        return f"a value of length <{self.expected_length}>"

    def describe_mismatch(self, value: object) -> str:
        return f"was <{value}> with length <{len(value)}>"


class IsEmptyMatcher(BaseMatcher):
    def matches(self, value: object) -> bool:
        return len(value) == 0

    def describe(self) -> str:
        return "an empty value"


class IsNotEmptyMatcher(BaseMatcher):
    def matches(self, value: object) -> bool:
        return len(value) > 0

    def describe(self) -> str:
        return "a non-empty value"


# --- Numeric matchers ---


class IsPositiveMatcher(BaseMatcher):
    def matches(self, value: object) -> bool:
        return value > 0

    def describe(self) -> str:
        return "a positive value"


class IsNegativeMatcher(BaseMatcher):
    def matches(self, value: object) -> bool:
        return value < 0

    def describe(self) -> str:
        return "a negative value"


class IsZeroMatcher(BaseMatcher):
    def matches(self, value: object) -> bool:
        return value == 0

    def describe(self) -> str:
        return "zero"


class IsEvenMatcher(BaseMatcher):
    def matches(self, value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value % 2 == 0

    def describe(self) -> str:
        return "an even integer"

    def describe_mismatch(self, value: object) -> str:
        if isinstance(value, bool) or not isinstance(value, int):
            return f"was <{value!r}> of type <{type(value).__name__}>, not an integer"
        return f"was <{value}>, which is odd"


class IsOddMatcher(BaseMatcher):
    def matches(self, value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value % 2 != 0

    def describe(self) -> str:
        return "an odd integer"

    def describe_mismatch(self, value: object) -> str:
        if isinstance(value, bool) or not isinstance(value, int):
            return f"was <{value!r}> of type <{type(value).__name__}>, not an integer"
        return f"was <{value}>, which is even"


class IsDivisibleByMatcher(BaseMatcher):
    def __init__(self, divisor: int):
        self.divisor = divisor

    def matches(self, value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value % self.divisor == 0

    def describe(self) -> str:
        return f"an integer divisible by <{self.divisor}>"

    def describe_mismatch(self, value: object) -> str:
        if isinstance(value, bool) or not isinstance(value, int):
            return f"was <{value!r}> of type <{type(value).__name__}>, not an integer"
        return f"was <{value}>, which has remainder <{value % self.divisor}>"


class IsCallableMatcher(BaseMatcher):
    def matches(self, value: object) -> bool:
        return callable(value)

    def describe(self) -> str:
        return "a callable"

    def describe_mismatch(self, value: object) -> str:
        return f"was <{value!r}> of type <{type(value).__name__}>, which is not callable"


class IsInMatcher(BaseMatcher):
    def __init__(self, *values: object):
        self.values = values

    def matches(self, value: object) -> bool:
        return value in self.values

    def describe(self) -> str:
        return f"a value in <{self.values}>"

    def describe_mismatch(self, value: object) -> str:
        return f"was <{value!r}>, which is not in <{self.values}>"


class HasPropertyMatcher(BaseMatcher):
    def __init__(self, name: str, matcher: Matcher | None = None):
        self.name = name
        self.matcher = matcher

    def matches(self, value: object) -> bool:
        if not hasattr(value, self.name):
            return False
        if self.matcher is not None:
            return self.matcher.matches(getattr(value, self.name))
        return True

    def describe(self) -> str:
        if self.matcher is not None:
            return f"an object with property <{self.name}> matching {self.matcher.describe()}"
        return f"an object with property <{self.name}>"

    def describe_mismatch(self, value: object) -> str:
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

    def matches(self, value: object) -> bool:
        return isinstance(value, str) and self.substring in value

    def describe(self) -> str:
        return f"a string containing <{self.substring}>"


class MatchesRegexMatcher(BaseMatcher):
    def __init__(self, pattern: str):
        self.pattern = pattern

    def matches(self, value: object) -> bool:
        return isinstance(value, str) and re.search(self.pattern, value) is not None

    def describe(self) -> str:
        return f"a string matching pattern <{self.pattern}>"


class StartsWithMatcher(BaseMatcher):
    def __init__(self, prefix: str):
        self.prefix = prefix

    def matches(self, value: object) -> bool:
        return isinstance(value, str) and value.startswith(self.prefix)

    def describe(self) -> str:
        return f"a string starting with <{self.prefix}>"


class EndsWithMatcher(BaseMatcher):
    def __init__(self, suffix: str):
        self.suffix = suffix

    def matches(self, value: object) -> bool:
        return isinstance(value, str) and value.endswith(self.suffix)

    def describe(self) -> str:
        return f"a string ending with <{self.suffix}>"


# --- Structural matchers ---


class IgnoreMatcher(BaseMatcher):
    """Always matches. Used in structure specs to accept any value for a field."""

    def matches(self, value: object) -> bool:
        return True

    def describe(self) -> str:
        return "anything (ignored)"


class IsUuidMatcher(BaseMatcher):
    """Matches valid UUID strings."""

    def matches(self, value: object) -> bool:
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
    """Matches non-empty strings."""

    def matches(self, value: object) -> bool:
        return isinstance(value, str) and len(value) > 0

    def describe(self) -> str:
        return "a non-empty string"


class EachMatcher(BaseMatcher):
    """Matches when every item in an iterable satisfies the wrapped matcher."""

    def __init__(self, matcher: Matcher):
        self.matcher = matcher

    def matches(self, value: object) -> bool:
        try:
            return all(self.matcher.matches(item) for item in value)
        except TypeError:
            return False

    def describe(self) -> str:
        return f"each item matching {self.matcher.describe()}"

    def describe_mismatch(self, value: object) -> str:
        try:
            for i, item in enumerate(value):
                if not self.matcher.matches(item):
                    return f"item at index {i} <{item}> did not match {self.matcher.describe()}"
        except TypeError:
            return f"was not iterable: <{value}>"
        return f"was <{value}>"


class StructureMatcher(BaseMatcher):
    """Matches dicts against a structure spec where values are matchers, raw values, or nested dicts."""

    def __init__(self, spec: dict):
        self._spec = spec

    def matches(self, value: object) -> bool:
        if not isinstance(value, dict):
            return False
        return self._match_recursive(value, self._spec, "") is None

    def describe(self) -> str:
        return f"a dict matching structure {self._describe_spec(self._spec)}"

    def describe_mismatch(self, value: object) -> str:
        if not isinstance(value, dict):
            return f"was not a dict: <{value}>"
        error = self._match_recursive(value, self._spec, "")
        if error:
            return error
        return f"was <{value}>"

    def _match_recursive(self, value: dict, spec: dict, path: str) -> str | None:
        for key, expected in spec.items():
            current_path = f"{path}.{key}" if path else str(key)
            if key not in value:
                return f"missing key <{current_path}>"
            actual = value[key]
            if isinstance(expected, Matcher):
                if not expected.matches(actual):
                    return (
                        f"at <{current_path}>: expected {expected.describe()}, but {expected.describe_mismatch(actual)}"
                    )
            elif isinstance(expected, dict):
                if not isinstance(actual, dict):
                    return f"at <{current_path}>: expected a dict, but was <{actual}>"
                error = self._match_recursive(actual, expected, current_path)
                if error:
                    return error
            elif actual != expected:
                return f"at <{current_path}>: expected <{expected}>, but was <{actual}>"
        return None

    def _describe_spec(self, spec: dict) -> str:
        parts = []
        for key, value in spec.items():
            if isinstance(value, Matcher):
                parts.append(f"{key}: {value.describe()}")
            elif isinstance(value, dict):
                parts.append(f"{key}: {self._describe_spec(value)}")
            else:
                parts.append(f"{key}: <{value}>")
        return f"{{{', '.join(parts)}}}"


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
        return EqualToMatcher(expected)

    @staticmethod
    def greater_than(val: object) -> GreaterThanMatcher:
        return GreaterThanMatcher(val)

    @staticmethod
    def greater_than_or_equal_to(val: object) -> GreaterThanOrEqualToMatcher:
        return GreaterThanOrEqualToMatcher(val)

    @staticmethod
    def less_than(val: object) -> LessThanMatcher:
        return LessThanMatcher(val)

    @staticmethod
    def less_than_or_equal_to(val: object) -> LessThanOrEqualToMatcher:
        return LessThanOrEqualToMatcher(val)

    @staticmethod
    def between(low: object, high: object) -> BetweenMatcher:
        return BetweenMatcher(low, high)

    @staticmethod
    def close_to(expected: object, tolerance: object) -> CloseToMatcher:
        return CloseToMatcher(expected, tolerance)

    @staticmethod
    def is_none() -> IsNoneMatcher:
        return IsNoneMatcher()

    @staticmethod
    def is_not_none() -> IsNotNoneMatcher:
        return IsNotNoneMatcher()

    @staticmethod
    def is_instance_of(expected_type: type) -> IsInstanceOfMatcher:
        return IsInstanceOfMatcher(expected_type)

    @staticmethod
    def is_truthy() -> IsTruthyMatcher:
        return IsTruthyMatcher()

    @staticmethod
    def is_falsy() -> IsFalsyMatcher:
        return IsFalsyMatcher()

    @staticmethod
    def has_length(length: int) -> HasLengthMatcher:
        return HasLengthMatcher(length)

    @staticmethod
    def is_empty() -> IsEmptyMatcher:
        return IsEmptyMatcher()

    @staticmethod
    def is_not_empty() -> IsNotEmptyMatcher:
        return IsNotEmptyMatcher()

    @staticmethod
    def is_positive() -> IsPositiveMatcher:
        return IsPositiveMatcher()

    @staticmethod
    def is_negative() -> IsNegativeMatcher:
        return IsNegativeMatcher()

    @staticmethod
    def is_zero() -> IsZeroMatcher:
        return IsZeroMatcher()

    @staticmethod
    def is_even() -> IsEvenMatcher:
        return IsEvenMatcher()

    @staticmethod
    def is_odd() -> IsOddMatcher:
        return IsOddMatcher()

    @staticmethod
    def is_divisible_by(divisor: int) -> IsDivisibleByMatcher:
        return IsDivisibleByMatcher(divisor)

    @staticmethod
    def is_callable() -> IsCallableMatcher:
        return IsCallableMatcher()

    @staticmethod
    def is_in(*values: object) -> IsInMatcher:
        return IsInMatcher(*values)

    @staticmethod
    def has_property(name: str, matcher: Matcher | None = None) -> HasPropertyMatcher:
        return HasPropertyMatcher(name, matcher)

    @staticmethod
    def contains_string(substring: str) -> ContainsStringMatcher:
        return ContainsStringMatcher(substring)

    @staticmethod
    def matches_regex(pattern: str) -> MatchesRegexMatcher:
        return MatchesRegexMatcher(pattern)

    @staticmethod
    def starts_with(prefix: str) -> StartsWithMatcher:
        return StartsWithMatcher(prefix)

    @staticmethod
    def ends_with(suffix: str) -> EndsWithMatcher:
        return EndsWithMatcher(suffix)

    @staticmethod
    def all_of(*matchers: Matcher) -> AllOfMatcher:
        return AllOfMatcher(*matchers)

    @staticmethod
    def any_of(*matchers: Matcher) -> AnyOfMatcher:
        return AnyOfMatcher(*matchers)

    @staticmethod
    def not_(matcher: Matcher) -> NotMatcher:
        return NotMatcher(matcher)

    @staticmethod
    def ignore() -> IgnoreMatcher:
        return IgnoreMatcher()

    @staticmethod
    def is_uuid() -> IsUuidMatcher:
        return IsUuidMatcher()

    @staticmethod
    def is_non_empty_string() -> IsNonEmptyStringMatcher:
        return IsNonEmptyStringMatcher()

    @staticmethod
    def each_item(matcher: Matcher) -> EachMatcher:
        return EachMatcher(matcher)

    @staticmethod
    def structure(spec: dict) -> StructureMatcher:
        return StructureMatcher(spec)


match = _MatchNamespace()
