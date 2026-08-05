"""Per-call configuration for tolerant / custom-comparator equality, shared by the equality and diff code.

``is_equal_to`` builds a `_CompareConfig` from its ``tolerance``/``comparators`` kwargs and threads it
through both the boolean comparison (`HelpersMixin._dict_not_equal()`) and the diff/message rendering
(`assertpy2._engine._diff._sub_diff_entries()`, `HelpersMixin._dict_err()`).  `_node_decision()` is the single
switch both sides consult, so a tolerated or comparator-equal leaf is reported in neither.  With ``config is
None`` every helper reproduces the engine's historical ``actual != expected`` behavior exactly.

Following the package convention, the impl helpers take unannotated args (the typed public surface lives in
`assertpy2._engine._typing`); they operate on arbitrary user values whose operators ``numbers.Number`` cannot
express to the type checker.
"""

from __future__ import annotations

import dataclasses
import math
import numbers
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ._introspection import is_mapping_like, is_model_dump_object

if TYPE_CHECKING:
    from collections.abc import Callable


_EQ_ATOMIC = frozenset({int, float, bool, complex, str, bytes, bytearray, type(None)})
"""Types whose ``==`` is a plain bool and which have nothing inside to walk into."""


@dataclass(frozen=True, slots=True, kw_only=True)
class _CompareConfig:
    """Tolerance and custom comparators for a single ``is_equal_to`` call.

    ``tolerance`` is an absolute tolerance applied to real-number leaves; ``comparators`` maps a ``type`` or
    an immediate field name to a ``(actual, expected) -> bool`` predicate that owns matching leaves;
    ``ignore_null`` skips a named field whenever the *expected* side leaves it ``None``;
    ``strict_types`` additionally requires both sides of every node to be the same type, which plain
    ``==`` does not (``True == 1``, ``Decimal("1") == 1``, and so on all the way down a payload).
    """

    tolerance: float | None = None
    comparators: dict[object, Callable[[object, object], bool]] | None = None
    ignore_null: bool = False
    strict_types: bool = False


def _build_compare_config(tolerance, comparators, ignore_null=False, strict_types=False) -> _CompareConfig | None:
    """Validate the ``is_equal_to`` comparison kwargs and build a config.

    Returns ``None`` when none are set.  ``tolerance`` must be a non-negative real number (not
    ``bool``/``complex``/``NaN``); ``comparators`` must be a dict of ``(actual, expected) -> bool`` callables
    keyed by ``type`` or field name; ``ignore_null`` and ``strict_types`` must be bools.
    """
    if ignore_null is not False and ignore_null is not True:
        raise TypeError("given ignore_null arg must be a bool")
    if strict_types is not False and strict_types is not True:
        raise TypeError("given strict_types arg must be a bool")
    if tolerance is None and comparators is None and not ignore_null and not strict_types:
        return None
    if tolerance is not None:
        if isinstance(tolerance, bool) or not isinstance(tolerance, numbers.Number) or isinstance(tolerance, complex):
            raise TypeError("given tolerance arg must be a real number")
        if math.isnan(tolerance):
            raise ValueError("given tolerance arg must not be NaN")
        if tolerance < 0:
            raise ValueError("given tolerance arg must not be negative")
    if comparators is not None:
        if not isinstance(comparators, dict):
            raise TypeError("given comparators arg must be a dict")
        for comparator in comparators.values():
            if not callable(comparator):
                raise TypeError("each comparator must be callable")
    return _CompareConfig(
        tolerance=tolerance, comparators=comparators, ignore_null=ignore_null, strict_types=strict_types
    )


def _ambiguous_array_operand(value: object, other: object) -> object | None:
    """Return the array/frame-like operand whose ``==`` has no single truth value, else ``None``.

    numpy/pandas/polars containers expose ``__array__`` and compare element-wise, so ``bool(a == b)``
    raises rather than yielding one bool (and a ``DataFrame`` also quacks dict-like, which would otherwise
    mis-dispatch the comparison).  The ``__array__`` gate keeps the extra comparison off the hot path; the
    truth test is actually attempted, so 0-d / scalar array values (which *are* truth-testable) pass
    through unchanged.
    """
    if not hasattr(value, "__array__") and not hasattr(other, "__array__"):
        return None  # fast path: no array-like operand, skip the tuple/loop on every is_equal_to
    for candidate, counterpart in ((value, other), (other, value)):
        if hasattr(candidate, "__array__"):
            try:
                bool(candidate == counterpart)
            except (ValueError, TypeError):
                return candidate
    return None


