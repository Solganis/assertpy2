"""Per-call configuration for tolerant / custom-comparator equality, shared by the equality and diff code.

``is_equal_to`` builds a `_CompareConfig` from its ``tolerance``/``comparators`` kwargs and threads it
through both the boolean comparison (`HelpersMixin._dict_not_equal()`) and the diff/message rendering
(`assertpy2._engine._diff._sub_diff_entries()`, `HelpersMixin._dict_err()`).  `_node_decision()` is the single
switch both sides consult, so a tolerated or comparator-equal leaf is reported in neither.  With ``config is
None`` every helper reproduces plain ``actual == expected`` exactly.

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

from ._introspection import (
    KeyedValue,
    as_held,
    eq_keyed,
    is_attrs_instance,
    is_mapping_like,
    is_model_dump_object,
    kind_of,
    model_field_values,
)
from ._ordering import UnorderableError, equal_past, holds
from ._require import raised_inside, verdict

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


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
        if _is_nan(tolerance):
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
            except OverflowError as overflow:
                if raised_inside(overflow):
                    raise
                continue  # a `numpy` scalar converting a bignum, which says nothing about element-wise `==`
            except decimal.InvalidOperation as signal:
                if raised_inside(signal):
                    raise
                continue  # a signalling NaN, which `_guarded_equal` answers
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
    for left, right in _members_compared(actual, expected):
        found = _find_ambiguous_operand(left, right, _seen)
        if found is not None:
            return found
    return None


def _members_compared(actual: Any, expected: Any) -> Iterable[tuple[Any, Any]]:
    """The pairs ``==`` walks into for two values of one container kind, and none for any other pair."""
    if is_mapping_like(actual) and is_mapping_like(expected):
        expected_keys = set(expected)
        return ((actual[key], expected[key]) for key in actual if key in expected_keys)
    if (
        dataclasses.is_dataclass(actual)
        and not isinstance(actual, type)
        and dataclasses.is_dataclass(expected)
        and not isinstance(expected, type)
    ):
        return (
            (getattr(actual, one.name), getattr(expected, one.name, None))
            for one in dataclasses.fields(actual)
            if one.compare
        )
    if is_attrs_instance(actual) and is_attrs_instance(expected):
        return _keyed_members(actual, expected)
    if is_model_dump_object(actual) and is_model_dump_object(expected):
        return ((model_field_values(actual), model_field_values(expected)),)
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        return zip(actual, expected, strict=False)
    return ()


def _keyed_members(actual: Any, expected: Any) -> tuple[tuple[Any, Any], ...]:
    """The attrs fields ``==`` compares, each read through its key as ``==`` reads it, or none.

    Only what ``==`` compares can have broken it.  attrs reads every key before it compares a field, so a key
    that raises is the error being explained and no array is to blame: read again here, it raised a second
    error while the first was handled, and skipped, it let a later array take the blame.
    """
    try:
        return tuple(
            (
                eq_keyed(one, getattr(actual, one.name)),
                eq_keyed(one, getattr(expected, one.name)) if hasattr(expected, one.name) else None,
            )
            for one in actual.__attrs_attrs__
            if one.eq is not False
        )
    except (TypeError, ValueError):  # the two errors `_guarded_equal` hands to this search
        return ()


def _guarded_equal(actual, expected, *, method="is_equal_to") -> bool:
    """``bool(actual == expected)``, converting the ambiguity raised from *inside* a container's ``==``
    (where the top-level operand gate cannot see the array member) into the actionable ``TypeError``.

    The one question every equality verdict asks, the negative ones included: a type's ``__ne__`` need
    not be the negation of its ``__eq__``, and asking it made ``is_equal_to`` and ``is_not_equal_to``
    fail the same pair while a list holding that pair, which compares its members with ``==``, passed.
    A signalling NaN or an overflowing `numpy` float, anywhere in the pair, is answered as `equals` answers it.
    """
    try:
        return bool(actual == expected)
    except (ValueError, TypeError) as error:
        operand = _find_ambiguous_operand(actual, expected)
        if operand is not None:
            raise _array_equality_error(method, operand) from error
        if isinstance(error, ValueError):
            raise
        return equal_past(actual, expected, error)
    except (decimal.InvalidOperation, OverflowError) as refusal:
        return equal_past(actual, expected, refusal)


def _is_real_number(value) -> bool:
    """Return whether ``value`` is a real number eligible for tolerance (excludes ``bool`` and ``complex``).

    Array/frame-likes are not `numbers.Number`, so they are excluded too - tolerance never triggers
    their element-wise ``==`` that has no single truth value.  An exact `int` or `float` answers before
    the ABC check, which cost a hundred nanoseconds on every leaf a tolerance is asked about.
    """
    return type(value) in (int, float) or (isinstance(value, numbers.Number) and not isinstance(value, (bool, complex)))


def _within_tolerance(actual, expected, tolerance) -> bool:
    """Whether two values lie within ``tolerance`` of each other, the same answer whichever comes first.

    One distance, measured three ways that a float rounds differently at the boundary: the difference,
    and the window around each side.  Any of them holding is enough.  Measured one way each, the three
    spellings disagreed: ``-1.1`` was close to ``-0.9`` within ``0.2`` for `is_close_to`, which windows
    around the other operand, and not for `match.close_to`, which windows around the value, nor for
    ``is_equal_to(tolerance=)``, which takes the difference.  Taking any of the three, no spelling now
    fails a pair it passed before.

    A window the ordering engine cannot order is one way fewer of holding, and the difference still
    answers: a `Decimal` refuses to order against a `numpy.int64` it subtracts exactly.  Only a pair with
    no difference either raises `UnorderableError` out of the windows, for the caller to refuse or to read
    as no match.

    ``NaN`` is never within, and an infinity is within only of itself, whatever the tolerance, the rule
    `math.isclose` keeps.  The operands are classified before equality is asked, since a value's own
    `__eq__` could otherwise call a NaN or a finite number equal to what it is not, and the distance is
    never classified: two finite values far enough apart overflow their difference to an infinity and are
    still measured.  An infinite tolerance was a wildcard before this, `1` was close to `inf` within `inf`
    through the window around `1`, and it now covers every finite pair and no more.
    """
    actual_kind, expected_kind = _non_finite(actual), _non_finite(expected)
    if actual_kind or expected_kind:
        return actual_kind == expected_kind == "inf" and bool(actual == expected)
    try:
        if actual == expected:
            return True
    except (TypeError, OverflowError) as refusal:
        # `Decimal` refuses to compare a `numpy.int64` it subtracts exactly: the equality is unknown, not false
        if raised_inside(refusal):
            raise
    difference = _difference_within(actual, expected, tolerance)
    if difference:
        return True
    unordered = None
    try:
        if _window_holds(expected, actual, tolerance):
            return True
    except UnorderableError as refusal:
        unordered = refusal
    try:
        if _window_holds(actual, expected, tolerance):
            return True
    except UnorderableError as refusal:
        unordered = unordered or refusal
    if unordered is not None and difference is None:
        raise unordered
    return False


def _difference_within(actual, expected, tolerance) -> bool | None:
    """``abs(actual - expected) <= tolerance``, or ``None`` for two values that cannot be subtracted.

    Tried as written, so two floats keep the arithmetic they always had.  A `Decimal` against a ``float``
    refuses to subtract at all and a bignum ``int`` or a `Fraction` past the float range overflows one, and
    those pairs are measured exactly instead, through `fractions.Fraction`.
    """
    try:
        return abs(actual - expected) <= tolerance
    except (TypeError, OverflowError) as error:
        # their own `__sub__` or `__abs__` raised: a bug in the value, not a refusal
        if raised_inside(error) and not _rational_overflow(error):
            raise
        try:
            return abs(_as_fraction(actual) - _as_fraction(expected)) <= _as_fraction(tolerance)
        except (TypeError, ValueError, OverflowError):
            return None


def _as_fraction(value: Any) -> fractions.Fraction:
    """*value* as an exact `fractions.Fraction`, an integer through `int` first.

    `Fraction` keeps the numerator an `Integral` gives it, so a `numpy.int64` stayed a fixed-width integer inside
    it and overflowed again the moment a bignum met it in the exact arithmetic.
    """
    return fractions.Fraction(int(value) if isinstance(value, numbers.Integral) else value)


def _rational_overflow(error: BaseException) -> bool:
    """Whether *error* is `Fraction` overflowing its own conversion to ``float``, which an exact measure removes.

    `Fraction` meets a ``float`` by converting itself through `numbers.Rational.__float__`, which is Python code,
    so `raised_inside` read the overflow as a bug in the value.  The call decides instead: the operator the
    arithmetic called is `Fraction`'s own, and the overflow was raised in the conversion's own code, converting a
    `Fraction`.  Checked by code object at both ends, since a module's name or namespace can be claimed by a
    function of anybody's, the conversion's code alone can be reached from a value's own method, and both can
    be borrowed by a class of anybody's, which is why the value converted has to be a `Fraction` as well.
    """
    called = error.__traceback__.tb_next if error.__traceback__ is not None else None
    if not isinstance(error, OverflowError) or called is None:
        return False
    raised = called
    while raised.tb_next is not None:
        raised = raised.tb_next
    arithmetic = (fractions.Fraction.__sub__.__code__, fractions.Fraction.__rsub__.__code__)
    conversion = (numbers.Rational.__float__.__code__, fractions.Fraction.__float__.__code__)
    converted = raised.tb_frame.f_locals.get("self")
    return (
        called.tb_frame.f_code in arithmetic
        and raised.tb_frame.f_code in conversion
        and isinstance(converted, fractions.Fraction)
    )


def _window_holds(middle, value, tolerance) -> bool:
    """Whether *value* lies in the closed window *tolerance* either side of *middle*."""
    try:
        low, high = tolerance_window(middle, tolerance)
    except WindowRefusedError:
        return False
    if type(value) is type(low) is type(high) is float:
        return low <= value <= high
    return holds(value, low, "ge") and holds(value, high, "le")


def _is_nan(value) -> bool:
    """Whether the value is a NaN, without converting what never is one.

    A `Decimal` is asked through its base type: a signalling NaN refuses to become a float, and reading
    it as "not a NaN" is the one answer it certainly is not.  Not through the value's own `is_nan`,
    which a subclass owns: measured, one saying it was a NaN turned a passing `is_close_to` into a
    failure.  `_is_infinite` reads the same question the same way.

    An `int` or any other rational is never a NaN and is not converted: past the float range the
    conversion overflows, and for a `Fraction` it overflows inside Python code, which read as a bug in the
    value.  Any other value is converted, and an error from a conversion of its own is handed on:
    swallowed, `is_not_nan()` held on a value nothing could read.
    """
    if isinstance(value, float):
        return math.isnan(value)
    if isinstance(value, decimal.Decimal):
        return decimal.Decimal.is_nan(value)
    if isinstance(value, (int, numbers.Rational)):
        return False
    return math.isnan(value)


def _is_infinite(value) -> bool:
    """Whether a real number other than a `Decimal` is itself an infinity.

    A `float` directly.  Any other value is asked through `math.isinf`, since a `numpy.float32` infinity is
    not a `float` and was read as finite, and one with no conversion is refused there, as the assertions
    always refused it.  A rational never is one, and an `int` or a `Fraction` past the float range would
    overflow the conversion.  `_non_finite` reads a `Decimal` through its base type's own method, and the
    assertions asking this refuse one.

    The conversion alone would call a finite value past the float range infinite, a `numpy.longdouble` or
    an arbitrary-precision float, so the value's own comparison has to agree.  A conversion of their own
    that raises is a bug in the value and is handed on, as `_is_nan` does.
    """
    if isinstance(value, float):
        return math.isinf(value)
    if isinstance(value, (int, numbers.Rational)):
        return False
    return math.isinf(value) and bool(value == math.inf or value == -math.inf)


def _non_finite(value) -> str:
    """``"nan"`` or ``"inf"`` for a value closeness answers by rule, ``""`` for one it measures.

    One pass per operand: a float, a `Decimal` and a type with no conversion answer before either question.
    The conversion is read off the type rather than the `numbers` ABCs, which cost a datetime pair a quarter
    of its `is_close_to`, measured, and a datetime is measured rather than refused.
    """
    if isinstance(value, float):
        if math.isfinite(value):
            return ""
        return "nan" if math.isnan(value) else "inf"
    if isinstance(value, decimal.Decimal):
        if decimal.Decimal.is_finite(value):
            return ""
        return "nan" if decimal.Decimal.is_nan(value) else "inf"
    if isinstance(value, int) or not hasattr(type(value), "__float__"):
        return ""
    if _is_nan(value):
        return "nan"
    return "inf" if _is_infinite(value) else ""


class WindowRefusedError(TypeError):
    """The two operands form no window: neither the arithmetic nor an exact conversion takes them.

    A `TypeError` still, so a caller that let the operand's own refusal out keeps letting this one out,
    and a matcher, which may not raise, can tell it from a `__sub__` of somebody's own that raised.
    """


def tolerance_window(middle: Any, tolerance: Any) -> tuple[Any, Any]:
    """The closed interval ``middle`` plus and minus ``tolerance``.

    Typed as `Any` because the pairing is a run-time fact: the assertion has refused every combination
    but two before it asks, a number against a number and a datetime against a timedelta, and a checker
    reading the public signature alone is right to refuse the arithmetic.  A pair inside that domain can
    still refuse, since a class registered as a `numbers.Number` need not subtract, which is what
    `WindowRefusedError` is for: it hands back the operands' own refusal as something a matcher may answer
    "no match" to.
    """
    try:
        return middle - tolerance, middle + tolerance
    except (TypeError, OverflowError) as refusal:
        if raised_inside(refusal) and not _rational_overflow(refusal):  # their own `__sub__` raised: a bug
            raise
        if not all(isinstance(operand, numbers.Number) for operand in (middle, tolerance)):
            raise WindowRefusedError(str(refusal)) from None
        # a `Decimal` refuses a `float` or a `Fraction` and a bignum overflows a `float`, all converting
        # exactly, while an infinite or NaN one does not convert at all
        try:
            exact, span = _as_fraction(middle), _as_fraction(tolerance)
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
    actual = as_held(actual)
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
    ``_guarded_equal`` from this module, so the module-level import would be a cycle.
    """
    if kind_of(actual) is kind_of(expected):
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
        if config.ignore_null and field is not None and as_held(expected) is None:
            return "equal"  # a named field the expected side leaves None is not compared
        comparator = _resolve_comparator(actual, config, field=field)
        if comparator is not None:
            agreed = verdict(comparator(as_held(actual), as_held(expected)), subject="the comparator")
            return "equal" if agreed else "leaf"
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
            if type(actual) not in _EQ_ATOMIC and _guarded_equal(actual, expected):
                # `[True] == [1]`: a container says nothing about the types inside it, so the walk keeps going
                return "strict"
        if config.tolerance is not None and _is_real_number(as_held(actual)) and _is_real_number(as_held(expected)):
            try:
                within = _within_tolerance(as_held(actual), as_held(expected), config.tolerance)
            except UnorderableError:
                return _plain_decision(actual, expected, config, at_root=at_root)
            # a keyed field's key still holds equal what the tolerance would not: it only ever loosens `==`
            return "equal" if within or (type(actual) is KeyedValue and actual == expected) else "leaf"
    return _plain_decision(actual, expected, config, at_root=at_root)


def _plain_decision(actual, expected, config: _CompareConfig | None, *, at_root: bool = False) -> str:
    """``==``'s answer as a decision, where under a config a pair ruled out by its kind alone is a leaf."""
    if actual is expected and not at_root:
        # the same rule a container's own `==` applies to its members, and the verdict came from that `==`:
        # without it the diff listed a NaN both sides hold as differing, and the hint blamed it
        return "equal"
    if _guarded_equal(actual, expected):
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
