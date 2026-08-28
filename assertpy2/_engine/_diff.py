"""Recursive diff engine shared by the equality assertions and the dict error path.

Three walkers coexist on purpose and must not be merged: `_build_equality_diff()` dispatches a
top-level pair (top-level dicts are handled by `HelpersMixin._dict_err()` instead, so its ladder
starts at namedtuples), `_sub_diff_entries()` decomposes nested values (mappings first), and
`_walk_leaves()` iterates scalar leaves for the recursive leaf assertions.  Their dispatch orders
differ deliberately; a shared type classifier was investigated and rejected, because a single global
precedence changes behavior for values that quack like several container shapes at once.
`_sequence_diff_entries()` and `_dataclass_diff_entries()` are the pieces genuinely shared by the
diff builders.

The three ladders are not the same width, and the reason is worth stating because it has already cost
two bugs.  They answer different questions.  `_build_equality_diff()` asks *how should a difference
here be shown*, so it carries steps that are renderers rather than decompositions: a set diffs by
membership, a string or bytes goes through ``difflib``.  `_sub_diff_entries()` asks *does this value
break into path-addressed entries*, which a set does not, because its members have no stable position
to name.  They agree on mappings and sequences and disagree at both ends: the top has sets, strings and
bytes that the nested walker refuses, and the nested one has mappings that the top never sees, since a
top-level dict is routed to `HelpersMixin._dict_err()` before it gets here.

So do **not** write a predicate that answers "will this decompose".  Two attempts have been made and
both produced a false failure on values that were equal, because the predicate drifted from one ladder
or answered for the wrong one.  Ask the walker and read its answer instead: ``None`` from
`_sub_diff_entries()`, or the ladder falling through to the scalar case in `_build_equality_diff()`.
`_child_entries()` is where that reading is interpreted.
"""

from __future__ import annotations

import dataclasses
import difflib
from typing import TYPE_CHECKING, TypeVar

from ..errors import DiffEntry, DiffResult, _safe_repr
from ._compare import _guarded_not_equal, _node_decision
from ._introspection import is_attrs_instance, is_mapping_like, is_model_dump_object, is_namedtuple
from ._path import _ROOT, _Path

if TYPE_CHECKING:
    from collections.abc import Hashable, Iterable

_K = TypeVar("_K", bound="Hashable")  # a mapping key or a field name, kept as itself through the walk

__tracebackhide__ = True


def _field_dict(obj, is_model):
    """Field mapping of a pydantic-style model (``model_dump()``) or an attrs instance (shallow)."""
    if is_model:
        return obj.model_dump()
    return {field.name: getattr(obj, field.name) for field in obj.__attrs_attrs__}


def _child_entries(actual, expected, path: _Path, *, descended_for, _seen=None, config=None) -> list[DiffEntry]:
    """Walk a child node and turn the walker's answer into entries, given *why* it was descended into.

    `_sub_diff_entries()` answers ``None`` for a value it does not take apart, and that answer means
    two different things depending on the reason for the descent.  Descending because the two sides
    differ, ``None`` is a differing leaf and must be reported.  Descending because ``strict_types`` has
    to look past a container whose own ``==`` was true, ``None`` is a value that is already equal and
    must not be.  Reading it wrong is where the false failure on two equal sets came from, so the two
    readings live here and nowhere else: every caller names its reason and gets entries back.

    Scope, because this is easy to over-read: it owns ``None`` for *building entries*, not for every
    use of the walker.  Two other readings exist and are both correct for their own job -
    `assertpy2.helpers._values_not_equal()` treats ``None`` as "ask ``==`` instead", and
    `HelpersMixin._dict_err()` treats it as "nothing to render".  A new caller still has to decide what
    ``None`` means for what it is doing; it just must not invent a fourth answer for this one.
    """
    sub_entries = _sub_diff_entries(actual, expected, path, _seen=_seen, config=config)
    if sub_entries is not None:
        return sub_entries
    if descended_for == "strict":
        return []
    return [path.entry(actual=actual, expected=expected)]


_ALIGN_MAX_ELEMENTS = 1000
"""Longest sequence `_alignment_opcodes()` will align.

difflib's search is quadratic, and the alignment buys nothing a reader of a thousand-element failure
was going to use anyway, so past this the diff stays positional: never wrong, only longer.
"""


