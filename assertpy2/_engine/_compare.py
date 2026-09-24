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
import datetime
import decimal
import fractions
import inspect
import math
import numbers
import pathlib
import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ._introspection import is_attrs_instance, is_mapping_like, is_model_dump_object, model_field_values
from ._ordering import nan_operand
from ._require import raised_inside, verdict

if TYPE_CHECKING:
    from collections.abc import Callable


_EQ_ATOMIC = frozenset(
    {
        int,
        float,
        bool,
        complex,
        str,
        bytes,
        bytearray,
        type(None),
        datetime.datetime,
        datetime.date,
        datetime.time,
        datetime.timedelta,
        decimal.Decimal,
        uuid.UUID,
        pathlib.PurePosixPath,
        pathlib.PureWindowsPath,
        pathlib.PosixPath,
        pathlib.WindowsPath,
    }
)
"""Types whose ``==`` is a plain bool and which have nothing inside to walk into.

The stdlib scalars past the builtins are here for cost, not for correctness.  ``strict_types`` walks
past any value it does not know to be atomic, because a container's own ``==`` says nothing about the
types inside it - and a ``datetime`` is not a container, so that walk runs the whole introspection
ladder to come back with nothing.  Over 200 records of timestamps, decimals and UUIDs that was 3.7 ms
against 0.5 ms with them listed.

Listing one changes no verdict: a type difference is decided by `_types_differ()` before atomicity is
ever consulted, so ``date`` against ``datetime`` still fails.  Exact types, not ``isinstance``, so a
subclass with its own structure is still walked.
"""


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
    # `dict` and not `Mapping`: the runtime refuses anything else, so a checker-approved `MappingProxyType` would fail
    comparators: dict[Any, Callable[[Any, Any], Any]] | None = None
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
    # the dedicated assertion names the differing column or index, where wrapping `.equals()` reports a bare False
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
        return _find_ambiguous_operand(model_field_values(actual), model_field_values(expected), _seen)
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

    Checked by type rather than through `math.isnan`, which overflows on an arbitrary-precision ``int``
    and signals on a `Decimal` NaN.

    The subtraction is tried as written, so two floats keep the arithmetic they always had.  A `Decimal`
    against a ``float`` refuses to subtract at all and a bignum ``int`` overflows one, and those two pairs
    are measured exactly instead, through `fractions.Fraction`.
    """
    if nan_operand(actual) or nan_operand(expected):
        return False
    if actual == expected:  # equal values (including inf == inf) are within any tolerance
        return True
    if _is_infinite(actual) or _is_infinite(expected):
        return False  # unequal, and no distance from an infinity is within a finite tolerance
    try:
        return abs(actual - expected) <= tolerance
    except (TypeError, OverflowError) as error:
        if raised_inside(error):  # their own `__sub__` or `__abs__` raised: a bug in the value, not a refusal
            raise
        return abs(fractions.Fraction(actual) - fractions.Fraction(expected)) <= fractions.Fraction(tolerance)


def _is_infinite(value) -> bool:
    """A `float` or `Decimal` infinity, asked by type so nothing else is converted to a float to answer.

    Through `Decimal`'s own method rather than the value's: a subclass overriding `is_infinite` would
    otherwise decide this, and run its code before the arithmetic it is being asked about.
    """
    if isinstance(value, float):
        return math.isinf(value)
    return isinstance(value, decimal.Decimal) and decimal.Decimal.is_infinite(value)


class WindowRefusedError(TypeError):
    """The two operands form no window: neither the arithmetic nor an exact conversion takes them.

    A `TypeError` still, so a caller that let the operand's own refusal out keeps letting this one out,
    and a matcher, which may not raise, can tell it from a `__sub__` of somebody's own that raised.
    """


def tolerance_window(middle: Any, tolerance: Any) -> tuple[Any, Any]:
    """The closed interval ``middle`` plus and minus ``tolerance``.

    Typed as `Any` because the pairing is a run-time fact: the assertion has refused every combination
    but two before it asks, a number against a number and a datetime against a timedelta, and a checker
    reading the public signature alone is right to refuse the arithmetic.  The matcher asks without
    refusing anything first, which is what `WindowRefusedError` is for: it hands back the operands' own
    refusal as something a matcher may answer "no match" to.
    """
    if _is_infinite(middle) and _is_real_number(tolerance):
        # its own window, the way a float infinity already gets one: no distance from it is finite.  The
        # tolerance is still read, or an infinity paired with anything at all would answer "close enough"
        return middle, middle
    try:
        return middle - tolerance, middle + tolerance
    except TypeError as refusal:
        if raised_inside(refusal):  # their own `__sub__` raised: that is a bug in the value
            raise
        if not all(isinstance(operand, numbers.Number) for operand in (middle, tolerance)):
            raise WindowRefusedError(str(refusal)) from None
        # a `Decimal` refuses arithmetic with a `float` or a `Fraction`, which both convert exactly, while
        # an infinite or NaN one does not convert at all
        try:
            exact, span = fractions.Fraction(middle), fractions.Fraction(tolerance)
        except (TypeError, ValueError, OverflowError) as failed:
            raise WindowRefusedError(str(failed)) from None
        return exact - span, exact + span


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


def _keyed_types_differ(actual, expected) -> bool:
    """Whether two equal containers disagree on the *types* of what they are keyed by.

    The rest of `strict_types` works pair by pair, and a mapping key or a set member never becomes a
    pair: the container matched them itself, by hash and equality, before the walk ever saw them.  So
    `{True: "a"} == {1: "a"}` and `{1} == {1.0}` both passed a strict comparison, which is the one
    thing the flag's name promises they would not.

    Each side is reduced to its members paired with their types.  `(bool, True)` and `(int, 1)` are
    different pairs where `True` and `1` are the same key, which is exactly the distinction being made.
    Values are left alone here: they do become pairs, and the walk judges them.
    """
    # structural, like everything here: the concrete-type check let a `UserDict` pass where the matcher refused it
    if is_mapping_like(actual) and is_mapping_like(expected):
        return {(type(key), key) for key in actual} != {(type(key), key) for key in expected}
    if isinstance(actual, (set, frozenset)) and isinstance(expected, (set, frozenset)):
        return {(type(member), member) for member in actual} != {(type(member), member) for member in expected}
    return False


def _kinds_never_equal(actual, expected) -> bool:
    """Whether ``==`` rejects the pair by its kind alone, which a walk over the parts cannot see.

    Under a compare config the walker decides by parts, so ``[1.0]`` against ``(1.0,)``, or two dataclasses
    of different classes holding the same fields, had no differing part and passed, while ``==`` rejects
    both outright.  Asked only once ``==`` has already said no, so it never fails a pair ``==`` accepts.

    The kind alone is not the answer: a list subclass may define ``__eq__`` to accept a tuple.  So a pair
    of different kinds counts only when both sides' own ``__eq__`` decline it, which leaves ``==`` at
    identity whatever the parts hold.  A pydantic model answers ``False`` rather than declining, so which of
    class or fields decided cannot be told apart, and models are left to the walk.
    """
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        kinds_differ = isinstance(actual, list) is not isinstance(expected, list)
    else:
        both_dataclasses = all(
            dataclasses.is_dataclass(side) and not isinstance(side, type) for side in (actual, expected)
        )
        both_attrs = is_attrs_instance(actual) and is_attrs_instance(expected)
        kinds_differ = (both_dataclasses or both_attrs) and type(actual) is not type(expected)
    return kinds_differ and _both_decline(actual, expected)


def _declines(value: Any, other: Any) -> bool:
    """Whether *value*'s own ``__eq__`` answers ``NotImplemented`` for *other*, asked as ``==`` asks it.

    Read statically off the type, since `type(x).__eq__` is an ordinary read that a metaclass answers,
    and bound through the descriptor protocol, since that is what turns a function, a `staticmethod` or
    anything else on the class into the callable the operator uses.
    """
    held: Any = inspect.getattr_static(type(value), "__eq__", None)
    bind: Any = getattr(type(held), "__get__", None)
    # measured against `==` itself: a callable that binds to nothing is called with the other side alone
    asking = held if bind is None else bind(held, value, type(value))
    return asking(other) is NotImplemented


def _both_decline(actual: Any, expected: Any) -> bool:
    """Whether each side's own ``__eq__`` answers ``NotImplemented`` for the other."""
    try:
        return _declines(actual, expected) and _declines(expected, actual)
    except Exception:  # an `__eq__` that raises decides nothing here, and the walk goes on as before
        return False


