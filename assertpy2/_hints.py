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
import math
from typing import TYPE_CHECKING, Final

from ._engine._introspection import is_attrs_instance, is_mapping_like, is_model_dump_object

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from .errors import DiffResult

    # a step's wording: fixed, or decided from the shape of the pairs it is describing
    _Label = str | Callable[[Sequence[tuple[object, object]]], str]

_NAN_FACT = "a NaN takes part in this comparison, and a NaN is equal to nothing, not even itself"

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
    return value.replace("\r\n", "\n") if isinstance(value, str) else value


def _stripped(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


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


# Ordered, and the order decides which of two sufficient explanations gets named: stripping a string
# also hides a difference in its line endings, so the narrower claim has to be tried first.
#
# A label describes the *normalisation*, not a guess at the cause, because one normalisation can
# resolve more than one cause.  Replacing enum members by their values equalises both a member against
# its value and two different enum types that happen to share one, and only the first of those is what
# "one side holds members" would claim.  Where the shapes differ enough to matter, the label is a
# function of them instead of a fixed string.
_STEPS: list[tuple[Callable[[object], object], _Label]] = [
    (_parsed_json, _json_label),
    (_decoded, "bytes against decoded text"),
    (_enum_value, "enum members against their values"),
    (_newlines, "line endings"),
    (_stripped, "surrounding whitespace"),
]


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and math.isnan(value)


def _explains(pairs: Sequence[tuple[object, object]], steps: Sequence[Callable[[object], object]]) -> bool:
    """Whether applying ``steps`` to both sides of every pair leaves nothing differing.

    Comparison failures count as "not explained" rather than propagating.  This runs while a failure
    is already being raised, on values the caller wrote, and a numpy array or any object with an
    opinionated ``__eq__`` can raise from ``!=``.  Letting that out would replace the assertion error
    the reader needs with a crash from the line that was only trying to be helpful.
    """
    try:
        for left, right in pairs:
            for step in steps:
                left, right = step(left), step(right)
            if left != right:
                return False
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return False
    return True


def diagnose(diff: DiffResult | None, actual: object = None, expected: object = None) -> str | None:
    """The one line to add to a failure message, or ``None`` when nothing can be said.

    Args:
        diff: the structured diff already built for this failure.
        actual: the value asserted on, needed only for the string case below.
        expected: the value it was compared against.

    Returns:
        A lowercase clause to put on its own line under the message, or ``None``.
    """
    if diff is None or not diff.entries or diff.kind not in _VALUE_KINDS:
        return None
    entries = diff.entries

    # first, and regardless of what else differs: with a NaN in the comparison there is no value the
    # other side could hold that would make it pass, so it is the thing to fix before anything else
    if any(_is_nan(entry.actual) or _is_nan(entry.expected) for entry in entries):
        return _NAN_FACT

    if diff.kind == "string":
        # a string diff is built line by line, and `splitlines()` treats "\r\n" and "\n" as the same
        # break: a file that differs in its line endings *and* in one line produces an entry for the
        # line only. Reading that entry would have this claim that trailing whitespace is the whole
        # story, the reader would strip it, and the assertion would fail again on the endings. The
        # two strings themselves are the complete account, and comparing them costs nothing
        if not isinstance(actual, str) or not isinstance(expected, str):
            return None
        pairs = [(actual, expected)]
        return _named(pairs)

    # keys on the left that the right does not have at all, and nothing else. restricted to plain
    # mappings because that is where "key" is the right word: a sequence reports its extras the same
    # way, and telling someone their list carries extra keys helps nobody
    if diff.kind == "dict" and all(entry.absent == "expected" for entry in entries):
        return "every shared key matches, and actual carries keys the expected side does not"

    # a mixture of absent sides and differing values has no single statement that covers it
    if any(entry.absent is not None for entry in entries):
        return None
    pairs = [(entry.actual, entry.expected) for entry in entries]

    # a DTO against the payload it was built from: the fields all agree and only the wrapper differs.
    # said before the leaf steps because it explains the shape, which is the narrower claim
    if all(type(left) is not type(right) and _fields_match(left, right) for left, right in pairs):
        return "the contents match field for field, and only the type of the two sides differs"

    named = _named(pairs)
    if named is not None:
        return named

    # last, because it is the broadest thing that can be said and the easiest to reach by accident.
    # one differing value can never be a rearrangement, which also keeps the sort off the common case
    if len(pairs) >= 2 and _all_positional(entries) and _same_values(pairs):
        return "both sides hold the same elements, in a different order"
    return None


def _all_positional(entries: Sequence) -> bool:
    """Whether every difference is at a position in a sequence rather than at a named field.

    Order is a property of sequences, so a rearrangement is a real and actionable thing to report
    there.  Across the fields of a mapping it is mostly a coincidence: with two boolean fields, any
    failure where both flip holds "the same values in different places", and measured over generated
    boolean payloads that was one failure in five.  Every one of those statements was true, and not
    one of them told the reader anything, which is the surest way to teach people to skip the line.
    """
    return all(entry.path.endswith("]") for entry in entries)


def _fields_of(value: object) -> dict | None:
    """A dataclass, attrs instance or pydantic-style model as its field mapping, else ``None``."""
    if is_model_dump_object(value):
        return value.model_dump()
    if is_attrs_instance(value):
        return {field.name: getattr(value, field.name) for field in value.__attrs_attrs__}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: getattr(value, field.name) for field in dataclasses.fields(value)}
    return None


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
    """Whether the differing values are the same on both sides, sitting in different places."""
    try:
        left = sorted((value for value, _ in pairs), key=repr)
        right = sorted((value for _, value in pairs), key=repr)
        return left == right
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return False


def _named(pairs: Sequence[tuple[object, object]]) -> str | None:
    """The narrowest set of steps that accounts for every pair, worded, or ``None``."""

    for step, label in _STEPS:
        if _explains(pairs, (step,)):
            return f"every difference here is one of {_worded(label, pairs)}"
    # only now pairs of steps: `"a\r\n "` against `"a\n"` needs both, and neither alone equalises it
    for index, (first_step, first_label) in enumerate(_STEPS):
        for second_step, second_label in _STEPS[index + 1 :]:
            if _explains(pairs, (first_step, second_step)):
                first, second = _worded(first_label, pairs), _worded(second_label, pairs)
                return f"every difference here is one of {first} and {second}"
    return None


def _worded(label: _Label, pairs: Sequence[tuple[object, object]]) -> str:
    """A step's label, letting one that depends on the shape of the pairs decide for itself."""
    return label if isinstance(label, str) else label(pairs)
