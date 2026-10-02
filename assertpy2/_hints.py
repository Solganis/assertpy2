"""One line naming *why* two values differ, when the whole difference has a single explanation.

The diff says what differs, which is where every assertion library stops.  It leaves the reader to
work out why, and there are failures where that is genuinely hard: two strings that render
identically and differ in a trailing space, a comparison that can never pass because a NaN is in it.

A hint is stated only when it accounts for **every** entry in the diff.  A partial explanation is
worse than none, because the reader acts on it and lands back at the same failure.  That rule is what
keeps this from becoming the kind of advice people learn to scroll past, and it is measurable: over a
corpus of 20000 ordinary failures (a wrong leaf somewhere in a generated structure) the checks below
stay silent on all of them, and over a set of near misses built to resemble each form without being
it, likewise.

Everything here reads the diff rather than the values.  That is not only cheaper, though it is: the
diff of a failure over 500 records holds one entry, so the cost does not grow with the data.  It also
means a difference nested six levels down is examined exactly like a top-level one, with no separate
code path.
"""

from __future__ import annotations

import dataclasses
import enum
import json
from collections import Counter
from typing import TYPE_CHECKING, Final

from ._engine._equality import comparable_fields
from ._engine._introspection import definition_of, is_attrs_instance, is_mapping_like, is_model_dump_object, kind_of
from ._engine._ordering import equals, nan_operand
from .errors import _class_names, _safe_repr, _safe_str

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from .errors import DiffEntry, DiffResult, Step

    # a step's wording: fixed, or decided from the shape of the pairs it is describing
    _Label = str | Callable[[Sequence[tuple[object, object]]], str]

_NAN_FACT = "a NaN takes part in this comparison, and a NaN is equal to nothing, not even itself"
_IDENTITY_FACT = (
    "these values compare with object's __eq__, so equality is identity and no two separate instances are equal"
)

_UNSEEN_FACT = "a difference here prints the same on both sides, so what holds the two apart is not in their repr"
_UNSEEN_IDENTITY_FACT = (
    "a difference here prints the same on both sides, and the class of the two leaves __eq__ to object,"
    " so two separate instances are never equal"
)
_ORDER_FACT = "both sides hold the same elements, in a different order"
_UNSEEN_ORDER_FACT = f"{_ORDER_FACT}, and their repr does not show which is which"
# exact types whose repr differs wherever their values do, so ``==`` answers for the repr at a fraction of its cost
_PRINTED_AS_HELD: Final = frozenset({int, str, bytes, bool})

_VALUE_KINDS: Final = frozenset(
    {"dict", "sequence", "dataclass", "namedtuple", "model", "attrs", "set", "string", "scalar"}
)
"""Diff kinds whose entries hold two values compared for equality.

Everything here reasons about a pair as two values, so it only applies where both sides are one.  A
``match`` entry holds the actual value against a *description* of a predicate ("a value equal to
<guest>"), and an ``openapi`` one against a schema violation.  Treating a description as a value is
not a false positive waiting to happen so much as a category error, and one that would surface as an
authoritative-sounding line about whitespace in a predicate.
"""


def _newlines(value: object) -> object:
    if isinstance(value, bytes):
        return value.replace(b"\r\n", b"\n")
    return value.replace("\r\n", "\n") if isinstance(value, str) else value


def _stripped(value: object) -> object:
    return value.strip() if isinstance(value, (str, bytes)) else value


def _parsed_json(value: object) -> object:
    """A string that is a JSON document, parsed.  Anything else passes through."""
    if isinstance(value, str) and value[:1] in "{[":
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _decoded(value: object) -> object:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value
    return value


def _enum_value(value: object) -> object:
    return value.value if isinstance(value, enum.Enum) else value


def _json_label(pairs: Sequence[tuple[object, object]]) -> str:
    """What parsing actually resolved, which is not the same thing on both shapes.

    One side a string and the other a container is the familiar forgotten ``.json()``.  Two strings
    that parse to the same document differ in their formatting instead, and calling either of them
    unparsed would be plainly wrong about both.
    """
    if all(isinstance(left, str) and isinstance(right, str) for left, right in pairs):
        return "the same JSON written differently"
    return "unparsed JSON text"


