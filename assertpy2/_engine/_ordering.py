"""Ordering as one decision: can these two be ordered, and if so, how do they compare.

The comparison itself is an operator and needs no core.  What did need one is the rule *around* it,
because it was written twice and in two different shapes.  The builder listed types (`complex` has no
ordering, a `datetime` wants a `datetime`, a number wants a number) and then tried the operator; the
matcher tried the operator and answered False on `TypeError`.  Two spellings of one rule is exactly how
`bytes` drifted apart in the text matchers, and it is a matter of time rather than of luck.

`compare` gives both callers the same three answers: ordered one way, ordered the other, or not
orderable at all.  What each does with "not orderable" stays theirs, and stays different on purpose: a
builder refuses the call, because a wrong subject there is a mistake in the test, while a matcher
answers "no match", because it feeds `==` and the combinators where raising would be wrong.
"""

from __future__ import annotations

import collections
import collections.abc
import decimal
import fractions
import inspect
import numbers
import operator
import types
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from ._require import raised_inside

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# ordering exists for real numbers and not for complex ones, whatever `numbers.Number` says
_UNORDERED = frozenset({complex})
# types whose ordering needs no rule at all: identical on both sides, total, and not kind-bound
_PLAIN = frozenset({int, float, str, bytes})
_DIRECT = {"lt": operator.lt, "le": operator.le, "gt": operator.gt, "ge": operator.ge}
_SEARCHED_BY_EQUALITY = frozenset({list, tuple, collections.deque, type({}.values())})


