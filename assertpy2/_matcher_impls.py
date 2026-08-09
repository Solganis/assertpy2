from __future__ import annotations

import math
import re
import uuid as _uuid_mod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, NamedTuple, Protocol, runtime_checkable

from ._engine._compare import _CompareConfig, _guarded_not_equal
from ._engine._diff import _sub_diff_entries
from ._engine._introspection import MappingLike, is_attrs_instance, is_mapping_like, is_model_dump_object
from ._engine._path import _ROOT, _Path

if TYPE_CHECKING:
    from types import UnionType
    from typing import TypeAlias

    from typing_extensions import TypeIs

    from .errors import DiffResult

    # what `isinstance()` itself accepts, which is what `is_instance_of` forwards to.  Spelled out
    # rather than recursive (`tuple` may nest in principle): a recursive alias is not understood by
    # every checker we gate on, and one level is the whole of the documented surface.
    ClassInfo: TypeAlias = "type | UnionType | tuple[type | UnionType, ...]"


@runtime_checkable
class Matcher(Protocol):
    """Protocol for composable matcher objects."""

    def matches(self, value: Any) -> bool: ...

    def describe(self) -> str: ...

    def describe_mismatch(self, value: Any) -> str: ...


# builtin scalar/container types are never matchers; a frozenset membership test skips the expensive
# runtime_checkable protocol isinstance for the common operand of contains()/satisfies()/matcher dispatch
_NON_MATCHER_TYPES: Final = frozenset(
    {int, float, bool, complex, str, bytes, bytearray, list, tuple, dict, set, frozenset, type(None)}
)


def _is_matcher(obj: object) -> TypeIs[Matcher]:
    """Fast membership test for the runtime_checkable ``Matcher`` protocol.

    ``isinstance(x, Matcher)`` is expensive: the runtime_checkable check walks every protocol member
    through ``getattr_static``.  Two fast paths skip it while staying *strictly equivalent* to
    ``isinstance(obj, Matcher)``: a builtin operand is never a matcher (frozenset membership), and a
    ``BaseMatcher`` subclass instance always satisfies the protocol (a cheap C-level ``isinstance``,
    ~5x faster than the protocol walk).  Any other object - including a duck-typed custom matcher that
    does not inherit ``BaseMatcher`` - falls through to the full protocol check unchanged.
    """
    if type(obj) in _NON_MATCHER_TYPES:
        return False
    if isinstance(obj, BaseMatcher):
        return True
    return isinstance(obj, Matcher)


def _require_matcher(operand: object, operator: str) -> None:
    """Reject a non-matcher operand where the combinator is built, not where it is later applied.

    Combining silently would hand back a matcher that raises ``AttributeError: 'int' object has no
    attribute 'matches'`` at assertion time, far from the line that built it.
    """
    if not _is_matcher(operand):
        raise TypeError(f"cannot combine a Matcher with <{type(operand).__name__}> using '{operator}'")


@dataclass(frozen=True, slots=True, kw_only=True)
class MatchResult:
    """What a matcher decided about one value, in one object instead of three calls.

    Deliberately not an [`AssertionOutcome`][assertpy2.outcome.AssertionOutcome], which is the record of
    a *failed assertion*.  A matcher is asked about every leaf of a structure and about every element of
    a collection, so its result has to stay cheap: four fields, no location, no group, nothing that has
    to be computed before it is known whether anyone will read it.
    """

    matched: bool
    """Whether the value matched."""

    description: str
    """What the matcher requires, in the words it uses in a failure message: ``a positive value``."""

    mismatch: str = ""
    """Why this value did not match, in the words a failure message continues with: ``was <-1>``.

    Empty when it matched.  There is nothing to say about a value that satisfied the matcher, and the
    text would have to be invented.
    """

    diff: DiffResult | None = None
    """A structured diff, from a matcher that compares rather than tests: equality has one, ``is_odd``
    does not."""

    def __bool__(self) -> bool:
        """The verdict, so a result reads the same way the ``matches()`` it can replace did."""
        return self.matched


