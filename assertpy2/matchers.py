from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, TypeVar, cast, overload

from ._engine._introspection import is_same_implementation
from ._engine._require import argument, refuse
from ._matcher_impls import (
    AllOfMatcher,
    AnyOfMatcher,
    BetweenMatcher,
    CloseToMatcher,
    ContainsMatcher,
    ContainsOnlyMatcher,
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
    IsNegativeMatcher,
    IsNoneMatcher,
    IsNonEmptyStringMatcher,
    IsNotEmptyMatcher,
    IsNotNoneMatcher,
    IsNowMatcher,
    IsOddMatcher,
    IsPositiveMatcher,
    IsSortedMatcher,
    IsSubsetOfMatcher,
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
    IsInstanceOfMatcher as IsInstanceOfMatcher,
)
from ._matcher_impls import (
    IsTypeOfMatcher as IsTypeOfMatcher,
)
from ._matcher_impls import (
    Matcher as Matcher,
)
from ._matcher_impls import (
    MatchResult as MatchResult,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    # the element of the collection a membership matcher judges, so `match.contains("x")` is a matcher
    # for collections *of strings* rather than for anything at all
    _Item = TypeVar("_Item")

    from ._matcher_impls import ClassInfo


# --- Matcher application helpers ---


def _apply_matcher(matcher: Matcher[Any] | Callable[..., object], value: object) -> bool:
    """Evaluate a ``Matcher`` or one-arg callable against ``value``.

    Shared resolution for every assertion that accepts either a `Matcher` or a callable
    predicate, mirroring the dispatch in ``satisfies``/``each``: a `Matcher` is checked via
    ``matches``, a callable via its return value, and anything else raises ``TypeError``.
    """
    if _is_matcher(matcher):
        return matcher.matches(value)
    if callable(matcher):
        return bool(cast("Callable[..., object]", matcher)(value))
    refuse(matcher, "a Matcher or a callable", subject=argument("matcher"))


def _evaluate_matcher(matcher: Matcher[Any], value: object) -> MatchResult:
    """One `MatchResult` from any matcher, including one that never heard of `evaluate()`.

    `BaseMatcher` gets `evaluate()` from its base, but a matcher is allowed to be duck-typed: the
    `Matcher` protocol is three methods and stays three, because widening it would un-match every
    third-party matcher written against the documented shape.  The composition that `BaseMatcher` does
    for its subclasses is done here for everything else.
    """
    evaluate = getattr(matcher, "evaluate", None)
    if evaluate is not None:
        return evaluate(value)
    matched = matcher.matches(value)
    return MatchResult(
        matched=matched,
        description=matcher.describe(),
        mismatch="" if matched else matcher.describe_mismatch(value),
    )


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


def _describe_matcher(matcher: Matcher[Any] | Callable[..., object]) -> str:
    """Describe a ``Matcher`` or callable for the "expected" half of an error or diff entry."""
    if _is_matcher(matcher):
        return matcher.describe()
    return _describe_callable(cast("Callable[..., object]", matcher))


# --- Custom matcher registry ---

_custom_matchers: dict[str, Callable[..., BaseMatcher]] = {}
_custom_matchers_lock = threading.Lock()


def register_matcher(
    name: str, *, override: bool = False
) -> Callable[[Callable[..., BaseMatcher]], Callable[..., BaseMatcher]]:
    """Register a custom matcher factory on the ``match`` namespace.

    A name already taken by another custom matcher is refused unless ``override`` says otherwise, so
    two libraries registering ``has_status`` find out at import rather than by whichever imported
    last quietly winning.

    A name already taken by a *built-in* matcher is refused outright, and ``override`` cannot lift it.
    ``match.equal_to`` resolves through ordinary attribute lookup, which never reaches this registry,
    so such a registration would not lose an argument - it would simply never run.

    Args:
        name: the name to register on ``match`` (e.g. ``"is_valid_email"``)
        override: replace an existing custom matcher of the same name instead of refusing

    Returns:
        A decorator that registers the wrapped function and returns it unchanged.

    Raises:
        TypeError: if ``name`` is not a string, or the decorated object is not callable
        ValueError: if ``name`` is not an identifier, names a built-in matcher, or names a custom one
            already registered and ``override`` is false

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
        refuse(name, "a string", subject=argument("name"))
    if not name.isidentifier():
        raise ValueError(f"name must be a valid Python identifier, got {name!r}")
    if hasattr(_MatchNamespace, name):
        raise ValueError(
            f"match.{name} is a built-in matcher, and attribute lookup reaches it before this "
            f"registry: a custom {name!r} would never be called. Register it under another name."
        )

    def decorator(func: Callable[..., BaseMatcher]) -> Callable[..., BaseMatcher]:
        if not callable(func):
            refuse(func, "callable", subject=argument("func"))
        with _custom_matchers_lock:
            # registering the same factory again is a no-op: a module imported twice, or a conftest
            # fixture that runs per module, is not two libraries fighting over one name
            clash = name in _custom_matchers and not is_same_implementation(_custom_matchers[name], func)
            if clash and not override:
                raise ValueError(
                    f"a custom matcher named {name!r} is already registered; pass override=True to "
                    f"replace it, or unregister_matcher({name!r}) first"
                )
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
    def equal_to(expected: object, strict_types: bool = False, **options: object) -> EqualToMatcher:
        """Matcher for a value equal to ``expected``.

        Args:
            expected: the value to compare against
            strict_types: also require the same type, so ``True`` no longer matches ``1``.  The same
                relation ``is_equal_to(..., strict_types=True)`` applies, spelled for a spec.
            **options: the rest of what
                [`is_equal_to()`][assertpy2.base.BaseMixin.is_equal_to] accepts, with the same meaning:
                ``tolerance``, ``comparators``, ``ignore``, ``include`` and ``ignore_null``.  One
                relation, one set of knobs, whichever way it is spelled.

        Examples:
            Usage:

                assert_that(reading).satisfies(match.equal_to(expected, tolerance=0.01))
                assert_that(payload).matches_structure({"user": match.equal_to(user, ignore="updated_at")})
        """
        return EqualToMatcher(expected, strict_types, **options)

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
    def is_instance_of(expected_type: ClassInfo) -> IsInstanceOfMatcher:
        """Matcher for an instance of ``expected_type`` (via ``isinstance``).

        Accepts whatever ``isinstance`` accepts: a class, a union (``int | str``), or a tuple of
        either.  The builder assertion of the same name stays narrower on purpose - its overloads
        refine the tracked value to the given class, and a union has no single class to refine to.
        Reach for `is_instance_of_any` there.
        """
        return IsInstanceOfMatcher(expected_type)

    @staticmethod
    def is_type_of(expected_type: type) -> IsTypeOfMatcher:
        """Matcher for exactly ``expected_type``, rejecting subclasses (``int`` but not ``bool``)."""
        return IsTypeOfMatcher(expected_type)

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
    def is_length(length: int) -> HasLengthMatcher:
        """Matcher for a value whose ``len()`` equals ``length``.

        The same matcher as `has_length()`, under the name the fluent assertion uses
        ([`is_length()`][assertpy2.base.BaseMixin.is_length]).  One relation was reachable as
        ``has_length`` from the matcher namespace and as ``is_length`` from the builder, so which name
        worked depended on which of the two a reader had seen first.  Both work from both now.
        """
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
    def contains_string(substring: str | bytes) -> Matcher[str | bytes]:
        """Matcher for text containing ``substring``, on `str` and on `bytes` alike."""
        return ContainsStringMatcher(substring)

    @staticmethod
    def matches_regex(pattern: str) -> Matcher[str]:
        """Matcher for a string in which ``pattern`` is found (``re.search``)."""
        return MatchesRegexMatcher(pattern)

    @staticmethod
    def starts_with(prefix: str | bytes) -> Matcher[str | bytes]:
        """Matcher for text starting with ``prefix``, on `str` and on `bytes` alike."""
        return StartsWithMatcher(prefix)

    @staticmethod
    def ends_with(suffix: str | bytes) -> Matcher[str | bytes]:
        """Matcher for text ending with ``suffix``, on `str` and on `bytes` alike."""
        return EndsWithMatcher(suffix)

    @staticmethod
    def all_of(*matchers: Matcher[Any]) -> AllOfMatcher:
        """Matcher that holds when every one of ``matchers`` matches (the ``&`` operator)."""
        return AllOfMatcher(*matchers)

    @staticmethod
    def any_of(*matchers: Matcher[Any]) -> AnyOfMatcher:
        """Matcher that holds when at least one of ``matchers`` matches (the ``|`` operator)."""
        return AnyOfMatcher(*matchers)

    @staticmethod
    def not_(matcher: Matcher[Any]) -> NotMatcher:
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
    def contains(*items: _Item) -> Matcher[Iterable[_Item]]:
        """Matcher for a collection containing every one of ``items``.

        The spec spelling of [`contains()`][assertpy2.contains.ContainsMixin.contains], with the same
        rules: a mapping is searched by key, and a matcher among the items is satisfied by any element.

        Examples:
            Usage:

                assert_that(payload).matches_structure({"tags": match.contains("beta")})
                assert_that(rows).satisfies(match.contains(match.greater_than(100)))
        """
        return ContainsMatcher(*items)

    @staticmethod
    def contains_only(*items: _Item) -> Matcher[Iterable[_Item]]:
        """Matcher for a collection holding these items and nothing else.

        The spec spelling of [`contains_only()`][assertpy2.contains.ContainsMixin.contains_only].
        """
        return ContainsOnlyMatcher(*items)

    @overload
    @staticmethod
    def is_subset_of(superset: Iterable[_Item], /) -> Matcher[Iterable[_Item]]: ...

    @overload
    @staticmethod
    def is_subset_of(*superset: _Item) -> Matcher[Iterable[_Item]]: ...

    @staticmethod
    def is_subset_of(*superset: object) -> Matcher[Iterable[Any]]:
        """Matcher for a collection whose items all appear in ``superset``.

        The spec spelling of [`is_subset_of()`][assertpy2.collection.CollectionMixin.is_subset_of].
        Takes the superset either as one collection or as loose items, which is why it is overloaded:
        read off a single union, a checker cannot tell `[1, 2]` the collection from `[1, 2]` the item.

        An ordinary collection stays a live view of itself, the way ``equal_to`` keeps its expected
        value; a one-shot iterator is drained when the matcher is built, since it could not answer a
        second time otherwise.  Handing in an endless iterator therefore never returns.
        """
        return IsSubsetOfMatcher(*superset)

    @staticmethod
    def is_sorted(key: Callable[[Any], Any] | None = None, reverse: bool = False) -> Matcher[Iterable[Any]]:
        """Matcher for a collection in order, optionally by ``key`` and optionally reversed.

        The spec spelling of [`is_sorted()`][assertpy2.collection.CollectionMixin.is_sorted].
        """
        return IsSortedMatcher(key, reverse)

    @staticmethod
    def each_item(matcher: Matcher[Any]) -> EachMatcher:
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
