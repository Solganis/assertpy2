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
import sys
import types
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from ._require import argument, raised_inside, refuse

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
    range and a `Decimal` refuses a `numpy` integer, in a list or a mapping as much as on its own.  A `numpy`
    scalar against a list or a tuple answers an array, element by element (`broadcasts`), and is unequal to it
    as a number is.  Asked as written first, so every other pair keeps the answer and the cost it always had.
    """
    try:
        equal = actual == expected
    except (decimal.InvalidOperation, OverflowError, TypeError, ValueError) as refusal:
        return equal_past(actual, expected, refusal)
    if type(equal) is not bool and broadcasts(actual, expected, answer=equal):
        return False
    return bool(equal)


_SEQUENCES = (list, tuple)


def numpy_duration(value: object) -> bool:
    """Whether *value* is a `numpy.timedelta64`, a duration `numpy` registers as an integer all the same."""
    numpy = sys.modules.get("numpy")
    return numpy is not None and type(value) is numpy.timedelta64


_UNANSWERED: Any = object()


def broadcasts(actual: Any, expected: Any, *, ordering: bool = False, answer: object = _UNANSWERED) -> bool:
    """Whether `numpy` answered ``actual == expected``, or ``actual < expected`` with *ordering*, element by element.

    One is a `numpy` scalar and the other a list or a tuple, which the scalar turns into an array.  It answers an
    array, true where one element was equal, or raises on its truth where there were several, or on building the
    array of a ragged list.  A number is simply unequal to a list and unordered against it.  Only where the scalar's
    operator in that place is one `numpy` wrote, its own on the left and its reflected one on the right, and where
    the *answer* is at hand, only for the array itself: a subclass that wrote the operator keeps the answer it
    gives, and a sequence's own operator that declined the scalar leaves the answer to `numpy`.
    """
    numpy = sys.modules.get("numpy")
    if numpy is None or (answer is not _UNANSWERED and type(answer) is not numpy.ndarray):
        return False
    first, second = type(actual), type(expected)
    if issubclass(first, numpy.generic) and issubclass(second, _SEQUENCES):
        return _written_by_numpy(first, "__lt__" if ordering else "__eq__")
    if issubclass(second, numpy.generic) and issubclass(first, _SEQUENCES):
        return _written_by_numpy(second, "__gt__" if ordering else "__eq__")
    return False


def _written_by_numpy(kind: type, name: str) -> bool:
    """Whether *kind*'s operator *name* is one `numpy` wrote, read off the class without running it."""
    owner = getattr(inspect.getattr_static(kind, name, None), "__objclass__", None)
    return getattr(owner, "__module__", None) == "numpy"


def may_broadcast(value: Any) -> bool:
    """Whether *value* can be one side of a pair `broadcasts` names, while `numpy` is loaded."""
    numpy = sys.modules.get("numpy")
    return numpy is not None and issubclass(type(value), (numpy.generic, *_SEQUENCES))


def mixes_broadcasting(values: Any, others: Any = ()) -> bool:
    """Whether a `numpy` scalar and a list or a tuple meet across *values* and *others*, or within *values*.

    One linear pass over the types, for a walk that compares every pair and is quadratic already.
    """
    numpy = sys.modules.get("numpy")
    if numpy is None:
        return False
    try:
        kinds: Any = {*map(type, values), *map(type, others)}
    except TypeError:  # a metaclass may refuse to hash its classes
        kinds = [*map(type, values), *map(type, others)]
    return any(issubclass(kind, numpy.generic) for kind in kinds) and any(
        issubclass(kind, _SEQUENCES) for kind in kinds
    )