class BaseMatcher:
    """Abstract base for all matchers with operator support.

    A subclass implements either `matches()` or `evaluate()`, and gets the other one from here.
    `matches()` is the cheap primitive: it is what ``==`` calls, and matchers are used as dict values in
    `matches_structure` and as snapshot placeholders, so a comparison must not have to build a result
    object.  `evaluate()` is the whole answer, for a caller that would otherwise ask the same value
    three questions in a row.
    """

    def matches(self, value: Any) -> bool:
        if type(self).evaluate is BaseMatcher.evaluate:
            raise NotImplementedError("a matcher must implement matches() or evaluate()")
        return self.evaluate(value).matched

    def evaluate(self, value: Any) -> MatchResult:
        """The verdict, the requirement and the reason, from one look at *value*.

        The default composes the three older methods, so a matcher written before this existed answers
        it without changing.  Overriding it is for a matcher whose reason costs what the verdict already
        paid for: the alternative is `matches()` and `describe_mismatch()` walking the same value twice,
        which is how a matcher over a one-shot iterator used to name the wrong element.
        """
        if type(self).matches is BaseMatcher.matches:
            raise NotImplementedError("a matcher must implement matches() or evaluate()")
        matched = self.matches(value)
        return MatchResult(
            matched=matched,
            description=self.describe(),
            mismatch="" if matched else self.describe_mismatch(value),
        )

    def describe(self) -> str:
        raise NotImplementedError

    def describe_mismatch(self, value: Any) -> str:
        return f"was <{value}>"

    def __and__(self, other: Matcher) -> AllOfMatcher:
        _require_matcher(other, "&")
        left = list(self.matchers) if isinstance(self, AllOfMatcher) else [self]
        right = list(other.matchers) if isinstance(other, AllOfMatcher) else [other]
        return AllOfMatcher(*left, *right)

    def __or__(self, other: Matcher) -> AnyOfMatcher:
        _require_matcher(other, "|")
        left = list(self.matchers) if isinstance(self, AnyOfMatcher) else [self]
        right = list(other.matchers) if isinstance(other, AnyOfMatcher) else [other]
        return AnyOfMatcher(*left, *right)

    def __invert__(self) -> NotMatcher:
        return NotMatcher(self)

    def __eq__(self, other: object) -> bool:
        # an operand the predicate cannot evaluate means "no match"; ``==`` must never raise
        try:
            return self.matches(other)
        except (TypeError, ValueError):
            return False

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
    """Equality, optionally requiring the same type.

    ``strict_types`` is the same relation ``is_equal_to(..., strict_types=True)`` applies, spelled for a
    structural spec: one matcher covering value and type, rather than an `IsTypeOfMatcher` combined with
    a second matcher on every field that needs both.
    """

    def __init__(self, expected: object, strict_types: bool = False):
        self.expected = expected
        self.strict_types = strict_types

    def matches(self, value: Any) -> bool:
        if not self.strict_types:
            return bool(value == self.expected)
        if type(value) is not type(self.expected):
            return False
        # the flag walks to the leaves, so this has to as well: a composite expected value whose own
        # `==` is true says nothing about the types inside it, and one spelling of a relation that
        # disagrees with the other on nested data is worse than not offering it
        entries = _sub_diff_entries(value, self.expected, _ROOT, config=_CompareConfig(strict_types=True))
        if entries is None:  # a leaf the walker does not decompose
            return bool(value == self.expected)
        return not entries

    def describe(self) -> str:
        if self.strict_types:
            return f"a value equal to <{self.expected}> of type <{type(self.expected).__name__}>"
        return f"a value equal to <{self.expected}>"

    def describe_mismatch(self, value: Any) -> str:
        if self.strict_types and type(value) is not type(self.expected):
            return f"was <{value}> of type <{type(value).__name__}>"
        return f"was <{value}>"


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


def _is_nan(value: Any) -> bool:
    """Whether value is a NaN float/Decimal; False for operands math.isnan rejects (datetime, str)."""
    try:
        return math.isnan(value)
    except (TypeError, ValueError):
        return False


