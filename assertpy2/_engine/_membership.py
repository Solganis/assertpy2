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


def missing_items(value: Any, items: Sequence[Any], is_matcher: Callable[[object], bool]) -> list[Any]:
    """Which of *items* are not in *value*, in the order they were asked for.

    A matcher among the items is satisfied by any single element, which is what makes this more than
    `item in value`: `contains(match.greater_than(3))` asks whether *some* element is greater than 3,
    not whether the collection holds that matcher object.

    The matcher test is passed in rather than imported: matchers are a layer above this one, and having
    the core reach up for them would make the dependency circular.
    """
    absent = []
    for item in items:
        if is_matcher(item):
            if not any(item.matches(element) for element in value):
                absent.append(item)
        elif item not in value:
            absent.append(item)
    return absent


def only_faults(value: Any, items: Sequence[Any]) -> tuple[list[Any], list[Any]]:
    """``(extra, missing)`` for "contains only these": what is there but unwanted, and what is absent.

    Both halves at once, because reporting only the extras sends the reader to fix one problem and rerun
    into the other.  A matcher looks at whether either list is non-empty; the assertion words them.
    """
    extra = [item for item in value if item not in items]
    missing = [item for item in items if item not in value]
    return extra, missing


def not_contained_in(value: Any, container: Any) -> list[Any]:
    """Which elements of *value* the *container* does not hold, for "is a subset of"."""
    return [item for item in value if item not in container]