def _alignment_opcodes(actual, expected):
    """difflib opcodes pairing two sequences, or ``None`` when only positions are available.

    Alignment decides *which elements to pair*, never whether a pair is equal - that stays with
    `_node_decision()`, which is what keeps a comparator, a tolerance and ``strict_types`` in charge of
    the verdict no matter how the pairing was found.

    Elements difflib cannot hash - dicts, lists, arrays, which is the shape of most API payloads - are
    aligned on their reprs instead.  A repr stands in for structural identity here, and standing in
    badly costs only a worse pairing, not a wrong answer.  ``autojunk`` is off because the heuristic
    calls any value filling more than 1% of a 200+ element sequence junk, which is exactly the repeated
    value an alignment has to match on.

    `_rechecked_equal_runs()` is what makes the first paragraph true rather than merely intended, and
    both branches go through it: neither of difflib's two notions of a match is this library's.  The
    repr keying matches values that print alike, and the hashable keying matches on ``==``, while every
    verdict here is reached with ``!=``.

    The length cap lives in the caller, which reaches it before paying for anything here.
    """
    try:
        opcodes = difflib.SequenceMatcher(None, actual, expected, autojunk=False).get_opcodes()
    except (TypeError, ValueError):
        pass
    else:
        return _rechecked_equal_runs(opcodes, actual, expected)
    try:
        keyed_actual = [_safe_repr(item) for item in actual]
        keyed_expected = [_safe_repr(item) for item in expected]
        opcodes = difflib.SequenceMatcher(None, keyed_actual, keyed_expected, autojunk=False).get_opcodes()
    # pragma: no cover - `_safe_repr` swallows everything; what is left degrades to a positional diff
    except (TypeError, ValueError):  # pragma: no cover
        return None
    return _rechecked_equal_runs(opcodes, actual, expected)


def _rechecked_equal_runs(opcodes, actual, expected):
    """Opcodes whose ``equal`` runs survive the comparison this library reaches its verdicts with.

    A run difflib calls equal was matched on whatever it was keyed with, and neither key is the
    verdict.  Keyed on reprs, the run is only known to *print* the same, and a shared repr is not
    exotic: `_safe_repr()` renders every value of a type whose ``__repr__`` raises as the same string.
    Keyed on the values, it is known to satisfy ``==``, which a type is free to define apart from
    ``!=``.  Either way the pair would drop out of the diff and out of the message's elision, and the
    failure would name a smaller difference than the one that caused it.

    Compared through `_guarded_not_equal()`, the same operator `_node_decision()` reaches its verdict
    with, so a run split back into a substitution is exactly a pair the walk will then report.  That
    costs one comparison per matched element, on the failing path only and under the caller's length
    cap.  Measured on 200 records with one inserted at the head: 0.38 ms to 0.48 ms for unhashable rows,
    and 0.15 ms to 0.20 ms for hashable ones, which is the path most sequences take.
    """
    revalidated = []
    for tag, actual_start, actual_stop, expected_start, expected_stop in opcodes:
        if tag != "equal":
            revalidated.append((tag, actual_start, actual_stop, expected_start, expected_stop))
            continue
        holds = [
            not _guarded_not_equal(actual[actual_start + offset], expected[expected_start + offset])
            for offset in range(actual_stop - actual_start)
        ]
        run_start = 0
        for offset in range(1, len(holds) + 1):
            if offset < len(holds) and holds[offset] == holds[run_start]:
                continue
            revalidated.append(
                (
                    "equal" if holds[run_start] else "replace",
                    actual_start + run_start,
                    actual_start + offset,
                    expected_start + run_start,
                    expected_start + offset,
                )
            )
            run_start = offset
    return revalidated


def _aligned_match_indices(seq, counterpart) -> set[int] | None:
    """Indices of ``seq`` that align with an equal element of ``counterpart``, or ``None`` if unaligned.

    Lets the failure message collapse a matched run the way the diff collapses it: without this the
    message elides on position and an element inserted at the head shifts every later element out of
    the elision, so the message dumps both sequences whole while the diff below it shows one entry.
    """
    opcodes = _alignment_opcodes_if_useful(seq, counterpart)
    if opcodes is None:
        return None
    matched: set[int] = set()
    for tag, start, stop, _, _ in opcodes:
        if tag == "equal":
            matched.update(range(start, stop))
    return matched


