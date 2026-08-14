"""Membership as one decision: which of the wanted items a value does not contain.

`contains` is the second relation that a builder could express and a matcher could not.  A structural
spec had `each_item` (every element matches) and `is_in` (the value is one of these), but no way to say
the plain thing: *this collection contains that*.  Writing it a second time inside the matcher would
have repeated the part that is easy to get subtly wrong, since membership is not one rule: a mapping is
searched by key, a matcher argument is satisfied by any element rather than compared to the whole, and a
one-shot iterator has to be drained before it is searched more than once.

So the decision moves here and both spellings ask it.  What stays outside is the wording: the builder
turns the answer into a message with a closest-element hint, and a matcher turns it into a verdict.
"""

from __future__ import annotations

import datetime
import decimal
from collections import Counter
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, cast

from ._introspection import materialized

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def searchable(value: object) -> Any:
    """*value* in a form that can be searched more than once.

    A generator is consumed by the first pass, and membership is tested once per wanted item.  A value
    that cannot be iterated at all is handed back untouched, which is why the parameter is `object`:
    deciding whether membership can be asked of it is `is_searchable`'s job, not this one's.

    Only a one-shot iterator is copied.  A list, set, tuple or mapping is handed back as it is, so a
    matcher built from one stays a live view of it, the way `match.equal_to(expected)` does:

        known = [1]
        constraint = match.is_subset_of(known)
        known.append(2)
        constraint.matches([2])          # True: the same list, not a snapshot of it

    The copy for an iterator is therefore not a snapshot policy but the only way to answer twice at all,
    and it is eager: an endless iterator handed in as the expected operand never finishes being drained.
    """
    return materialized(cast("Iterable[Any]", value))


def is_searchable(value: object) -> bool:
    """Whether membership can be asked of *value*: `in` needs a container or an iterable.

    Wider than `is_walkable` on purpose, and the two are not interchangeable.  A value that answers
    `__contains__` and nothing else can be asked whether it holds something, and cannot be listed: it
    fits `contains` and does not fit `contains_only`, which has to see everything that is there.
    """
    return isinstance(value, Iterable) or hasattr(type(value), "__contains__")


def is_walkable(value: object) -> bool:
    """Whether *value* can be listed, which is what "only these" and "a subset of" both need."""
    return isinstance(value, Iterable)


# the built-in types whose `__hash__` and `__eq__` are defined together and agree, so asking a set is
# the same question as walking a list.  `bool` is here with `int` on purpose: `1 in {True}` and
# `1 in [True]` both answer True, which is the equality Python itself uses.  `bytearray` is not here
# although it looks like it belongs: it is mutable and therefore unhashable, and listing it turned
# `assert_that([bytearray(b"a")]).contains_only(...)` into a TypeError
_HASH_SAFE = frozenset(
    {
        int,
        float,
        complex,
        bool,
        str,
        bytes,
        frozenset,
        type(None),
        # the numeric tower and the calendar types: Python guarantees that equal values hash equally
        # across them, which is the whole rule here.  `Decimal` earns its place by measurement - a
        # collection of two thousand of them cost 53 ms on the walk and a tenth of a millisecond here -
        # and both modules are already imported by the comparison core, so this costs no import time.
        # `Fraction` is deliberately absent despite the same guarantee: `fractions` pulls in thirteen
        # more modules, and import cost is a promise this package keeps
        decimal.Decimal,
        datetime.date,
        datetime.datetime,
        datetime.time,
        datetime.timedelta,
    }
)


# below this many comparisons the walk is cheaper than deciding whether to avoid it.  A set costs a pass
# to build and a pass to classify, and on the collections most assertions actually see - a handful of
# elements - that preparation is the whole cost.  Measured: at ten elements the shortcut made the
# assertion twice as slow, at a hundred it paid for itself several times over
_WALK_UNDER = 400


def _worth_hashing(container: Any, probes: Any) -> bool:
    """Whether the pair is large enough that a set can win at all, asked before anything expensive.

    The comparison count is what decides, so the two questions differ: searching one collection for the
    elements of another costs `len * len`, while looking for a repeat inside one collection costs about
    `len` squared over two but pays for only one set.  Passing the same collection twice is how the
    second question spells itself.
    """
    try:
        return len(container) * max(len(probes), 1) >= _WALK_UNDER
    except TypeError:  # no length: an iterator or a view, where the walk cost is unknown but not small
        return True


def _hash_safe(items: Any) -> bool:
    """Whether every element hashes and compares by the same rule, so a set may stand in for a walk.

    Hashability is asked first, and asked of the type rather than tried on the value: an unhashable type
    carries `__hash__ = None`, which is exactly what building the set would trip over.  It is not implied
    by the rest of the rule - a class can inherit identity equality and still set `__hash__ = None` - so
    without this the shortcut raised `TypeError` where it used to answer.

    The types are collected first and judged afterwards, because a Python loop over ten thousand elements
    costs more than the set it is deciding about: `map(type, ...)` runs in the interpreter's own loop, and
    what is left to judge is one entry per distinct type, which is almost always one.
    """
    return all(
        kind.__hash__ is not None and (kind in _HASH_SAFE or kind.__eq__ is object.__eq__)
        for kind in set(map(type, items))
    )