def member(item: Any, container: Any, verify: bool = True) -> bool:
    """``item in container`` as a verdict, each element asked as `equals` asks it once ``in`` raised.

    A set or a mapping cannot hold a signalling NaN, which refuses to hash, alone or inside a tuple, so it holds
    none: answered where the lookup ends in a built-in set's or dict's own (`_searches_by_hash`), which refuses
    nothing but an unhashable key, and the item would hash but for the NaNs in it.  A built-in list, tuple, deque
    or dict's values, or a set or mapping the item hashes for, whose comparison refused a pair, is searched
    element by element too.  Any other error raised inside the container's or an element's own code is handed
    on.  An iterator is searched on from where the raising ``in`` stopped, which is enough: every element before
    it compared unequal, or ``in`` would have answered, and the one that raised met a NaN or an int no float can
    equal.  An item that may broadcast (`may_broadcast`) is searched element by element in a container that
    walks by ``==``, before ``in`` could take the truth of an array; *verify* false is a caller that knows no such
    item comes.  A set or a mapping meets one only through a hash collision, whose ambiguous truth is answered
    by the same walk.
    """
    if verify and type(item) not in _PLAIN and may_broadcast(item) and _walks_by_equality(container):
        return any(element is item or equals(element, item) for element in container)
    try:
        return item in container
    except (decimal.InvalidOperation, OverflowError) as refusal:
        if raised_inside(refusal):
            raise
        return any(element is item or equals(element, item) for element in container)
    except (ValueError, DeprecationWarning) as ambiguous:
        # a hash collision met a `numpy` scalar with a tuple, and `in` took the truth of their array
        if raised_inside(ambiguous) or not may_broadcast(item) or not _searched_again(container):
            raise
        return any(element is item or equals(element, item) for element in container)
    except TypeError as refusal:
        # a dict's items view hashes the key of a pair alone, and asks about the value only once the key is there
        pair = type(container) is type({}.items()) and isinstance(item, tuple) and len(item) == 2
        key = item[0] if pair else item
        hashed = _searches_by_hash(container)
        if hashed and _unhashable_for_a_nan_alone(key):
            return False
        if raised_inside(refusal) or not (_walks_by_equality(container) or (hashed and _hashes(key))):
            raise
        return any(element is item or equals(element, item) for element in container)


def _walks_by_equality(container: Any) -> bool:
    """Whether ``in`` walks *container* asking ``==``: a built-in list, tuple, deque or dict's values.

    A subclass counts where it keeps both the search and the iteration of the one it derives from, read off the
    class without running either.
    """
    kind = type(container)
    if kind in _SEARCHED_BY_EQUALITY:
        return True
    return any(
        issubclass(kind, base)
        and inspect.getattr_static(kind, "__contains__") is inspect.getattr_static(base, "__contains__")
        and inspect.getattr_static(kind, "__iter__") is inspect.getattr_static(base, "__iter__")
        for base in (list, tuple, collections.deque)
    )


def _searched_again(container: Any) -> bool:
    """Whether *container* can be searched a second time: a built-in sequence, set or mapping, never an iterator."""
    return _walks_by_equality(container) or _searches_by_hash(container)


REFUSALS = (TypeError, decimal.InvalidOperation, OverflowError, ValueError)
"""What ``==`` raises for a pair it refuses to compare: a `Decimal` against a `numpy` integer, a signalling NaN, a
`numpy` float against a Python int past its range, and the truth of the array a `numpy` integer answers against a
tuple key its hash collided with."""


def held_key(keys: Any, key: Any) -> tuple[bool, Any]:
    """Whether *keys* holds *key*, as `member` asks it, and the very key it holds there.

    Where ``in`` answers, that is *key* itself.  Where it refused a comparison after an equal hash, as a `Decimal`
    refuses a `numpy` integer, the key held is the one `equals` finds, which a lookup by that very object reaches
    through identity and never compares again.  Only a set or a mapping whose lookup ends in a built-in one
    (`_searches_by_hash`) is searched that way; anybody else's refusal is handed on.
    """
    try:
        return key in keys, key
    except REFUSALS:
        if not _searches_by_hash(keys):
            raise
        if not member(key, keys):
            return False, key
    return True, next(held for held in keys if held is key or equals(held, key))