class CloseToMatcher(BaseMatcher):
    def __init__(self, expected: object, tolerance: object):
        self.expected = expected
        self.tolerance = tolerance

    def matches(self, value: Any) -> bool:
        # mirror is_close_to: NaN is never close, and a band comparison (not abs) so inf is close to inf.
        # Arithmetic is anchored on ``value`` (the band edges), so inf/inf never forms ``inf - inf`` (NaN).
        if _is_nan(value) or _is_nan(self.expected) or _is_nan(self.tolerance):
            return False
        try:
            return not (value - self.tolerance > self.expected or value + self.tolerance < self.expected)
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


def _type_expression_name(expected: object) -> str:
    """A readable name for a type expression, on every Python this package supports.

    ``__name__`` is absent on a union below 3.14 and on a tuple of types on every version, so reading
    it directly turns a failure message into an ``AttributeError`` - raised on the failure path, which
    is the worst place for it.  ``str()`` renders a union as ``int | str`` verbatim, which also reads
    better than the bare ``Union`` that 3.14 started reporting.

    A tuple is the third thing ``isinstance`` accepts, and its ``str()`` is a wall of ``<class '...'>``;
    naming its members is what the reader is after.
    """
    if isinstance(expected, tuple):
        return ", ".join(_type_expression_name(member) for member in expected)
    return expected.__name__ if isinstance(expected, type) else str(expected)


class IsInstanceOfMatcher(BaseMatcher):
    def __init__(self, expected_type: ClassInfo):
        # Probed here rather than in `matches()`, for the reason `MatchesRegexMatcher` compiles its
        # pattern eagerly: a matcher must not raise on use.  Without this, `list[int]` was accepted and
        # blew up inside `matches()`, and a tuple of classes matched fine and then blew up inside
        # `describe()` - only when a failure was being rendered.
        try:
            isinstance(None, expected_type)
        except TypeError:
            raise TypeError("given arg must be a class") from None
        self.expected_type = expected_type

    def matches(self, value: Any) -> bool:
        return isinstance(value, self.expected_type)

    def describe(self) -> str:
        return f"an instance of <{_type_expression_name(self.expected_type)}>"

    def describe_mismatch(self, value: Any) -> str:
        return f"was <{value}> of type <{type(value).__name__}>"


class IsTypeOfMatcher(BaseMatcher):
    """Exact type, mirroring the ``is_type_of`` assertion.

    `IsInstanceOfMatcher` accepts a subclass, which makes it unable to say "an ``int``, not a ``bool``"
    - the distinction a structural spec needs most, since ``bool`` subclasses ``int`` and JSON turns
    one into the other.
    """

    def __init__(self, expected_type: type):
        # the same check `is_type_of` applies, and for the same reason: `type(value) is <a union>` can
        # never be true, so accepting one produces a matcher that silently never matches
        if type(expected_type) is not type and not issubclass(type(expected_type), type):
            raise TypeError("given arg must be a type")
        self.expected_type = expected_type

    def matches(self, value: Any) -> bool:
        return type(value) is self.expected_type

    def describe(self) -> str:
        return f"exactly type <{_type_expression_name(self.expected_type)}>"

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
        try:
            return bool(value > 0)
        except TypeError:
            return False

    def describe(self) -> str:
        return "a positive value"