def _array_equality_error(method: str, operand: object) -> TypeError:
    """Build the actionable error raised when ``method`` is given an element-wise array/frame-like."""
    # point at the assertion that delegates to the library's own comparison: it reports the differing
    # column or index, where wrapping `.equals()` in is_true() would report a bare False
    dedicated = "is_frame_equal(expected)" if hasattr(operand, "equals") else "is_array_equal(expected)"
    return TypeError(
        f"{method}() cannot directly compare <{type(operand).__name__}>: its '==' is element-wise and has"
        f" no single truth value. Use {dedicated}, assert on extracted scalars (columns, shape, length),"
        " or use satisfies(...) with an explicit predicate."
    )


def _find_ambiguous_operand(actual, expected, _seen=None):
    """Locate the array/frame-like member that broke a comparison, walking the diff engine's containers.

    Cold error-path only; ``None`` means the error was not array-caused and must be re-raised unchanged.
    """
    if _seen is None:
        _seen = set()
    pair = (id(actual), id(expected))
    if pair in _seen:
        return None
    _seen = _seen | {pair}
    operand = _ambiguous_array_operand(actual, expected)
    if operand is not None:
        return operand
    if is_mapping_like(actual) and is_mapping_like(expected):
        expected_keys = set(expected)
        for key in actual:
            if key in expected_keys:
                found = _find_ambiguous_operand(actual[key], expected[key], _seen)
                if found is not None:
                    return found
        return None
    if (
        dataclasses.is_dataclass(actual)
        and not isinstance(actual, type)
        and dataclasses.is_dataclass(expected)
        and not isinstance(expected, type)
    ):
        for field in dataclasses.fields(actual):
            found = _find_ambiguous_operand(getattr(actual, field.name), getattr(expected, field.name, None), _seen)
            if found is not None:
                return found
        return None
    if is_model_dump_object(actual) and is_model_dump_object(expected):
        return _find_ambiguous_operand(actual.model_dump(), expected.model_dump(), _seen)
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        for actual_item, expected_item in zip(actual, expected, strict=False):
            found = _find_ambiguous_operand(actual_item, expected_item, _seen)
            if found is not None:
                return found
    return None


def _guarded_not_equal(actual, expected, *, method="is_equal_to") -> bool:
    """``bool(actual != expected)``, converting the ambiguity raised from *inside* a container's ``==``
    (where the top-level operand gate cannot see the array member) into the actionable ``TypeError``."""
    try:
        return bool(actual != expected)
    except (ValueError, TypeError) as error:
        operand = _find_ambiguous_operand(actual, expected)
        if operand is None:
            raise
        raise _array_equality_error(method, operand) from error


def _guarded_equal(actual, expected, *, method) -> bool:
    """``bool(actual == expected)`` with the same nested array/frame-like guard as `_guarded_not_equal`."""
    try:
        return bool(actual == expected)
    except (ValueError, TypeError) as error:
        operand = _find_ambiguous_operand(actual, expected)
        if operand is None:
            raise
        raise _array_equality_error(method, operand) from error


def _is_real_number(value) -> bool:
    """Return whether ``value`` is a real number eligible for tolerance (excludes ``bool`` and ``complex``).

    Array/frame-likes are not `numbers.Number`, so they are excluded too - tolerance never triggers
    their element-wise ``==`` that has no single truth value.
    """
    return isinstance(value, numbers.Number) and not isinstance(value, (bool, complex))


def _within_tolerance(actual, expected, tolerance) -> bool:
    """Return whether two real numbers are within ``tolerance`` (absolute); ``NaN`` is never within.

    Only actual ``float`` operands are checked for ``NaN`` (other reals cannot be ``NaN``), which also keeps
    ``math.isnan`` off arbitrary-precision ``int`` values that would overflow it.
    """
    if isinstance(actual, float) and math.isnan(actual):
        return False
    if isinstance(expected, float) and math.isnan(expected):
        return False
    if actual == expected:  # equal values (including inf == inf) are within any tolerance
        return True
    return abs(actual - expected) <= tolerance