def _positional_difference_count(actual, expected) -> int:
    """How many positions the two sequences differ at when paired by index.

    Guarded rather than bare ``!=``: an array member reached here has an element-wise ``==`` with no
    single truth value, and the operand gate on the assertion never saw it - the top-level ``!=`` that
    admitted the failure short-circuited on an earlier element.  Without the guard numpy's own
    ``ValueError`` leaves the library in place of the actionable ``TypeError`` it promises.
    """
    return sum(
        1
        for index in range(max(len(actual), len(expected)))
        if index >= len(actual) or index >= len(expected) or _guarded_not_equal(actual[index], expected[index])
    )


def _aligned_difference_count(opcodes) -> int:
    """How many positions the alignment reports, which is what an aligned walk would emit."""
    return sum(
        max(actual_stop - actual_start, expected_stop - expected_start)
        for tag, actual_start, actual_stop, expected_start, expected_stop in opcodes
        if tag != "equal"
    )


def _alignment_opcodes_if_useful(actual, expected):
    """Alignment opcodes, or ``None`` when pairing by index already reads at least as short.

    The order matters for cost, not just for the answer.  A long list of records with one field changed
    is the common failure, and pairing it by index already yields the one entry an alignment could -
    but the elements are unhashable, so asking difflib means rendering every element's repr first.  One
    differing position cannot be beaten, so that case never asks: measured on 200 records, it is the
    difference between 0.09 ms and 0.75 ms.

    Alignment is a large win when a sequence shifted and a loss when it did not: a reversal reads as
    two substitutions positionally and as four insertions and deletions aligned.  Counting both, and
    keeping the index reading on a tie, is what lets one rule serve both - and it answers whether a
    tuple should align without a special case, since a coordinate pair is never shorter aligned.

    Counted on ``==`` alone rather than on the built entries: the walkers recurse, so building both to
    compare them would double the work at every level of nesting.  Measured over 13 600 random pairs,
    this count picks the same winner as the exact one every time.
    """
    if len(actual) == len(expected):
        # equal lengths hide a rotation, worth 8% of the wins over 13 640 pairs against a doubled comparison
        return None
    if max(len(actual), len(expected)) > _ALIGN_MAX_ELEMENTS:
        return None  # over the cap nothing here can be used anyway
    positional = _positional_difference_count(actual, expected)
    if positional <= 1:
        return None  # nothing to win: an alignment would have to report zero positions to beat it
    opcodes = _alignment_opcodes(actual, expected)
    if opcodes is None or _aligned_difference_count(opcodes) >= positional:
        return None
    return opcodes


def _sequence_diff_entries(actual, expected, prefix: _Path, seen, config=None) -> list[DiffEntry]:
    """Diff two sequences, pairing their elements by alignment where that reads shorter.

    An element inserted or removed shifts everything after it, and pairing by index then calls every
    later element different.  Pairing by `difflib` alignment reports the one insertion instead.

    ``seen`` must already include the ids of ``actual``/``expected`` so a self-referential element
    is caught.  Shared by the top-level (`_build_equality_diff()`) and nested
    (`_sub_diff_entries()`) paths so both decompose sequences identically.  Elements have no field
    name, so a ``config`` applies only type comparators and tolerance to them.
    """
    opcodes = _alignment_opcodes_if_useful(actual, expected)
    if opcodes is not None:
        return _aligned_diff_entries(actual, expected, prefix, seen, config, opcodes)
    entries: list[DiffEntry] = []
    max_len = max(len(actual), len(expected))
    for i in range(max_len):
        if i >= len(actual):
            entries.append(prefix.index(i).entry(actual=None, absent="actual", expected=expected[i]))
        elif i >= len(expected):
            entries.append(prefix.index(i).entry(actual=actual[i], expected=None, absent="expected"))
        else:
            # the path is built after the decision: an empty list per equal element cost 15% of the walk
            decision = _node_decision(actual[i], expected[i], config)
            if decision == "leaf":
                entries.append(prefix.index(i).entry(actual=actual[i], expected=expected[i]))
            elif decision != "equal":
                entries.extend(
                    _child_entries(
                        actual[i], expected[i], prefix.index(i), descended_for=decision, _seen=seen, config=config
                    )
                )
    return entries