def _node_decision(actual, expected, config: _CompareConfig | None, *, field=None, at_root: bool = False) -> str:
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
            return "equal" if verdict(comparator(actual, expected), subject="the comparator") else "leaf"
        if config.strict_types:
            if actual is expected and not at_root:
                # identity, free from `PyObject_RichCompareBool`.  Not at the root, where it made `strict_types` weaker
                return "equal"
            if _types_differ(actual, expected):
                # ahead of tolerance: how far apart is not the same as may differ in type
                return "leaf"
            if _keyed_types_differ(actual, expected):
                # before the walk: it descends keys into values, so `True` and `1` keys present the same values
                return "leaf"
            if type(actual) not in _EQ_ATOMIC and not _guarded_not_equal(actual, expected):
                # `[True] == [1]`: a container says nothing about the types inside it, so the walk keeps going
                return "strict"
        if config.tolerance is not None and _is_real_number(actual) and _is_real_number(expected):
            return "equal" if _within_tolerance(actual, expected, config.tolerance) else "leaf"
    return _plain_decision(actual, expected, config, at_root=at_root)


def _plain_decision(actual, expected, config: _CompareConfig | None, *, at_root: bool = False) -> str:
    """``==``'s answer as a decision, where under a config a pair ruled out by its kind alone is a leaf."""
    if actual is expected and not at_root:
        # the same rule a container's own `==` applies to its members, and the verdict came from that `==`:
        # without it the diff listed a NaN both sides hold as differing, and the hint blamed it
        return "equal"
    if not _guarded_not_equal(actual, expected):
        return "equal"
    return "leaf" if config is not None and _kinds_never_equal(actual, expected) else "recurse"


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


def _config_note(config: _CompareConfig | None) -> str:
    """A newline plus an echo of the comparison settings that were in force, or ``""`` when none were.

    ``is_equal_to`` already names ``ignore`` and ``include`` inside its sentence, but nothing reports
    the rest, and they are what a reader is questioning when a field they thought was tolerated still
    failed.  Rendered only for a non-default config: `_build_compare_config()` returns ``None`` when
    every setting is at its default, so the check costs nothing and the line never appears on the
    ordinary failure.

    It goes on its own line rather than into the sentence, so the original message stays a prefix and
    a `match=` or ``startswith`` written against it keeps working.
    """
    if config is None:
        return ""
    parts = []
    if config.tolerance is not None:
        parts.append(f"tolerance={config.tolerance!r}")
    if config.comparators:
        keys = ", ".join(sorted(key.__name__ if isinstance(key, type) else str(key) for key in config.comparators))
        parts.append(f"comparators for {keys}")
    if config.ignore_null:
        parts.append("ignore_null=True")
    if config.strict_types:
        parts.append("strict_types=True")
    return "\ncompared with " + ", ".join(parts) if parts else ""