# ordered, narrower first: a step explains a pair only if the pair differed before it ran
_STEPS: list[tuple[Callable[[object], object], _Label]] = [
    (_parsed_json, _json_label),
    (_decoded, "bytes against decoded text"),
    (_enum_value, "enum members against their values"),
    (_newlines, "line endings"),
    (_stripped, "surrounding whitespace"),
]


def _explains(pairs: Sequence[tuple[object, object]], steps: Sequence[Callable[[object], object]]) -> bool:
    """Whether applying ``steps`` to both sides of every pair leaves nothing differing.

    A pair that already matches counts against every step rather than for it.  Under
    ``strict_types=True`` the two sides of an entry can compare equal and still be a difference,
    because what differs is their type - and then any normalisation "explains" them by doing nothing,
    so the first step in the ladder took the credit and the reader was told that a comparison holding
    no JSON at all was one of unparsed JSON text.

    Comparison failures count as "not explained" rather than propagating.  This runs while a failure
    is already being raised, on values the caller wrote, and a numpy array or any object with an
    opinionated ``__eq__`` can raise from ``==``.  Letting that out would replace the assertion error
    the reader needs with a crash from the line that was only trying to be helpful.
    """
    try:
        for left, right in pairs:
            if equals(left, right):
                return False
            for step in steps:
                left, right = step(left), step(right)
            explained = equals(left, right)
            if not explained:
                return False
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return False
    return True


def _typed(pairs: Sequence[tuple[object, object]], kind: str) -> str | None:
    """Whether every pair differs in its type, and what kind of type difference it is.

    The leaf twin of the DTO-against-payload claim above, and the case a REST payload produces more
    than any other: the ids came back as ``"7"`` where the test expects ``7``.  Two facts live here
    rather than one, because they are not the same news.  Values that compare equal differ only in
    their type, which is a difference at all only under ``strict_types``.  Values that do not compare
    equal but read alike are the same text on one side and a parsed value on the other.

    Silent where the headline already said it.  A scalar failure whose two sides render alike is
    tagged by `_disambiguated` as ``<1:str>`` / ``<1:int>``, which names the two types outright, and
    a line under it restating that in general terms is worse than nothing.
    """
    try:
        if not all(kind_of(left) is not kind_of(right) for left, right in pairs):
            return None
        if kind == "scalar" and all(str(left) == str(right) for left, right in pairs):
            return None
        if all(equals(left, right) for left, right in pairs):
            return "the values on both sides are equal, and only their types differ"
        if all(str(left) == str(right) for left, right in pairs):
            return "every difference here is the same text against a value of another type"
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return None
    return None