def lookup(mapping: Any, key: Any, refusal: BaseException | None = None) -> tuple[bool, Any]:
    """Whether *mapping* holds *key*, and ``mapping[key]`` where it does, the key found as `held_key` finds it.

    *refusal* is what the caller's own lookup raised, handed on where it came from code of the mapping's, the
    key's or a value's own rather than from the comparison of two keys.
    """
    if refusal is not None and raised_inside(refusal):
        raise refusal
    found, held = held_key(mapping, key)
    return found, mapping[held] if found else None


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
    whatever else the pair holds, and so is a refusal nothing here answers.  A `ValueError` is otherwise answered
    only for a pair `broadcasts` names, as unequal.
    """
    if raised_inside(refusal):
        raise refusal
    if isinstance(refusal, decimal.InvalidOperation) and (nan_operand(actual) or nan_operand(expected)):
        return False
    walked = _equal_by_element(actual, expected)
    if walked is not None:
        return walked
    if isinstance(refusal, ValueError):
        if broadcasts(actual, expected):
            return False
        raise refusal
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
    """Built-in ``==`` over two lists, tuples, sets or mappings, asked of each element, else ``None``.

    A set equals another of its size that holds each of its elements, and a mapping one of its size that holds
    each of its keys, found as `member` finds it, under an equal value.
    """
    for kind in (list, tuple):
        if isinstance(actual, kind) and isinstance(expected, kind):
            if type(actual).__eq__ is not kind.__eq__ or type(expected).__eq__ is not kind.__eq__:
                return None
            pairs = zip(actual, expected, strict=False)
            return len(actual) == len(expected) and all(left is right or equals(left, right) for left, right in pairs)
    if isinstance(actual, (set, frozenset)) and isinstance(expected, (set, frozenset)):
        if not {type(actual).__eq__, type(expected).__eq__} <= {set.__eq__, frozenset.__eq__}:
            return None
        return len(actual) == len(expected) and all(member(element, expected) for element in actual)
    if isinstance(actual, dict) and isinstance(expected, dict):
        return _mappings_equal(actual, expected)
    return None


def _mappings_equal(actual: dict, expected: dict) -> bool | None:
    """Two dicts, as ``==`` compares them: two `OrderedDict` values item by item in order, else key by key."""
    kinds = {type(actual).__eq__, type(expected).__eq__}
    if not kinds <= {dict.__eq__, collections.OrderedDict.__eq__}:
        return None
    if kinds == {collections.OrderedDict.__eq__}:
        return equals(list(actual.items()), list(expected.items()))
    return len(actual) == len(expected) and all(_held_alike(key, held, expected) for key, held in actual.items())


def _held_alike(key: Any, held: Any, mapping: Any) -> bool:
    """Whether *mapping* holds *key* under a value equal to *held*."""
    found, other = lookup(mapping, key)
    return found and (other is held or equals(held, other))


def _order_past(actual: Any, expected: Any, refusal: Exception) -> int | None:
    """How a pair orders once its own operator raised *refusal*: ``-1``, ``0`` or ``1``, ``None`` for a NaN.

    An `OverflowError` is a `numpy` float converting a Python int past its range, and a `TypeError` the operator
    refusing the pair, as a `Decimal` refuses a `numpy` integer.  Where both stand for exact values the pair
    orders by them, an infinity above every finite value and a NaN against nothing.  A `TypeError` between any
    other two leaves the pair with no order.  Raised inside a comparison of the value's own, either is a bug in
    the value and is handed on, and so is an overflow from a value with no exact value to order by.  A
    `ValueError` otherwise leaves only a pair `broadcasts` names either way with no order, and is handed on.
    """
    if raised_inside(refusal):
        raise refusal
    if _lexicographic(actual, expected):
        return _order_by_element(actual, expected)
    if isinstance(refusal, ValueError):
        if broadcasts(actual, expected, ordering=True) or broadcasts(expected, actual, ordering=True):
            raise UnorderableError("pair") from None
        raise refusal
    left, right = _exact_real(actual), _exact_real(expected)
    if left is None or right is None:
        if isinstance(refusal, TypeError):
            raise UnorderableError("pair") from None
        raise refusal
    if isinstance(left, str) or isinstance(right, str):
        return None
    return (left > right) - (left < right)


def _lexicographic(actual: Any, expected: Any) -> bool:
    """Whether the pair is two lists or two tuples ordered by the built-in ``<``, element by element."""
    return any(
        isinstance(actual, kind)
        and isinstance(expected, kind)
        and type(actual).__lt__ is kind.__lt__
        and type(expected).__lt__ is kind.__lt__
        for kind in (list, tuple)
    )


def _order_by_element(actual: Any, expected: Any) -> int | None:
    """Two sequences in the built-in order: the first pair `equals` calls unequal decides, else the length.

    That pair ordered by `compare`, and ``None`` where it orders neither way, as a NaN does.
    """
    for left, right in zip(actual, expected, strict=False):
        if left is right or equals(left, right):
            continue
        return compare(left, right) or None
    return (len(actual) > len(expected)) - (len(actual) < len(expected))


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
    if issubclass(type(value), int) or issubclass(type(value), numbers.Integral):
        whole = exact_int(value)
        return None if whole is None else (0, fractions.Fraction(whole))
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


def exact_int(value: Any) -> int | None:
    """*value* as the int it holds, read by `int`'s own `__index__` or a `numpy` integer's, else ``None``.

    Never by a conversion of the value's own, which a registered `numbers.Integral` can make answer anything.
    """
    kind = type(value)
    if issubclass(kind, int):
        return int.__index__(value)
    if issubclass(kind, numbers.Integral):
        index = _known_number_method(kind, "__index__", types.WrapperDescriptorType)
        return None if index is None else index(value)
    return None


def whole_number(value: Any) -> int | None:
    """*value* as the int it stands for where it is an integer, which a bool is not, else ``None``."""
    if type(value) is int:
        return value
    return None if isinstance(value, bool) else exact_int(value)


def require_integer(value: object, name: str | None = None) -> int:
    """*value* as the int it stands for (`whole_number`), or refused as no integer: as the argument *name*, else val.

    A caller on an assertion's own path asks ``value if type(value) is int else require_integer(value, name)``:
    asked through the call with its subject built up front, a plain `int` cost `is_length` 37%.
    """
    whole = whole_number(value)
    if whole is None:
        refuse(value, "an integer", subject="val" if name is None else argument(name))
    return whole


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
        less = left < right
        if type(less) is not bool and broadcasts(left, right, ordering=True, answer=less):
            raise UnorderableError("pair")
        if less:
            return -1
        greater = right < left
        if type(greater) is not bool and broadcasts(right, left, ordering=True, answer=greater):
            raise UnorderableError("pair")
        if greater:
            return 1
    except (TypeError, OverflowError, ValueError) as refusal:
        order = _order_past(actual, expected, refusal)
        return 0 if order is None else order
    except decimal.InvalidOperation as signal:
        return _order_past_signal(actual, expected, signal)
    return 0  # neither less nor greater, which is what a float NaN answers and `holds` keeps from reading equal


def _order_past_signal(actual: Any, expected: Any, signal: decimal.InvalidOperation) -> int:
    """How a pair orders once a `Decimal` NaN signalled at ``<``: a NaN operand neither way, two sequences by element.

    Asked after the comparison rather than before: checked first, `'a'` against a NaN read as a verdict where the
    same pair without one is refused.  The operands decide and not the traceback: measured, a signal comes from
    one frame under the C accelerator and from four under `_pydecimal`, so `raised_inside` answered the
    interpreter build.  A `numpy` scalar against a sequence holding a NaN is no order, as a number against a list.
    Any other signal is handed on.
    """
    if nan_operand(actual) or nan_operand(expected):
        return 0
    if broadcasts(actual, expected, ordering=True) or broadcasts(expected, actual, ordering=True):
        raise UnorderableError("pair") from None
    if not _lexicographic(actual, expected):
        raise signal
    order = _order_by_element(actual, expected)
    return 0 if order is None else order


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