def missing_items(value: Any, items: Sequence[Any], is_matcher: Callable[[object], bool]) -> list[Any]:
    """Which of *items* are not in *value*, in the order they were asked for.

    A matcher among the items is satisfied by any single element, which is what makes this more than
    `item in value`: `contains(match.greater_than(3))` asks whether *some* element is greater than 3,
    not whether the collection holds that matcher object.

    The matcher test is passed in rather than imported: matchers are a layer above this one, and having
    the core reach up for them would make the dependency circular.
    """
    absent = []
    present = indexed(value) if isinstance(value, (list, tuple)) and _classified(value, items) else value
    for item in items:
        if is_matcher(item):
            if not any(item.matches(element) for element in value):
                absent.append(item)
        elif item not in present:
            absent.append(item)
    return absent


def only_faults(value: Any, items: Sequence[Any]) -> tuple[list[Any], list[Any]]:
    """``(extra, missing)`` for "contains only these": what is there but unwanted, and what is absent.

    Both halves at once, because reporting only the extras sends the reader to fix one problem and rerun
    into the other.  A matcher looks at whether either list is non-empty; the assertion words them.
    """
    # both sides classified once rather than once per lookup: this is the hot spot of the whole module,
    # and asking four times cost more on small collections than the walk it was avoiding
    if not _classified(value, items):
        return [item for item in value if item not in items], [item for item in items if item not in value]
    wanted, present = indexed(items), indexed(value)
    extra = [item for item in value if item not in wanted]
    missing = [item for item in items if item not in present]
    return extra, missing


def has_duplicates(values: Sequence[Any]) -> bool:
    """Whether any element appears twice, by the same equality the rest of membership uses."""
    if _classified_alone(values):
        unique = indexed(values)
        if isinstance(unique, set):
            return len(unique) != len(values)
    # `in` rather than a generator of `==`: it is the same question asked by the interpreter instead of
    # by a Python loop, and it short-circuits on identity, which is how the rest of membership answers
    # for a value that is not equal to itself
    seen: list[Any] = []
    for value in values:
        if value in seen:
            return True
        seen.append(value)
    return False


def repeated_items(values: Sequence[Any]) -> list[Any]:
    """Which elements appear more than once, each named once, in order of first appearance.

    Counting with `list.count()` per element re-walks the whole sequence every time, so naming the
    duplicates in a collection of a few thousand costs as much as the assertion it explains.  Where the
    elements are safe to hash (same rule as membership uses), one pass counts them all.
    """
    counts = None
    if _classified_alone(values):
        try:
            counts = Counter(values)
        except TypeError:  # a value that refuses to hash despite its type, such as a signalling NaN
            counts = None
    if counts is None:
        named: list[Any] = []
        for value in values:
            if values.count(value) > 1 and not any(value == earlier for earlier in named):
                named.append(value)
        return named
    seen: set[Any] = set()
    repeated = []
    for value in values:
        if counts[value] > 1 and value not in seen:
            seen.add(value)
            repeated.append(value)
    return repeated


def not_contained_in(value: Any, container: Any) -> list[Any]:
    """Which elements of *value* the *container* does not hold, for "is a subset of"."""
    fast = isinstance(container, (list, tuple)) and _classified(container, value)
    allowed = indexed(container) if fast else container
    return [item for item in value if item not in allowed]


def _classified(container: Any, probes: Any) -> bool:
    """Whether a set may stand in for the walk here: worth the preparation, and safe to build."""
    return _worth_hashing(container, probes) and _hash_safe(container) and _hash_safe(probes)


def indexed(items: Any) -> Any:
    """*items* as a set, or unchanged when one of them refuses to be hashed after all.

    The type rule answers for the type, and one value in the standard library disagrees with its own
    type: `Decimal("snan")` raises when hashed, because a signalling NaN is meant to be noticed rather
    than compared quietly.  That is a property of the value, so it cannot be seen before trying, and the
    walk answers it perfectly well.
    """
    try:
        return set(items)
    except TypeError:
        return items


def _classified_alone(values: Any) -> bool:
    """The same decision for a question asked of one collection, where only one set gets built.

    Kept apart from `_classified` because the arithmetic differs, and differs in the other direction than
    it first looks: what a set replaces here is a growing list of seen elements, which is quadratic from
    the very first elements.  A size threshold made this *slower* at thirty elements, so there is none:
    the only question is whether the elements may be hashed at all.
    """
    return _hash_safe(values)