def _aligned_diff_entries(actual, expected, prefix, seen, config, opcodes) -> list[DiffEntry]:
    """Entries for a pair the alignment reports as shifted.

    A one-sided entry names the sequence its index belongs to (``actual[2]``, ``expected[1]``).  Once
    the two sides have shifted apart their index spaces no longer agree, and numbering both as ``[i]``
    put two unrelated entries on one path - the reader cannot tell which sequence the number indexes,
    and a consumer reading entries by path sees a collision.
    """
    entries: list[DiffEntry] = []
    for tag, actual_start, actual_stop, expected_start, expected_stop in opcodes:
        if tag == "equal" and config is None:
            continue  # `_alignment_opcodes()` guarantees these compare equal, the whole test when no config narrows it
        for offset in range(max(actual_stop - actual_start, expected_stop - expected_start)):
            actual_index, expected_index = actual_start + offset, expected_start + offset
            if actual_index >= actual_stop:
                path = prefix.side_index("expected", expected_index)
                entries.append(path.entry(actual=None, absent="actual", expected=expected[expected_index]))
            elif expected_index >= expected_stop:
                path = prefix.side_index("actual", actual_index)
                entries.append(path.entry(actual=actual[actual_index], expected=None, absent="expected"))
            else:
                entries.extend(
                    _element_entries(
                        actual[actual_index], expected[expected_index], prefix.index(actual_index), seen, config
                    )
                )
    return entries


def _element_entries(actual_item, expected_item, path: _Path, seen, config) -> list[DiffEntry]:
    """Entries for one paired element: none when equal, one leaf, or the nested sub-diff."""
    decision = _node_decision(actual_item, expected_item, config)
    if decision == "equal":
        return []
    if decision == "leaf":
        return [path.entry(actual=actual_item, expected=expected_item)]
    return _child_entries(actual_item, expected_item, path, descended_for=decision, _seen=seen, config=config)


def _ordered_keys(actual: Iterable[_K], expected: Iterable[_K]) -> list[_K]:
    """Every key of both sides, in the order a reader wrote them.

    A union of two sets loses insertion order, which is why this used to be sorted: without an order
    imposed, the report varied with the hash seed.  Sorting bought determinism at the price of the one
    ordering that carries meaning - a JSON response reads in the order its fields arrived, and `k0, k1,
    k10, k100` reads as no order at all.  Walking the actual side and then the keys only the expected
    side has is just as deterministic, and it is the order pytest shows.
    """
    seen = set(actual)
    return [*actual, *(key for key in expected if key not in seen)]


def _dataclass_diff_entries(actual, expected, prefix: _Path, seen, config=None) -> list[DiffEntry]:
    """Diff two dataclasses over both sides' field names in declaration order, recursing.

    Reports fields present on only one side, and recurses into nested containers.  ``seen`` must
    already include the ids of ``actual``/``expected``.  Shared by the top-level and nested paths
    so both report dataclass fields identically.
    """
    entries: list[DiffEntry] = []
    actual_names = [field.name for field in dataclasses.fields(actual)]
    expected_names = [field.name for field in dataclasses.fields(expected)]
    in_actual, in_expected = set(actual_names), set(expected_names)
    for field in _ordered_keys(actual_names, expected_names):
        if field not in in_expected:
            entries.append(prefix.attr(field).entry(actual=getattr(actual, field), expected=None, absent="expected"))
        elif field not in in_actual:
            entries.append(prefix.attr(field).entry(actual=None, absent="actual", expected=getattr(expected, field)))
        else:
            actual_value = getattr(actual, field)
            expected_value = getattr(expected, field)
            decision = _node_decision(actual_value, expected_value, config, field=field)
            if decision == "leaf":
                entries.append(prefix.attr(field).entry(actual=actual_value, expected=expected_value))
            elif decision != "equal":
                entries.extend(
                    _child_entries(
                        actual_value,
                        expected_value,
                        prefix.attr(field),
                        descended_for=decision,
                        _seen=seen,
                        config=config,
                    )
                )
    return entries