def diagnose(
    diff: DiffResult | None,
    actual: object = None,
    expected: object = None,
    *,
    identity: bool = False,
    comparators: bool = False,
) -> str | None:
    """The one line to add to a failure message, or ``None`` when nothing can be said.

    Args:
        diff: the structured diff already built for this failure.
        actual: the value asserted on, needed only for the string case below.
        expected: the value it was compared against.
        identity: whether the comparison was an unconfigured equality one that `identity_candidate`
            found identity-bound *before* it ran.  Only then does identity account for the failure.
        comparators: whether the comparison was given ``comparators=``.  Identity is then not said of a pair
            inside the diff, whose verdict may be the predicate's.

    Returns:
        A lowercase clause to put on its own line under the message, or ``None``.
    """
    if diff is None or diff.kind not in _VALUE_KINDS:
        return None
    # asked of the two values compared, never of a pair inside the diff: identity equality can never pass
    if identity:
        return _IDENTITY_FACT
    if not diff.entries:
        return None
    entries = diff.entries

    # one flat pass: this is the only part whose cost grows with the entry count
    pairs: list[tuple[object, object]] = []
    # by the container each pair sits in: values swapped between two lists are not one list rearranged
    per_container: dict[tuple[object, ...], list[tuple[object, object]]] = {}
    absent_seen = False
    absent_expected_only = True
    positional = True
    for entry in entries:
        left, right = entry.actual, entry.expected
        if nan_operand(left) or nan_operand(right):
            # with a NaN in the comparison no other value would make it pass, so it comes before anything else
            return _beside_a_nan(entries, comparators=comparators)
        absent = entry.absent
        if absent is None:
            pairs.append((left, right))
            per_container.setdefault(entry.steps[:-1], []).append((left, right))
            absent_expected_only = False
        else:
            absent_seen = True
            if absent != "expected":
                absent_expected_only = False
        # a step and not the rendered text: a mapping key ending in a bracket used to read as an index
        if positional and not (entry.steps and entry.steps[-1].kind == "index"):
            positional = False

    if diff.kind == "string":
        # the whole strings: `splitlines()` folds "  " into " ", so a text differing in both yields one entry
        if not isinstance(actual, (str, bytes)) or not isinstance(expected, (str, bytes)):
            return None
        return _named([(actual, expected)])

    # restricted to plain mappings, since telling someone their list carries extra keys helps nobody
    if diff.kind == "dict" and absent_seen and absent_expected_only:
        return "every shared key matches, and actual carries keys the expected side does not"

    # a mixture of absent sides and differing values has no single statement that covers it
    if absent_seen:
        return _unseen(pairs, comparators=comparators)

    # a DTO against the payload it was built from, said before the leaf steps because the shape is the narrower claim
    if all(type(left) is not type(right) and _fields_match(left, right) for left, right in pairs):
        return "the contents match field for field, and only the type of the two sides differs"

    named = _named(pairs)
    if named is not None:
        return named

    # after the ladder: a step that resolves the pairs has named the encoding they differ in, which is narrower
    typed = _typed(pairs, diff.kind)
    if typed is not None:
        return typed

    # last, as the broadest thing that can be said; one differing value can never be a rearrangement
    if (
        len(pairs) >= 2
        and positional
        and all(len(group) >= 2 and _same_values(group) for group in per_container.values())
    ):
        # the elements moved, and where two of them print the same no row shows which went where
        return _UNSEEN_ORDER_FACT if any(_prints_alike(left, right) for left, right in pairs) else _ORDER_FACT
    return _unseen(pairs, comparators=comparators)


def placed(diff: DiffResult | None) -> str | None:
    """Where the differences of a diff sit, when they repeat at one to three places down a sequence, or ``None``.

    Forty rows that differ in one field are forty rows of diff to read before that can be said, and past the
    fiftieth the rows are not printed at all: a single difference of another field among them went unseen.
    A place is the path with every position replaced by ``[*]``.  It is a fact about where, said beside
    whatever is said about why, and it recommends nothing.
    """
    if diff is None or diff.kind not in _VALUE_KINDS or len(diff.entries) < 3:
        return None
    counted: dict[tuple[tuple[str, str], ...], int] = {}
    for entry in diff.entries:
        place = _place(entry.steps)
        if place is None:
            return None
        counted[place] = counted.get(place, 0) + 1
        if len(counted) > 3:
            return None
    total = len(diff.entries)
    spelled = {place: _spelled(place) for place in counted}
    # nothing repeats, two places read the same (a key and a field of one name), or one is too long to be a line
    if (
        len(counted) == total
        or len(set(spelled.values())) != len(spelled)
        or any(len(text) > 200 for text in spelled.values())
    ):
        return None
    if len(counted) == 1:
        return f"all {total} differences here are at <{next(iter(spelled.values()))}>"
    # by how many, and among equals by which came first, which is the order a dict keeps and a stable sort leaves
    ranked = [f"<{spelled[place]}> ({count})" for place, count in sorted(counted.items(), key=lambda item: -item[1])]
    return f"the {total} differences here are at {', '.join(ranked[:-1])} and {ranked[-1]}"


def _place(steps: Sequence[Step]) -> tuple[tuple[str, str], ...] | None:
    """*steps* with every position made one, or ``None`` where they name no field.

    The kind of each hop is kept, so a key and a field of one name are two places.  Only a name that is
    exactly a `str` counts: ``1`` and ``"1"`` are two keys and read as one.  A place with no position in it
    is met once and so never repeats, which is why none is asked for.
    """
    place: list[tuple[str, str]] = []
    named = False
    for step in steps:
        kind = step.kind
        if kind == "index":
            place.append(("index", "*"))
        elif kind in ("key", "attr") and type(step.value) is str:
            place.append((kind, step.value))
            named = True
        elif kind != "json":
            return None
    return tuple(place) if named else None