class UnorderableError(Exception):
    """The pair cannot be ordered, with the reason the caller needs to explain it.

    ``kind`` is one of ``"value"`` (this value has no ordering at all), ``"kind"`` (both are ordered,
    but not against each other's type) or ``"pair"`` (the operator itself refused them).
    """

    def __init__(self, kind: str, *, wanted: type | None = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.wanted = wanted


def nan_operand(value: Any) -> bool:
    """A `float`, `Decimal` or `numpy` float NaN, unordered against everything, the `Decimal` one by signalling.

    Asked by type rather than through `math.isnan`, which would call `__float__` on somebody else's
    number and raises on a signalling `Decimal` instead of answering.

    Through the base type's own operator and method rather than the value's, the rule `_is_infinite`
    already follows: this answer decides whether an `InvalidOperation` is a verdict or a bug in the
    value, so a subclass overriding `is_nan` could have its own signal absorbed, and one overriding
    `__ne__` could call itself unordered against everything.  A `numpy` float other than `float64` is no
    `float`, and is read through its own type's `as_integer_ratio` as the exact order reads it: missed, it
    let a `Decimal`'s signal out and passed `is_sorted` over a list a `float` NaN fails.  Subclasses
    included, and only off a class built by `type` itself, since a metaclass of anybody's answers reads.  An
    integer, built in or registered, is never one, and is not read at all.
    """
    if isinstance(value, float):
        return bool(float.__ne__(value, value))
    if isinstance(value, decimal.Decimal):
        return decimal.Decimal.is_nan(value)
    kind = type(value)
    if kind is int or type(kind) is not type or issubclass(kind, numbers.Integral):
        return False
    return _exact_real(value) == "nan"


def _kind_of(value: Any) -> type | None:
    """The date-and-time kind a value orders within, subclasses included, or ``None`` for anything else.

    By kind rather than by exact type: `pandas.Timestamp` and `freezegun`'s clock are `datetime`
    subclasses, and refusing them against a `datetime` boundary failed an assertion that holds.
    """
    for kind in (datetime, date, timedelta, time):  # `datetime` ahead of `date`, which it subclasses
        if isinstance(value, kind):
            return kind
    return None


def _equal(actual: Any, expected: Any) -> bool:
    """``==``, with a NaN on either side answering ``False`` rather than signalling."""
    if nan_operand(actual) or nan_operand(expected):
        return False
    return equals(actual, expected)


def equals(actual: Any, expected: Any) -> bool:
    """``actual == expected`` as a verdict, where Python's own ``==`` would raise instead of answering.

    A signalling `Decimal` NaN signals at ``==``, a `numpy` float overflows converting a Python int past its
    range and a `Decimal` refuses a `numpy` integer, in a list or a mapping as much as on its own.  Asked as
    written first, so every other pair keeps the answer and the cost it always had.
    """
    try:
        return bool(actual == expected)
    except (decimal.InvalidOperation, OverflowError, TypeError) as refusal:
        return equal_past(actual, expected, refusal)


def member(item: Any, container: Any) -> bool:
    """``item in container`` as a verdict, each element asked as `equals` asks it once ``in`` raised.

    A set or a mapping cannot hold a signalling NaN, which refuses to hash, alone or inside a tuple, so it holds
    none: answered where the lookup ends in a built-in set's or dict's own (`_searches_by_hash`), which refuses
    nothing but an unhashable key, and the item would hash but for the NaNs in it.  A built-in list, tuple, deque
    or dict's values, or a set or mapping the item hashes for, whose comparison refused a pair, is searched
    element by element too.  Any other error raised inside the container's or an element's own code is handed
    on.  An iterator is searched on from where the raising ``in`` stopped, which is enough: every element before
    it compared unequal, or ``in`` would have answered, and the one that raised met a NaN or an int no float can
    equal.
    """
    try:
        return item in container
    except (decimal.InvalidOperation, OverflowError) as refusal:
        if raised_inside(refusal):
            raise
        return any(element is item or equals(element, item) for element in container)
    except TypeError as refusal:
        # a dict's items view hashes the key of a pair alone, and asks about the value only once the key is there
        pair = type(container) is type({}.items()) and isinstance(item, tuple) and len(item) == 2
        key = item[0] if pair else item
        hashed = _searches_by_hash(container)
        if hashed and _unhashable_for_a_nan_alone(key):
            return False
        if raised_inside(refusal) or not (type(container) in _SEARCHED_BY_EQUALITY or (hashed and _hashes(key))):
            raise
        return any(element is item or equals(element, item) for element in container)


def _hashes(key: Any) -> bool:
    """Whether *key* hashes, so a lookup that refused it refused a comparison rather than the key."""
    try:
        hash(key)
    except TypeError:
        return False
    return True


def _unhashable_for_a_nan_alone(item: Any) -> bool:
    """Whether *item* is a `Decimal` NaN, or a tuple holding one that would hash if its NaNs did."""
    if nan_operand(item):
        return True
    if not isinstance(item, tuple):
        return False
    held = False
    for element in item:
        if _unhashable_for_a_nan_alone(element):
            held = True
            continue
        try:
            hash(element)
        except TypeError:
            return False
    return held


def _searches_by_hash(container: Any) -> bool:
    """Whether ``in`` over *container* ends in a built-in set's or dict's own lookup, all the way down.

    A built-in set or dict, or a view of one, directly.  A `UserDict` whose `data` is a built-in dict, and the
    keys view over such a mapping, by following the path, read without running a descriptor of anybody's.
    """
    searched = inspect.getattr_static(type(container), "__contains__", None)
    built_in = (set, frozenset, dict, type({}.keys()), type({}.items()))
    if any(searched is inspect.getattr_static(kind, "__contains__") for kind in built_in):
        return True
    if searched is collections.UserDict.__contains__:
        return type(inspect.getattr_static(container, "data", None)) is dict
    if searched is collections.abc.KeysView.__contains__:
        # the slot `MappingView` declares, read by its own descriptor, and only where no subclass has shadowed it
        slot = inspect.getattr_static(collections.abc.MappingView, "_mapping")
        return inspect.getattr_static(type(container), "_mapping") is slot and _searches_by_hash(
            slot.__get__(container)
        )
    return False


def equal_past(actual: Any, expected: Any, refusal: Exception) -> bool:
    """Whether a pair whose own ``==`` raised *refusal* is equal, or *refusal* again where nothing can answer.

    A NaN equals nothing, which answers a signal wherever one of the pair is a NaN, as the operands decide it for
    ordering.  Two lists, two tuples or two mappings compared by the built-in ``==`` are equal element by
    element, each asked as `equals` asks it.  Two numbers whose operator overflowed or refused the other are equal
    where their exact values are.  An error raised inside a comparison of the value's own is handed on first,
    whatever else the pair holds, and so is a refusal nothing here answers.
    """
    if raised_inside(refusal):
        raise refusal
    if isinstance(refusal, decimal.InvalidOperation) and (nan_operand(actual) or nan_operand(expected)):
        return False
    walked = _equal_by_element(actual, expected)
    if walked is not None:
        return walked
    left, right = _exact_real(actual), _exact_real(expected)
    if not isinstance(refusal, decimal.InvalidOperation) and left is not None and right is not None:
        return not isinstance(left, str) and left == right
    # a scalar against a container broadcast by `numpy`: the NaN that signalled equals nothing it met
    if isinstance(refusal, decimal.InvalidOperation) and (_holds_nan(actual) or _holds_nan(expected)):
        return False
    raise refusal


def _holds_nan(value: Any, seen: frozenset[int] = frozenset()) -> bool:
    """Whether *value* is a `Decimal` NaN or a list, tuple or dict holding one at any depth."""
    if id(value) in seen:
        return False
    within = seen | {id(value)}
    if isinstance(value, dict):
        return any(_holds_nan(held, within) for held in value.values())
    if isinstance(value, (list, tuple)):
        return any(_holds_nan(held, within) for held in value)
    return nan_operand(value)


def _equal_by_element(actual: Any, expected: Any) -> bool | None:
    """Built-in ``==`` over two lists, two tuples or two mappings, asked of each element, else ``None``."""
    for kind in (list, tuple):
        if isinstance(actual, kind) and isinstance(expected, kind):
            if type(actual).__eq__ is not kind.__eq__ or type(expected).__eq__ is not kind.__eq__:
                return None
            pairs = zip(actual, expected, strict=False)
            return len(actual) == len(expected) and all(left is right or equals(left, right) for left, right in pairs)
    if isinstance(actual, dict) and isinstance(expected, dict):
        if type(actual).__eq__ is not dict.__eq__ or type(expected).__eq__ is not dict.__eq__:
            return None
        if actual.keys() != expected.keys():
            return False
        return all(actual[key] is expected[key] or equals(actual[key], expected[key]) for key in actual)
    return None


def _order_past(actual: Any, expected: Any, refusal: Exception) -> int | None:
    """How a pair orders once its own operator raised *refusal*: ``-1``, ``0`` or ``1``, ``None`` for a NaN.

    An `OverflowError` is a `numpy` float converting a Python int past its range, and a `TypeError` the operator
    refusing the pair, as a `Decimal` refuses a `numpy` integer.  Where both stand for exact values the pair
    orders by them, an infinity above every finite value and a NaN against nothing.  A `TypeError` between any
    other two leaves the pair with no order.  Raised inside a comparison of the value's own, either is a bug in
    the value and is handed on, and so is an overflow from a value with no exact value to order by.
    """
    if raised_inside(refusal):
        raise refusal
    left, right = _exact_real(actual), _exact_real(expected)
    if left is None or right is None:
        if isinstance(refusal, TypeError):
            raise UnorderableError("pair") from None
        raise refusal
    if isinstance(left, str) or isinstance(right, str):
        return None
    return (left > right) - (left < right)


def _exact_real(value: Any) -> tuple[int, fractions.Fraction] | str | None:
    """*value* as ``(rank, exact)`` for ordering past an overflow, ``"nan"``, or ``None`` with no exact value.

    The rank puts an infinity above or below every finite value, whose exact value is compared otherwise.  An
    integer is read by `int`'s own `__index__` or a `numpy` integer's, never by a conversion of the value's own,
    which a registered `numbers.Integral` can make answer anything.  Any other number is read through
    `as_integer_ratio`, which never rounds and refuses an infinity and a NaN by the error it raises, rather than
    through a conversion to ``float``.  Only as `float`, `Decimal` or a `numpy` float wrote it in C,
    whose errors mean exactly that, and called as the type holds it, as is its ``>`` for an infinity's sign:
    any other, on the class or reached through the instance, can raise either error for a finite value, and
    would order it as an infinity or leave it unordered.
    """
    if issubclass(type(value), int):
        return 0, fractions.Fraction(int.__index__(value))
    if issubclass(type(value), numbers.Integral):
        index = _known_number_method(type(value), "__index__", types.WrapperDescriptorType)
        return None if index is None else (0, fractions.Fraction(index(value)))
    ratio = _known_number_method(type(value), "as_integer_ratio", types.MethodDescriptorType)
    if ratio is None:
        return None
    try:
        numerator, denominator = ratio(value)
    except OverflowError:
        greater = _known_number_method(type(value), "__gt__", types.WrapperDescriptorType)
        if greater is None:
            return None
        return (1 if greater(value, 0) else -1), fractions.Fraction(0)
    except ValueError:
        return "nan"
    return 0, fractions.Fraction(int(numerator), int(denominator))


def _known_number_method(owner: type, name: str, kind: type) -> Any | None:
    """*owner*'s *name* as the type holds it, if `float`, `Decimal` or a `numpy` number wrote it in C, else ``None``."""
    method = inspect.getattr_static(owner, name, None)
    maker = getattr(method, "__objclass__", None)
    known = maker in (float, decimal.Decimal) or getattr(maker, "__module__", None) == "numpy"
    # borrowed from another number type, the method refuses the instance with a `TypeError` of its own
    owned = isinstance(maker, type) and issubclass(owner, maker)
    return method if isinstance(method, kind) and known and owned else None


def compare(actual: Any, expected: Any) -> int:
    """``-1``/``0``/``1`` for *actual* against *expected*, or `UnorderableError` when they cannot be ordered.

    A `TypeError` raised *inside* somebody's own `__lt__` travels out untouched: that is a bug in the
    value, not an unorderable pair, and answering it either way would send the reader to the wrong file.
    """
    actual_type = type(actual)
    # the ordinary case first: in a per-element loop, so the frozenset lookup and two `isinstance` were paid each time
    if actual_type is type(expected) and actual_type in _PLAIN:
        return (actual > expected) - (actual < expected)
    if actual_type in _UNORDERED:
        raise UnorderableError("value")
    actual_kind: Any = _kind_of(actual)
    # a subclass that wrote its own `<` is asked instead: the rule is about the stock one being wrong across kinds
    if actual_kind is not None and type(actual).__lt__ is actual_kind.__lt__ and _kind_of(expected) is not actual_kind:
        raise UnorderableError("kind", wanted=actual_kind)
    if (
        actual_kind is None
        and isinstance(actual, numbers.Number)
        and (not isinstance(expected, numbers.Number) or type(expected) in _UNORDERED)
    ):
        raise UnorderableError("kind", wanted=numbers.Number)
    # deliberately dynamic: what may be ordered is decided above, and a checker reading the union sees no `<`
    left: Any = actual
    right: Any = expected
    try:
        if left < right:
            return -1
        if right < left:
            return 1
    except (TypeError, OverflowError) as refusal:
        order = _order_past(actual, expected, refusal)
        return 0 if order is None else order
    except decimal.InvalidOperation:
        # a `Decimal` NaN signals rather than answering.  Asked here rather than before the comparison:
        # checked first, `'a'` against a NaN read as a verdict where the same pair without one is refused.
        # The operands decide and not the traceback: measured, a signal comes from one frame under the C
        # accelerator and from four under `_pydecimal`, so `raised_inside` answered the interpreter build
        if nan_operand(actual) or nan_operand(expected):
            return 0
        raise
    return 0  # neither less nor greater, which is what a float NaN answers and `holds` keeps from reading equal


def holds(actual: Any, expected: Any, relation: str) -> bool:
    """Whether *relation* (``lt``/``le``/``gt``/``ge``) holds between the two.

    `NaN` is unordered against everything including itself, and `compare` answers ``0`` for it because
    neither side is less than the other.  That would make `le`/`ge` true, which is the one place where
    "not less, not greater" does not mean "equal", so equality is asked separately.
    """
    actual_type = type(actual)
    if actual_type is type(expected) and actual_type in _PLAIN:
        # the shortcut `compare` takes, one call earlier: building the answer through a dict of four keys cost most
        return _DIRECT[relation](actual, expected)
    order = compare(actual, expected)
    if order == 0 and relation in ("le", "ge") and not _equal(actual, expected):
        return False
    return {"lt": order < 0, "le": order <= 0, "gt": order > 0, "ge": order >= 0}[relation]


def first_out_of_order(
    items: Iterable[Any], *, key: Callable[[Any], Any], reverse: bool = False
) -> tuple[int, Any, Any] | None:
    """The first adjacent pair that breaks the order, as ``(index, earlier, later)``, or ``None``.

    Returned rather than reported, so both spellings get what they need from one walk: the assertion
    names the pair and where it sits, and a matcher only looks at whether there was one.
    """
    previous: Any = None
    previous_key: Any = None
    for index, current in enumerate(items):
        current_key = key(current)
        # through `compare`, not `<`: a raise here reads to the origin check as a plain type mismatch.
        # The key is carried rather than recomputed, which doubled the calls to the caller's `key`
        if index > 0 and _out_of_order(current_key, previous_key, reverse=reverse):
            return index - 1, previous, current
        previous = current
        previous_key = current_key
    return None


def _out_of_order(later: Any, earlier: Any, *, reverse: bool) -> bool:
    """Whether *later* breaks the order after *earlier*, a pair holding a NaN vouching for no order at all.

    The NaN is asked only where the pair did not order, a tie or no order, since a NaN orders against
    nothing: asked of every key, a `numpy` float's NaN check cost a sort of ints 18%.
    """
    try:
        order = compare(later, earlier)
    except UnorderableError:
        if nan_operand(later) or nan_operand(earlier):
            return True
        raise
    if order == 0:
        # a tie of two exact ints or strings holds no NaN: asked anyway, a sort of equal ints cost 19%
        never_nan = (int, str, bytes)
        if type(later) in never_nan and type(earlier) in never_nan:
            return False
        return nan_operand(later) or nan_operand(earlier)
    return order > 0 if reverse else order < 0
