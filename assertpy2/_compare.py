"""Per-call configuration for tolerant / custom-comparator equality, shared by the equality and diff code.

``is_equal_to`` builds a `_CompareConfig` from its ``tolerance``/``comparators`` kwargs and threads it
through both the boolean comparison (`HelpersMixin._dict_not_equal()`) and the diff/message rendering
(`BaseMixin._sub_diff_entries()`, `HelpersMixin._dict_err()`).  `_node_decision()` is the single
switch both sides consult, so a tolerated or comparator-equal leaf is reported in neither.  With ``config is
None`` every helper reproduces the engine's historical ``actual != expected`` behavior exactly.

Following the package convention, the impl helpers take unannotated args (the typed public surface lives in
`assertpy2._typing`); they operate on arbitrary user values whose operators ``numbers.Number`` cannot
express to the type checker.
"""

from __future__ import annotations

import math
import numbers
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

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
    return "recurse" if actual != expected else "equal"


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