def _resolve_comparator(actual, config: _CompareConfig, *, field):
    """Resolve the comparator owning a leaf: immediate field name first, then exact type, then ``isinstance``.

    ``field`` is the leaf's immediate key/field name (``None`` for sequence elements and bare scalars, which
    have no name).  Returns ``None`` when no comparator applies, so the caller falls back to tolerance / ``==``.
    """
    comparators = config.comparators
    if comparators is None:
        return None
    if field is not None and not isinstance(field, type) and field in comparators:
        return comparators[field]
    if type(actual) in comparators:
        return comparators[type(actual)]
    for key, comparator in comparators.items():
        if isinstance(key, type) and isinstance(actual, key):
            return comparator
    return None


def _types_differ(actual, expected) -> bool:
    """Whether ``strict_types`` should reject this pair.

    A matcher standing in for a value is not a value, so it is exempt: the expected side of
    ``is_equal_to({"id": match.greater_than(0)})`` is a ``GreaterThanMatcher`` by construction, and
    comparing its type against an ``int`` would break every composed matcher rather than catch a bug.

    ``_is_matcher`` is imported here rather than at module scope because ``_matcher_impls`` imports
    ``_guarded_not_equal`` from this module, so the module-level import would be a cycle.
    """
    if type(actual) is type(expected):
        return False
    from .._matcher_impls import _is_matcher

    return not _is_matcher(expected) and not _is_matcher(actual)


def _node_decision(actual, expected, config: _CompareConfig | None, *, field=None) -> str:
    """Classify a node as ``"equal"``, ``"leaf"``, ``"recurse"`` or ``"strict"``.

    With ``config is None`` this is exactly the engine's historical behavior: differing values ``"recurse"``
    (to decompose into a sub-diff), equal values are ``"equal"`` (skipped); ``"leaf"`` never occurs.  With a
    config, a matching comparator or tolerance owns the node - it is classified ``"equal"`` or ``"leaf"`` and
    never recursed into.

    ``"strict"`` is the fourth: the two sides are equal and the same type, but ``strict_types`` still has
    to look inside, because a container's ``==`` says nothing about the types of its members.  It differs
    from ``"recurse"`` only in what an undecomposable value means, which
    `assertpy2._engine._diff._child_entries()` is the single place to know.
    """
    if config is not None:
        if config.ignore_null and field is not None and expected is None:
            return "equal"  # a named field the expected side leaves None is not compared
        comparator = _resolve_comparator(actual, config, field=field)
        if comparator is not None:
            return "equal" if comparator(actual, expected) else "leaf"
        if config.strict_types:
            if actual is expected:
                # what `PyObject_RichCompareBool` hands a container for free, and what forcing the walk
                # below would otherwise take away: one object is equal to itself without consulting
                # `__eq__`, which is why a shared subnode is cheap and why `[nan] == [nan]` is true when
                # both elements are the same float
                return "equal"
            if _types_differ(actual, expected):
                # ahead of tolerance on purpose: a tolerance says how far apart two numbers may be, it
                # does not say they may be different types, and a strict run that quietly accepted int
                # vs float inside its own tolerance would be the surprise, not the rule
                return "leaf"
            if type(actual) not in _EQ_ATOMIC and not _guarded_not_equal(actual, expected):
                # a container's own `==` says nothing about the types inside it: `[True] == [1]`.  The
                # walk normally stops here, so under strict types it has to keep going.  Whether the
                # walker can actually take this value apart is not predicted here: `"strict"` tells the
                # caller that a value it cannot decompose is one that is already equal
                return "strict"
        if config.tolerance is not None and _is_real_number(actual) and _is_real_number(expected):
            return "equal" if _within_tolerance(actual, expected, config.tolerance) else "leaf"
    return "recurse" if _guarded_not_equal(actual, expected) else "equal"


def _spec_matches(key, value, specs) -> bool:
    """Return whether a dict ``key``/``value`` matches any ignore/include ``spec``.

    A spec matches by exact key equality (today's behavior), by a compiled `re.Pattern` searched
    against ``str(key)``, or by a ``type`` the ``value`` is an instance of.  Nested-path tuples never match
    here - they are expanded by the recursion in `HelpersMixin._dict_not_equal()`.
    """
    for spec in specs:
        if isinstance(spec, re.Pattern):
            if spec.search(str(key)):
                return True
        elif isinstance(spec, type):
            if isinstance(value, spec):
                return True
        elif spec == key:
            return True
    return False
