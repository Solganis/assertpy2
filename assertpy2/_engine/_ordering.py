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

import numbers
import operator
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from ._require import raised_inside

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# types whose own `<` is defined but wrong to use across kinds: a `datetime` is only ordered against a
# `datetime`, and comparing one with a number is a mistake rather than a verdict
_KIND_BOUND = frozenset({datetime, timedelta, date, time})
# ordering exists for real numbers and not for complex ones, whatever `numbers.Number` says
_UNORDERED = frozenset({complex})
# types whose ordering needs no rule at all: identical on both sides, total, and not kind-bound
_PLAIN = frozenset({int, float, str, bytes})
# the operators behind the four relation names, for the path that needs no rule
_DIRECT = {"lt": operator.lt, "le": operator.le, "gt": operator.gt, "ge": operator.ge}


class UnorderableError(Exception):
    """The pair cannot be ordered, with the reason the caller needs to explain it.

    ``kind`` is one of ``"value"`` (this value has no ordering at all), ``"kind"`` (both are ordered,
    but not against each other's type) or ``"pair"`` (the operator itself refused them).
    """

    def __init__(self, kind: str, *, wanted: type | None = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.wanted = wanted


def compare(actual: Any, expected: Any) -> int:
    """``-1``/``0``/``1`` for *actual* against *expected*, or `UnorderableError` when they cannot be ordered.

    A `TypeError` raised *inside* somebody's own `__lt__` travels out untouched: that is a bug in the
    value, not an unorderable pair, and answering it either way would send the reader to the wrong file.
    """
    actual_type = type(actual)
    # the ordinary case first: two values of the same simple type are ordered by the operator, and no
    # rule below can change that. Reached from every matcher in a loop, so the checks that follow --
    # a frozenset lookup and two `isinstance` against the numeric tower -- were paid per element
    if actual_type is type(expected) and actual_type in _PLAIN:
        return (actual > expected) - (actual < expected)
    if actual_type in _UNORDERED:
        raise UnorderableError("value")
    if actual_type in _KIND_BOUND and type(expected) is not actual_type:
        raise UnorderableError("kind", wanted=actual_type)
    if (
        actual_type not in _KIND_BOUND
        and isinstance(actual, numbers.Number)
        and (not isinstance(expected, numbers.Number) or type(expected) in _UNORDERED)
    ):
        raise UnorderableError("kind", wanted=numbers.Number)
    # the operands are deliberately dynamic here: which pairs may be ordered is decided above, by the
    # rules this module exists to hold, and a checker reading the narrowed union sees no `<` at all
    left: Any = actual
    right: Any = expected
    try:
        if left < right:
            return -1
        if right < left:
            return 1
    except TypeError as exc:
        if raised_inside(exc):
            raise
        raise UnorderableError("pair") from None
    return 0


def holds(actual: Any, expected: Any, relation: str) -> bool:
    """Whether *relation* (``lt``/``le``/``gt``/``ge``) holds between the two.

    `NaN` is unordered against everything including itself, and `compare` answers ``0`` for it because
    neither side is less than the other.  That would make `le`/`ge` true, which is the one place where
    "not less, not greater" does not mean "equal", so equality is asked separately.
    """
    actual_type = type(actual)
    if actual_type is type(expected) and actual_type in _PLAIN:
        # the same shortcut `compare` takes, taken one call earlier: this is the loop body of every
        # ordering matcher, and building the answer through a dict of four keys was most of its cost
        return _DIRECT[relation](actual, expected)
    order = compare(actual, expected)
    if order == 0 and relation in ("le", "ge") and not bool(actual == expected):
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
        if index > 0:
            # asked through `compare` rather than with the operator directly: it is the same rule the
            # rest of this module keeps, and it tells an unorderable pair from a `__lt__` of the user's
            # own that raises. Compared here with `<`, the raise happened inside *this* frame, where the
            # origin check reads it as somebody else's code and lets a plain type mismatch escape
            # each element's key is computed once and carried to the next round: recomputing it for
            # the left-hand side doubled the calls, which a key with a cost or a side effect would feel
            broken = holds(current_key, previous_key, "gt" if reverse else "lt")
            if broken:
                return index - 1, previous, current
        previous = current
        previous_key = current_key
    return None