def _spelled(place: tuple[tuple[str, str], ...]) -> str:
    """A place as a path.  A name that is no identifier is quoted: ``[*]['a.b']`` is one key, ``[*].a.b`` two."""
    parts: list[str] = []
    for kind, name in place:
        if kind == "index":
            parts.append("[*]")
        elif not name.isidentifier():
            parts.append(f"[{name!r}]")
        else:
            parts.append(f".{name}" if parts else name)
    return "".join(parts)


def _beside_a_nan(entries: Sequence[DiffEntry], *, comparators: bool) -> str:
    """The NaN fact, and under it what is said of a pair no NaN takes part in that prints the same on both sides."""
    others = [
        (entry.actual, entry.expected)
        for entry in entries
        if entry.absent is None and not (nan_operand(entry.actual) or nan_operand(entry.expected))
    ]
    unseen = _unseen(others, comparators=comparators)
    return _NAN_FACT if unseen is None else f"{_NAN_FACT}\n{unseen}"


def _prints_alike(left: object, right: object) -> bool:
    """Whether a row of these two reads the same on both sides: one class, or two nothing tells apart, one repr."""
    kind = type(left)
    if kind is type(right) and kind in _PRINTED_AS_HELD:
        return left == right
    return _class_names(left, right) is None and _safe_repr(left) == _safe_repr(right)


def _unseen(pairs: Sequence[tuple[object, object]], *, comparators: bool) -> str | None:
    """What to say of pairs that print the same on both sides and are one class, or ``None`` where none does.

    Such a row names no difference a reader can see, and nothing above accounted for it.  Where no comparator
    took part and every one of them is two instances of a class that leaves ``==`` to `object`, that is the
    reason.  Otherwise the reason is in the comparison itself, a comparator or an ``__eq__`` of the value's
    own, and the line says what is known: the repr does not show it, and which attributes of the two differ
    where they hold any.  Asked of every pair: how many rows a diff prints is the renderer's to decide.

    The identity line here is not the top pair's.  That one speaks of the two values compared, and is asked
    before they are.  A pair inside has no before short of walking both values on every passing comparison
    (23 times the cost of one over 200 rows), so its line speaks of the row and of the class as it stands now.
    """
    alike = [(left, right) for left, right in pairs if _prints_alike(left, right)]
    if not alike:
        return None
    if not comparators and all(identity_candidate(left, right) for left, right in alike):
        return _UNSEEN_IDENTITY_FACT
    names: dict[str, None] = {}
    for left, right in alike:
        _attributes_apart(left, right, names)
        if len(names) > 5:
            break
    if not names:
        return _UNSEEN_FACT
    shown = list(names)
    return f"{_UNSEEN_FACT} (attributes that differ: {', '.join(shown[:5])}{', ..' if len(shown) > 5 else ''})"


def _attributes_apart(left: object, right: object, known: dict[str, None]) -> None:
    """Add to *known* the attributes two values hold that differ between them, up to the six a line can use.

    An attribute whose comparison raises is left out: nothing is known of it.
    """
    try:
        held, other = vars(left), vars(right)
        for name in (*held, *(name for name in other if name not in held)):
            if name not in held or name not in other or _held_apart(held[name], other[name]):
                known[_safe_str(name)] = None
                if len(known) > 5:
                    return
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return


def _held_apart(one: object, other: object) -> bool:
    try:
        return not equals(one, other)
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return False


def _fields_of(value: object) -> dict | None:
    """A dataclass, attrs instance or pydantic-style model as its fields, read as its ``==`` reads them.

    Read field by field, a field ``==`` leaves out kept the hint away from a payload that matched, and so
    did a nested object against the nested mapping it was built from.
    """
    if (
        is_model_dump_object(value)
        or is_attrs_instance(value)
        or (dataclasses.is_dataclass(value) and not isinstance(value, type))
    ):
        return comparable_fields(value)
    return None


