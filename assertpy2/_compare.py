"""Per-call configuration for tolerant / custom-comparator equality, shared by the equality and diff code.

``is_equal_to`` builds a `_CompareConfig` from its ``tolerance``/``comparators`` kwargs and threads it
through both the boolean comparison (`HelpersMixin._dict_not_equal()`) and the diff/message rendering
(`assertpy2._diff._sub_diff_entries()`, `HelpersMixin._dict_err()`).  `_node_decision()` is the single
switch both sides consult, so a tolerated or comparator-equal leaf is reported in neither.  With ``config is
None`` every helper reproduces the engine's historical ``actual != expected`` behavior exactly.

Following the package convention, the impl helpers take unannotated args (the typed public surface lives in
`assertpy2._typing`); they operate on arbitrary user values whose operators ``numbers.Number`` cannot
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


@dataclass(frozen=True, slots=True, kw_only=True)
class _CompareConfig:
    """Tolerance and custom comparators for a single ``is_equal_to`` call.

    ``tolerance`` is an absolute tolerance applied to real-number leaves; ``comparators`` maps a ``type`` or
    an immediate field name to a ``(actual, expected) -> bool`` predicate that owns matching leaves.
    """

    tolerance: float | None = None
    comparators: dict[object, Callable[[object, object], bool]] | None = None


def _build_compare_config(tolerance, comparators) -> _CompareConfig | None:
    """Validate the ``is_equal_to`` ``tolerance``/``comparators`` kwargs and build a config (``None`` if neither).

    ``tolerance`` must be a non-negative real number (not ``bool``/``complex``/``NaN``); ``comparators`` must be a
    dict of ``(actual, expected) -> bool`` callables keyed by ``type`` or field name.
    """
    if tolerance is None and comparators is None:
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
    return _CompareConfig(tolerance=tolerance, comparators=comparators)


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
    return TypeError(
        f"{method}() cannot directly compare <{type(operand).__name__}>: its '==' is element-wise and has"
        " no single truth value. Compare the value's own equality (e.g."
        " assert_that(actual.equals(expected)).is_true()), assert on extracted scalars (columns, shape,"
        " length), or use satisfies(...) with an explicit predicate."
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


def _node_decision(actual, expected, config: _CompareConfig | None, *, field=None) -> str:
    """Classify a node as ``"equal"``, ``"leaf"`` or ``"recurse"``.

    With ``config is None`` this is exactly the engine's historical behavior: differing values ``"recurse"``
    (to decompose into a sub-diff), equal values are ``"equal"`` (skipped); ``"leaf"`` never occurs.  With a
    config, a matching comparator or tolerance owns the node - it is classified ``"equal"`` or ``"leaf"`` and
    never recursed into.
    """
    if config is not None:
        comparator = _resolve_comparator(actual, config, field=field)
        if comparator is not None:
            return "equal" if comparator(actual, expected) else "leaf"
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