def _build_equality_diff(
    actual: object, expected: object, *, _prefix: _Path = _ROOT, _seen: set[int] | None = None, config=None
) -> DiffResult:
    if _seen is None:
        _seen = set()
    pair_key = (id(actual), id(expected))
    if pair_key[0] in _seen or pair_key[1] in _seen:
        return DiffResult(
            kind="scalar",
            entries=[_prefix.leaf_entry(actual="<circular ref>", expected="<circular ref>")],
        )
    _seen = _seen | {pair_key[0], pair_key[1]}

    strict_descent = False
    if config is not None:
        # the root, where identity does not stand in for equality
        decision = _node_decision(actual, expected, config, at_root=_prefix is _ROOT)
        if decision == "equal":
            return DiffResult(kind="scalar", entries=[])
        if decision == "leaf":
            return DiffResult(kind="scalar", entries=[_prefix.leaf_entry(actual=actual, expected=expected)])
        strict_descent = decision == "strict"

    def _field_entries(
        field_actual: object, field_expected: object, field_path: _Path, descended_for
    ) -> list[DiffEntry]:
        return _child_entries(
            field_actual, field_expected, field_path, descended_for=descended_for, _seen=_seen, config=config
        )

    if is_namedtuple(actual) and is_namedtuple(expected):
        entries: list[DiffEntry] = []
        for field in actual._fields:
            actual_value = getattr(actual, field)
            # a field name colliding with an inherited tuple method resolves to that method rather than being absent
            if field not in expected._fields:
                entries.append(_prefix.attr(field).entry(actual=actual_value, expected=None, absent="expected"))
            else:
                expected_value = getattr(expected, field)
                decision = _node_decision(actual_value, expected_value, config, field=field)
                if decision == "leaf":
                    entries.append(_prefix.attr(field).entry(actual=actual_value, expected=expected_value))
                elif decision != "equal":
                    entries.extend(_field_entries(actual_value, expected_value, _prefix.attr(field), decision))
        entries.extend(
            _prefix.attr(field).entry(actual=None, absent="actual", expected=getattr(expected, field))
            for field in expected._fields
            if field not in actual._fields
        )
        return DiffResult(kind="namedtuple", entries=entries)
    if (
        dataclasses.is_dataclass(actual)
        and not isinstance(actual, type)
        and dataclasses.is_dataclass(expected)
        and not isinstance(expected, type)
    ):
        return DiffResult(
            kind="dataclass",
            entries=_dataclass_diff_entries(actual, expected, _prefix, _seen, config),
        )
    both_model = is_model_dump_object(actual) and is_model_dump_object(expected)
    both_attrs = is_attrs_instance(actual) and is_attrs_instance(expected)
    if both_model or both_attrs:
        actual_dict = _field_dict(actual, both_model)
        expected_dict = _field_dict(expected, both_model)
        entries = []
        for key in _ordered_keys(actual_dict, expected_dict):
            if key not in expected_dict:
                entries.append(_prefix.attr(key).entry(actual=actual_dict[key], expected=None, absent="expected"))
            elif key not in actual_dict:
                entries.append(_prefix.attr(key).entry(actual=None, absent="actual", expected=expected_dict[key]))
            else:
                decision = _node_decision(actual_dict[key], expected_dict[key], config, field=key)
                if decision == "leaf":
                    entries.append(_prefix.attr(key).entry(actual=actual_dict[key], expected=expected_dict[key]))
                elif decision != "equal":
                    entries.extend(
                        _child_entries(
                            actual_dict[key],
                            expected_dict[key],
                            _prefix.attr(key),
                            descended_for=decision,
                            _seen=_seen,
                            config=config,
                        )
                    )
        return DiffResult(kind="model" if both_model else "attrs", entries=entries)
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        return DiffResult(
            kind="sequence",
            entries=_sequence_diff_entries(actual, expected, _prefix, _seen, config),
        )
    if isinstance(actual, (set, frozenset)) and isinstance(expected, (set, frozenset)):
        entries = []
        for item in sorted(actual - expected, key=_safe_repr):
            entries.append(_prefix.member(item, "extra").entry(actual=item, expected=None, absent="expected"))
        for item in sorted(expected - actual, key=_safe_repr):
            entries.append(_prefix.member(item, "missing").entry(actual=None, absent="actual", expected=item))
        return DiffResult(kind="set", entries=entries)
    # bytes render as `b'...'`, which difflib points into like text, and both expose `splitlines()`
    both_text = isinstance(actual, str) and isinstance(expected, str)
    both_bytes = isinstance(actual, (bytes, bytearray)) and isinstance(expected, (bytes, bytearray))
    if both_text or both_bytes:
        entries = []
        actual_lines = actual.splitlines()
        expected_lines = expected.splitlines()
        max_len = max(len(actual_lines), len(expected_lines))
        for i in range(max_len):
            if i >= len(actual_lines):
                entries.append(_prefix.line(i + 1).entry(actual=None, absent="actual", expected=expected_lines[i]))
            elif i >= len(expected_lines):
                entries.append(_prefix.line(i + 1).entry(actual=actual_lines[i], expected=None, absent="expected"))
            elif actual_lines[i] != expected_lines[i]:
                entries.append(_prefix.line(i + 1).entry(actual=actual_lines[i], expected=expected_lines[i]))
        if not entries:
            entries.append(DiffEntry(path=".", actual=actual, expected=expected))
        return DiffResult(kind="string", entries=entries)
    # under a strict descent this means the two sides were already equal, not that they differ
    if strict_descent:
        return DiffResult(kind="scalar", entries=[])
    return DiffResult(kind="scalar", entries=[_prefix.leaf_entry(actual=actual, expected=expected)])