class IsNegativeMatcher(BaseMatcher):
    def matches(self, value: Any) -> bool:
        try:
            return bool(value < 0)
        except TypeError:
            return False

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
        # compile eagerly so an invalid pattern raises here, at the call site, instead of later inside
        # matches()/__eq__/a combinator, which would break the "matchers never raise on use" contract
        self._compiled = re.compile(pattern)

    def matches(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        return self._compiled.search(value) is not None

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


class IsNowMatcher(BaseMatcher):
    """Matches a ``datetime`` within a tolerance of the current time."""

    def __init__(self, delta: timedelta):
        self._delta = delta

    def matches(self, value: Any) -> bool:
        if not isinstance(value, datetime):
            return False
        # datetime.now(tzinfo) is naive for a naive value and aware (same offset) for an aware one, so
        # the subtraction never mixes offset-naive and offset-aware operands (which would raise)
        return abs(value - datetime.now(value.tzinfo)) <= self._delta

    def describe(self) -> str:
        return f"a datetime within {self._delta} of now"


class IsBeforeMatcher(BaseMatcher):
    """Matches a ``datetime`` strictly before a reference ``datetime``."""

    def __init__(self, other: datetime):
        self._other = other

    def matches(self, value: Any) -> bool:
        try:
            return isinstance(value, datetime) and value < self._other
        except TypeError:  # naive vs aware operands are not comparable -> no match
            return False

    def describe(self) -> str:
        return f"a datetime before {self._other}"


class IsAfterMatcher(BaseMatcher):
    """Matches a ``datetime`` strictly after a reference ``datetime``."""

    def __init__(self, other: datetime):
        self._other = other

    def matches(self, value: Any) -> bool:
        try:
            return isinstance(value, datetime) and value > self._other
        except TypeError:  # naive vs aware operands are not comparable -> no match
            return False

    def describe(self) -> str:
        return f"a datetime after {self._other}"


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
    if _is_matcher(value):
        return value.describe()
    if isinstance(value, dict):
        parts = [f"{key}: {_describe_spec_value(sub_value)}" for key, sub_value in value.items()]
        return f"{{{', '.join(parts)}}}"
    return f"<{value}>"


class _SpecMismatch(NamedTuple):
    """One structural mismatch produced by a single spec walk.

    ``expected_desc`` is the public "expected" half (as exposed by ``collect_mismatches``); ``detail``
    carries a matcher's ``describe_mismatch(actual)`` so fail-fast failure text keeps its per-value
    detail without a second traversal.
    """

    path: _Path
    actual: object
    expected_desc: str
    detail: str | None


class StructureMatcher(BaseMatcher):
    """Matches dicts (or pydantic-style models via ``model_dump()``) against a structure spec whose
    values are matchers, raw values, or nested dicts."""

    def __init__(self, spec: dict[Any, Any]):
        self._spec = spec

    @staticmethod
    def _as_mapping(value: Any) -> Any:
        """Normalize a pydantic-style model (``model_dump()``) or an attrs instance to its dict, so it
        can be matched structurally just like a plain dict; pass other values through."""
        if is_model_dump_object(value):
            return value.model_dump()
        if is_attrs_instance(value):
            return {field.name: getattr(value, field.name) for field in value.__attrs_attrs__}
        return value

    def matches(self, value: Any) -> bool:
        value = self._as_mapping(value)
        if not is_mapping_like(value):
            return False
        return not self._walk(value, self._spec, _ROOT, set())

    def describe(self) -> str:
        return f"a mapping matching structure {_describe_spec_value(self._spec)}"

    def describe_mismatch(self, value: Any) -> str:
        value = self._as_mapping(value)
        if not is_mapping_like(value):
            return f"was not a mapping: <{value}>"
        mismatches = self._walk(value, self._spec, _ROOT, set())
        return self.render_mismatch(mismatches) if mismatches else f"was <{value}>"

    def evaluate(self, value: Any) -> MatchResult:
        """One walk of the spec instead of two.

        `matches()` walks it and `describe_mismatch()` walks it again, which is the whole cost of this
        matcher on a payload of any size.  The rendering is shared with `describe_mismatch()` rather
        than repeated, so the two cannot answer differently.

        `matches_structure` does not go through here: it needs every mismatch for its diff, not only the
        first one in words, so it walks once via `walk_mismatches()` and renders from that.
        """
        mapped = self._as_mapping(value)
        if not is_mapping_like(mapped):
            return MatchResult(matched=False, description=self.describe(), mismatch=f"was not a mapping: <{mapped}>")
        mismatches = self._walk(mapped, self._spec, _ROOT, set())
        return MatchResult(
            matched=not mismatches,
            description=self.describe(),
            mismatch="" if not mismatches else self.render_mismatch(mismatches),
        )

    @staticmethod
    def render_mismatch(mismatches: list[_SpecMismatch]) -> str:
        """The first mismatch in words, from a walk the caller already paid for.

        Requires a non-empty list.  "Nothing mismatched" is not a mismatch to render, and the two callers
        disagree about what to say then: one has the mapped value to report, the other the raw one.
        """
        first = mismatches[0]
        where = first.path.text
        if first.actual is _MISSING:
            return f"missing key <{where}>"
        if first.expected_desc == "<circular ref>":  # cycle sentinel emitted by _walk
            # the root is unreachable here (see _walk), so the label only ever names a nested cycle
            return f"circular reference detected at <{where or 'root'}>"
        if first.detail is not None:
            return f"at <{where}>: expected {first.expected_desc}, but {first.detail}"
        return f"at <{where}>: expected {first.expected_desc}, but was <{first.actual}>"

    def collect_mismatches(self, value: Any) -> list[tuple[_Path, object, str]]:
        """Collect every structural mismatch as ``(path, actual, expected_description)``.

        Unlike `describe_mismatch()`, this does not stop at the first failure and joins nested
        paths, so callers can build a path-level [`DiffResult`][assertpy2.errors.DiffResult].
        """
        return [(mismatch.path, mismatch.actual, mismatch.expected_desc) for mismatch in self.walk_mismatches(value)]

    def walk_mismatches(self, value: Any) -> list[_SpecMismatch]:
        """Every mismatch, once, for a caller that needs both the entries and the message.

        `matches_structure` builds a diff entry per mismatch *and* names the first one in its message.
        Asking `collect_mismatches()` and then `describe_mismatch()` walked the spec twice, and the walk
        is the whole cost of this matcher on a payload of any size.
        """
        return self._walk(self._as_mapping(value), self._spec, _ROOT, set())

    def _walk(
        self, value: MappingLike, spec: dict[Any, Any], path: _Path, seen: set[tuple[int, int]]
    ) -> list[_SpecMismatch]:
        pair_id = (id(value), id(spec))
        if pair_id in seen:
            # `path` is empty only on the outermost call, where `seen` is still empty and no cycle can
            # be reported, so the fallback label is unreachable and kept purely as a guard
            return [_SpecMismatch(path, "<circular ref>", "<circular ref>", None)]
        seen = seen | {pair_id}
        mismatches: list[_SpecMismatch] = []
        for key, expected in spec.items():
            # the path is built where it is needed, not once per key: a spec that matches produces no
            # mismatch and reads no path, and building one per key was the whole added cost of carrying
            # machine-readable steps through this walk
            if key not in value:
                mismatches.append(_SpecMismatch(path.key(key), _MISSING, _describe_spec_value(expected), None))
                continue
            actual = value[key]
            if isinstance(expected, StructureMatcher) and is_mapping_like(normalized := self._as_mapping(actual)):
                mismatches.extend(self._walk(normalized, expected._spec, path.key(key), seen))
            elif _is_matcher(expected):
                # mirror BaseMatcher.__eq__ totality: a predicate that cannot evaluate means "no match"
                try:
                    matched = expected.matches(actual)
                except (TypeError, ValueError):
                    matched = False
                if not matched:
                    mismatches.append(
                        _SpecMismatch(path.key(key), actual, expected.describe(), expected.describe_mismatch(actual))
                    )
            elif isinstance(expected, dict):
                normalized = self._as_mapping(actual)
                if is_mapping_like(normalized):
                    mismatches.extend(self._walk(normalized, expected, path.key(key), seen))
                else:
                    mismatches.append(_SpecMismatch(path.key(key), actual, "a mapping", None))
            elif _guarded_not_equal(actual, expected, method="matches_structure"):
                mismatches.append(_SpecMismatch(path.key(key), actual, f"<{expected}>", None))
        return mismatches