def _defined_as(klass: type, name: str) -> bool:
    """Whether the definition of *name* the class tree carries is the one ``object`` carries."""
    found = definition_of(klass, name)
    # pragma: no cover on the `None` half - `object` ends every tree and defines the name asked here
    return found is not None and found[1] is object.__dict__[name]


def identity_candidate(left: object, right: object) -> bool:
    """Whether ``==`` between these two comes down to identity, asked *before* the comparison runs.

    A type that leaves ``__eq__`` to ``object`` is equal only to itself, so no value on the other side
    would have made the comparison pass.  That is a fact about the type rather than about what the two
    hold, which is the only claim worth making: state can live in a slot, in a descriptor's own table or
    in a C field, and a line that promised to have read all of it would be promising more than any
    reading can deliver.

    Three details make the answer trustworthy, and each was put here by a case that defeated the one
    before it.  It is asked before the comparison, because a type may rewrite its own ``__eq__`` while
    answering one, and a question asked afterwards would be answered by the type it left behind.  It
    never reads an attribute the ordinary way, because a metaclass is free to answer with something
    other than what the operator will run, or to install one as a side effect of being asked.  And what
    it finally reads is the class tree's own definitions, the way `slot_tp_richcompare` reads them,
    because a class-level descriptor can answer one way for the class and another for an instance.

    The cheap look comes first so the ordinary case, a type that does define equality, stops at 97 ns
    and never pays for the walk.  The walk itself is another 465 ns, spent only on a pair of separate
    instances of a type that compares by identity, which is a comparison that is about to fail anyway.
    Scalars reach none of it: their comparison returns before this is asked.

    ``__ne__`` is not asked about: the comparison a failing assertion runs is ``actual == expected``, so a
    type defining only ``__ne__`` still compares by identity.
    """
    try:
        klass = type(left)
        # one object against itself is equal under identity too, so a failure can never be about that
        if left is right or klass is not type(right):
            return False
        # a cheap look first, so a type that does define equality pays only for this
        if type.__getattribute__(klass, "__eq__") is not object.__eq__:
            return False
        return _defined_as(klass, "__eq__")
    except Exception:  # pragma: no cover - no input is known to reach it, see below
        # every lookup above runs none of the type's own code, and the guard stays because a failure is on the way
        return False


def _fields_match(left: object, right: object) -> bool:
    """Whether one side is an object whose fields are exactly the other side's mapping."""
    try:
        for obj, other in ((left, right), (right, left)):
            fields = _fields_of(obj)
            if fields is not None and is_mapping_like(other) and fields == dict(other):
                return True
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return False
    return False


def _same_values(pairs: Sequence[tuple[object, object]]) -> bool:
    """Whether the differing values are the same on both sides, sitting in different places.

    Counted rather than sorted wherever the values are hashable, which is the common case and the one
    that used to be expensive: sorting by ``repr`` calls ``repr`` on every value on both sides, and a
    failure over a two-thousand element sequence paid four thousand of them for an answer that is
    almost always no.  The sort stays as the fallback, since it is what handles values that are
    unhashable or not orderable against each other.
    """
    try:
        return Counter(value for value, _ in pairs) == Counter(value for _, value in pairs)
    except TypeError:  # unhashable values, which only the slower route can compare
        pass
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return False
    try:
        return sorted((value for value, _ in pairs), key=repr) == sorted((value for _, value in pairs), key=repr)
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return False


def _named(pairs: Sequence[tuple[object, object]]) -> str | None:
    """The narrowest set of steps that accounts for every pair, worded, or ``None``."""

    for step, label in _STEPS:
        if _explains(pairs, (step,)):
            return f"every difference here is one of {_worded(label, pairs)}"
    # only now pairs of steps: `"a   "` against `"a "` needs both, and neither alone equalises it
    for index, (first_step, first_label) in enumerate(_STEPS):
        for second_step, second_label in _STEPS[index + 1 :]:
            if _explains(pairs, (first_step, second_step)):
                first, second = _worded(first_label, pairs), _worded(second_label, pairs)
                return f"every difference here is one of {first} and {second}"
    return None


def _worded(label: _Label, pairs: Sequence[tuple[object, object]]) -> str:
    """A step's label, letting one that depends on the shape of the pairs decide for itself."""
    return label if isinstance(label, str) else label(pairs)