def _sub_diff_entries(
    actual: object, expected: object, prefix: _Path = _ROOT, *, _seen: set[int] | None = None, config=None
) -> list[DiffEntry] | None:
    """Canonical recursive diff for a value, returning path-level entries (or ``None`` for a leaf).

    Recurses into mappings, dataclasses, namedtuples, model-dump objects and sequences, returning a
    (possibly empty) list for those; anything else returns ``None`` so the caller renders a single
    leaf entry.  The empty-list-vs-``None`` distinction lets a caller tell a recursable value whose
    children are all ``config``-tolerated (empty list, no entry) from a genuinely differing leaf
    (``None``, one entry).  This is the single nested engine shared by the top-level paths:
    `_build_equality_diff()` (lists, dataclasses, ...) and the dict path
    (`HelpersMixin._dict_err()`), which calls it with an empty ``prefix`` so the top-level dict
    keys render bare (``b``) and nested keys render dotted (``u.b``).
    """
    if _seen is None:
        _seen = set()
    if id(actual) in _seen or id(expected) in _seen:
        return [prefix.entry(actual="<circular ref>", expected="<circular ref>")]

    if is_mapping_like(actual) and is_mapping_like(expected):
        child_seen = _seen | {id(actual), id(expected)}
        entries: list[DiffEntry] = []
        actual_keys = set(actual)
        expected_keys = set(expected)
        if config is not None and config.strict_types:
            # `{True} & {1}` hands back whichever side the set drew from, losing the type that differs
            stored = {key: key for key in expected}
            for key in actual:
                counterpart = stored.get(key, key)
                if type(key) is not type(counterpart):
                    entries.append(prefix.key(key).entry(actual=key, expected=counterpart))
        for key in _ordered_keys(actual, expected):
            if key not in expected_keys:
                entries.append(prefix.key(key).entry(actual=actual[key], expected=None, absent="expected"))
            elif key not in actual_keys:
                entries.append(prefix.key(key).entry(actual=None, absent="actual", expected=expected[key]))
            else:
                decision = _node_decision(actual[key], expected[key], config, field=key)
                if decision == "leaf":
                    entries.append(prefix.key(key).entry(actual=actual[key], expected=expected[key]))
                elif decision != "equal":
                    entries.extend(
                        _child_entries(
                            actual[key],
                            expected[key],
                            prefix.key(key),
                            descended_for=decision,
                            _seen=child_seen,
                            config=config,
                        )
                    )
        return entries
    if (
        dataclasses.is_dataclass(actual)
        and not isinstance(actual, type)
        and dataclasses.is_dataclass(expected)
        and not isinstance(expected, type)
    ):
        child_seen = _seen | {id(actual), id(expected)}
        return _dataclass_diff_entries(actual, expected, prefix, child_seen, config)
    if is_namedtuple(actual) and is_namedtuple(expected):
        child_seen = _seen | {id(actual), id(expected)}
        entries = []
        for field_name in actual._fields:
            actual_value = getattr(actual, field_name)
            if field_name not in expected._fields:  # _fields, not getattr sentinel (count/index collide)
                entries.append(prefix.attr(field_name).entry(actual=actual_value, expected=None, absent="expected"))
            else:
                expected_value = getattr(expected, field_name)
                decision = _node_decision(actual_value, expected_value, config, field=field_name)
                if decision == "leaf":
                    entries.append(prefix.attr(field_name).entry(actual=actual_value, expected=expected_value))
                elif decision != "equal":
                    entries.extend(
                        _child_entries(
                            actual_value,
                            expected_value,
                            prefix.attr(field_name),
                            descended_for=decision,
                            _seen=child_seen,
                            config=config,
                        )
                    )
        for field_name in expected._fields:
            if field_name not in actual._fields:  # _fields, not hasattr (count/index collide)
                entries.append(
                    prefix.attr(field_name).entry(actual=None, absent="actual", expected=getattr(expected, field_name))
                )
        return entries
    both_model = is_model_dump_object(actual) and is_model_dump_object(expected)
    both_attrs = is_attrs_instance(actual) and is_attrs_instance(expected)
    if both_model or both_attrs:
        child_seen = _seen | {id(actual), id(expected)}
        actual_dict = _field_dict(actual, both_model)
        expected_dict = _field_dict(expected, both_model)
        entries = []
        for key in _ordered_keys(actual_dict, expected_dict):
            if key not in expected_dict:
                entries.append(prefix.attr(key).entry(actual=actual_dict[key], expected=None, absent="expected"))
            elif key not in actual_dict:
                entries.append(prefix.attr(key).entry(actual=None, absent="actual", expected=expected_dict[key]))
            else:
                decision = _node_decision(actual_dict[key], expected_dict[key], config, field=key)
                if decision == "leaf":
                    entries.append(prefix.attr(key).entry(actual=actual_dict[key], expected=expected_dict[key]))
                elif decision != "equal":
                    entries.extend(
                        _child_entries(
                            actual_dict[key],
                            expected_dict[key],
                            prefix.attr(key),
                            descended_for=decision,
                            _seen=child_seen,
                            config=config,
                        )
                    )
        return entries
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        child_seen = _seen | {id(actual), id(expected)}
        return _sequence_diff_entries(actual, expected, prefix, child_seen, config)
    return None


def _walk_leaves(value, prefix: _Path = _ROOT, _seen=None):
    """Yield ``(path, leaf)`` for every scalar leaf of an object graph, depth-first.

    Recurses into the same containers as the rich-diff engine (`_sub_diff_entries()`): mappings,
    dataclasses, namedtuples, model-dump objects, attrs instances, lists and tuples.  Anything else -
    scalars, strings, sets, opaque objects - is yielded as a single leaf, so the paths match the diffs.
    A circular reference yields one ``(path, "<circular ref>")`` leaf and stops, mirroring the cycle guard.

    A field of the value itself is named bare (``age``) where the diff walkers name it ``.age``: these
    paths go into a message about the fields of the value under test, not into a diff between two of them.
    """
    if _seen is None:
        _seen = set()
    if id(value) in _seen:
        yield (prefix, "<circular ref>")
        return
    if is_mapping_like(value):
        child_seen = _seen | {id(value)}
        for key in value:
            yield from _walk_leaves(value[key], prefix.key(key), child_seen)
        return
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        child_seen = _seen | {id(value)}
        for field in dataclasses.fields(value):
            child = prefix.attr(field.name, dotted_at_root=False)
            yield from _walk_leaves(getattr(value, field.name), child, child_seen)
        return
    if is_namedtuple(value):
        child_seen = _seen | {id(value)}
        for field_name in value._fields:
            child = prefix.attr(field_name, dotted_at_root=False)
            yield from _walk_leaves(getattr(value, field_name), child, child_seen)
        return
    if is_model_dump_object(value):
        child_seen = _seen | {id(value)}
        dumped = value.model_dump()
        for key in dumped:
            yield from _walk_leaves(dumped[key], prefix.attr(str(key), dotted_at_root=False), child_seen)
        return
    if is_attrs_instance(value):
        child_seen = _seen | {id(value)}
        for field in value.__attrs_attrs__:
            child = prefix.attr(field.name, dotted_at_root=False)
            yield from _walk_leaves(getattr(value, field.name), child, child_seen)
        return
    if isinstance(value, (list, tuple)):
        child_seen = _seen | {id(value)}
        for index, item in enumerate(value):
            yield from _walk_leaves(item, prefix.index(index), child_seen)
        return
    yield (prefix, value)
