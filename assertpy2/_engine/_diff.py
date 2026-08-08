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

from ..errors import DiffEntry, DiffResult, _safe_repr, _safe_str
from ._compare import _node_decision
from ._introspection import is_attrs_instance, is_mapping_like, is_model_dump_object, is_namedtuple

__tracebackhide__ = True


def _field_dict(obj, is_model):
    """Field mapping of a pydantic-style model (``model_dump()``) or an attrs instance (shallow)."""
    if is_model:
        return obj.model_dump()
    return {field.name: getattr(obj, field.name) for field in obj.__attrs_attrs__}


def _child_entries(actual, expected, path, *, descended_for, _seen=None, config=None) -> list[DiffEntry]:
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
    return [DiffEntry(path=path, actual=actual, expected=expected)]


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

    The length cap lives in the caller, which reaches it before paying for anything here.
    """
    try:
        return difflib.SequenceMatcher(None, actual, expected, autojunk=False).get_opcodes()
    except (TypeError, ValueError):
        pass
    try:
        keyed_actual = [_safe_repr(item) for item in actual]
        keyed_expected = [_safe_repr(item) for item in expected]
        return difflib.SequenceMatcher(None, keyed_actual, keyed_expected, autojunk=False).get_opcodes()
    # pragma: no cover - not reachable through a broken __repr__: `_safe_repr` swallows everything and
    # returns a str, and strs are always hashable. What is left is a value whose iteration fails after
    # `len()` on it succeeded, so the guard keeps that degrading to a positional diff instead of raising.
    except (TypeError, ValueError):  # pragma: no cover
        return None


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
    """How many positions the two sequences differ at when paired by index."""
    return sum(
        1
        for index in range(max(len(actual), len(expected)))
        if index >= len(actual) or index >= len(expected) or actual[index] != expected[index]
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
        # a shift changes the length, and asked before anything is counted this keeps the whole cost
        # off the common failure: two sequences of records, same length, one field different.  Equal
        # lengths can still shift - a rotation - but measured over 13 640 random pairs that is 8% of
        # the cases alignment wins, against a doubled comparison on every equal-length diff
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


def _sequence_diff_entries(actual, expected, prefix, seen, config=None) -> list[DiffEntry]:
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
        path = f"{prefix}[{i}]" if prefix else f"[{i}]"
        if i >= len(actual):
            entries.append(DiffEntry(path=path, actual=None, expected=expected[i]))
        elif i >= len(expected):
            entries.append(DiffEntry(path=path, actual=actual[i], expected=None))
        else:
            # inlined rather than routed through `_element_entries()`: this runs once per element of
            # every sequence diff, and returning an empty list for an equal element cost 15% of the
            # walk in allocations alone
            decision = _node_decision(actual[i], expected[i], config)
            if decision == "leaf":
                entries.append(DiffEntry(path=path, actual=actual[i], expected=expected[i]))
            elif decision != "equal":
                entries.extend(
                    _child_entries(actual[i], expected[i], path, descended_for=decision, _seen=seen, config=config)
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
            continue  # difflib matched these on ``==``, which is the whole test when no config narrows it
        for offset in range(max(actual_stop - actual_start, expected_stop - expected_start)):
            actual_index, expected_index = actual_start + offset, expected_start + offset
            if actual_index >= actual_stop:
                path = f"{prefix}expected[{expected_index}]" if prefix else f"expected[{expected_index}]"
                entries.append(DiffEntry(path=path, actual=None, expected=expected[expected_index]))
            elif expected_index >= expected_stop:
                path = f"{prefix}actual[{actual_index}]" if prefix else f"actual[{actual_index}]"
                entries.append(DiffEntry(path=path, actual=actual[actual_index], expected=None))
            else:
                path = f"{prefix}[{actual_index}]" if prefix else f"[{actual_index}]"
                entries.extend(_element_entries(actual[actual_index], expected[expected_index], path, seen, config))
    return entries


def _element_entries(actual_item, expected_item, path, seen, config) -> list[DiffEntry]:
    """Entries for one paired element: none when equal, one leaf, or the nested sub-diff."""
    decision = _node_decision(actual_item, expected_item, config)
    if decision == "equal":
        return []
    if decision == "leaf":
        return [DiffEntry(path=path, actual=actual_item, expected=expected_item)]
    return _child_entries(actual_item, expected_item, path, descended_for=decision, _seen=seen, config=config)


def _dataclass_diff_entries(actual, expected, prefix, seen, config=None) -> list[DiffEntry]:
    """Diff two dataclasses over the sorted union of field names, both directions, recursing.

    Reports fields present on only one side, and recurses into nested containers.  ``seen`` must
    already include the ids of ``actual``/``expected``.  Shared by the top-level and nested paths
    so both report dataclass fields identically.
    """
    entries: list[DiffEntry] = []
    actual_names = {field.name for field in dataclasses.fields(actual)}
    expected_names = {field.name for field in dataclasses.fields(expected)}
    for field in sorted(actual_names | expected_names):
        path = f"{prefix}.{field}"
        if field not in expected_names:
            entries.append(DiffEntry(path=path, actual=getattr(actual, field), expected=None))
        elif field not in actual_names:
            entries.append(DiffEntry(path=path, actual=None, expected=getattr(expected, field)))
        else:
            actual_value = getattr(actual, field)
            expected_value = getattr(expected, field)
            decision = _node_decision(actual_value, expected_value, config, field=field)
            if decision == "leaf":
                entries.append(DiffEntry(path=path, actual=actual_value, expected=expected_value))
            elif decision != "equal":
                entries.extend(
                    _child_entries(
                        actual_value, expected_value, path, descended_for=decision, _seen=seen, config=config
                    )
                )
    return entries


def _build_equality_diff(
    actual: object, expected: object, *, _prefix: str = "", _seen: set[int] | None = None, config=None
) -> DiffResult:
    if _seen is None:
        _seen = set()
    pair_key = (id(actual), id(expected))
    if pair_key[0] in _seen or pair_key[1] in _seen:
        return DiffResult(
            kind="scalar",
            entries=[DiffEntry(path=_prefix or ".", actual="<circular ref>", expected="<circular ref>")],
        )
    _seen = _seen | {pair_key[0], pair_key[1]}

    strict_descent = False
    if config is not None:
        decision = _node_decision(actual, expected, config)
        if decision == "equal":
            return DiffResult(kind="scalar", entries=[])
        if decision == "leaf":
            return DiffResult(kind="scalar", entries=[DiffEntry(path=_prefix or ".", actual=actual, expected=expected)])
        # descended only to check the types inside; the ladder below decides whether there is an inside
        strict_descent = decision == "strict"

    def _field_entries(field_actual: object, field_expected: object, field_path: str, descended_for) -> list[DiffEntry]:
        return _child_entries(
            field_actual, field_expected, field_path, descended_for=descended_for, _seen=_seen, config=config
        )

    if is_namedtuple(actual) and is_namedtuple(expected):
        entries: list[DiffEntry] = []
        for field in actual._fields:
            actual_value = getattr(actual, field)
            path = f"{_prefix}.{field}"
            # use _fields membership, not getattr/hasattr: a field name colliding with an inherited
            # tuple method (count/index) would otherwise resolve to that bound method, not be "absent"
            if field not in expected._fields:
                entries.append(DiffEntry(path=path, actual=actual_value, expected=None))
            else:
                expected_value = getattr(expected, field)
                decision = _node_decision(actual_value, expected_value, config, field=field)
                if decision == "leaf":
                    entries.append(DiffEntry(path=path, actual=actual_value, expected=expected_value))
                elif decision != "equal":
                    entries.extend(_field_entries(actual_value, expected_value, path, decision))
        entries.extend(
            DiffEntry(path=f"{_prefix}.{field}", actual=None, expected=getattr(expected, field))
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
        for key in sorted(set(actual_dict) | set(expected_dict)):
            path = f"{_prefix}.{key}" if _prefix else f".{key}"
            if key not in expected_dict:
                entries.append(DiffEntry(path=path, actual=actual_dict[key], expected=None))
            elif key not in actual_dict:
                entries.append(DiffEntry(path=path, actual=None, expected=expected_dict[key]))
            else:
                decision = _node_decision(actual_dict[key], expected_dict[key], config, field=key)
                if decision == "leaf":
                    entries.append(DiffEntry(path=path, actual=actual_dict[key], expected=expected_dict[key]))
                elif decision != "equal":
                    entries.extend(
                        _child_entries(
                            actual_dict[key],
                            expected_dict[key],
                            path,
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
            entries.append(DiffEntry(path="extra", actual=item, expected=None))
        for item in sorted(expected - actual, key=_safe_repr):
            entries.append(DiffEntry(path="missing", actual=None, expected=item))
        return DiffResult(kind="set", entries=entries)
    # bytes render as their b'...' literal, which difflib can point into exactly like text, and both
    # kinds expose splitlines(), so one branch serves them
    both_text = isinstance(actual, str) and isinstance(expected, str)
    both_bytes = isinstance(actual, (bytes, bytearray)) and isinstance(expected, (bytes, bytearray))
    if both_text or both_bytes:
        entries = []
        actual_lines = actual.splitlines()
        expected_lines = expected.splitlines()
        max_len = max(len(actual_lines), len(expected_lines))
        for i in range(max_len):
            if i >= len(actual_lines):
                entries.append(DiffEntry(path=f"line {i + 1}", actual=None, expected=expected_lines[i]))
            elif i >= len(expected_lines):
                entries.append(DiffEntry(path=f"line {i + 1}", actual=actual_lines[i], expected=None))
            elif actual_lines[i] != expected_lines[i]:
                entries.append(DiffEntry(path=f"line {i + 1}", actual=actual_lines[i], expected=expected_lines[i]))
        if not entries:
            entries.append(DiffEntry(path=".", actual=actual, expected=expected))
        return DiffResult(kind="string", entries=entries)
    # the ladder ran out: this value has no inside. Reached under a strict descent that means the two
    # sides were already equal and there was nothing further to check, not that they differ
    if strict_descent:
        return DiffResult(kind="scalar", entries=[])
    return DiffResult(kind="scalar", entries=[DiffEntry(path=_prefix or ".", actual=actual, expected=expected)])


def _sub_diff_entries(
    actual: object, expected: object, prefix: str, *, _seen: set[int] | None = None, config=None
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
        return [DiffEntry(path=prefix, actual="<circular ref>", expected="<circular ref>")]

    if is_mapping_like(actual) and is_mapping_like(expected):
        child_seen = _seen | {id(actual), id(expected)}
        entries: list[DiffEntry] = []
        actual_keys = set(actual)
        expected_keys = set(expected)
        for key in sorted(actual_keys | expected_keys, key=_safe_repr):
            path = f"{prefix}.{_safe_str(key)}" if prefix else _safe_str(key)
            if key not in expected_keys:
                entries.append(DiffEntry(path=path, actual=actual[key], expected=None))
            elif key not in actual_keys:
                entries.append(DiffEntry(path=path, actual=None, expected=expected[key]))
            else:
                decision = _node_decision(actual[key], expected[key], config, field=key)
                if decision == "leaf":
                    entries.append(DiffEntry(path=path, actual=actual[key], expected=expected[key]))
                elif decision != "equal":
                    entries.extend(
                        _child_entries(
                            actual[key], expected[key], path, descended_for=decision, _seen=child_seen, config=config
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
                entries.append(DiffEntry(path=f"{prefix}.{field_name}", actual=actual_value, expected=None))
            else:
                expected_value = getattr(expected, field_name)
                decision = _node_decision(actual_value, expected_value, config, field=field_name)
                if decision == "leaf":
                    entries.append(
                        DiffEntry(path=f"{prefix}.{field_name}", actual=actual_value, expected=expected_value)
                    )
                elif decision != "equal":
                    entries.extend(
                        _child_entries(
                            actual_value,
                            expected_value,
                            f"{prefix}.{field_name}",
                            descended_for=decision,
                            _seen=child_seen,
                            config=config,
                        )
                    )
        for field_name in expected._fields:
            if field_name not in actual._fields:  # _fields, not hasattr (count/index collide)
                entries.append(
                    DiffEntry(path=f"{prefix}.{field_name}", actual=None, expected=getattr(expected, field_name))
                )
        return entries
    both_model = is_model_dump_object(actual) and is_model_dump_object(expected)
    both_attrs = is_attrs_instance(actual) and is_attrs_instance(expected)
    if both_model or both_attrs:
        child_seen = _seen | {id(actual), id(expected)}
        actual_dict = _field_dict(actual, both_model)
        expected_dict = _field_dict(expected, both_model)
        entries = []
        for key in sorted(set(actual_dict) | set(expected_dict)):
            path = f"{prefix}.{key}"
            if key not in expected_dict:
                entries.append(DiffEntry(path=path, actual=actual_dict[key], expected=None))
            elif key not in actual_dict:
                entries.append(DiffEntry(path=path, actual=None, expected=expected_dict[key]))
            else:
                decision = _node_decision(actual_dict[key], expected_dict[key], config, field=key)
                if decision == "leaf":
                    entries.append(DiffEntry(path=path, actual=actual_dict[key], expected=expected_dict[key]))
                elif decision != "equal":
                    entries.extend(
                        _child_entries(
                            actual_dict[key],
                            expected_dict[key],
                            path,
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


def _walk_leaves(value, prefix="", _seen=None):
    """Yield ``(path, leaf)`` for every scalar leaf of an object graph, depth-first.

    Recurses into the same containers as the rich-diff engine (`_sub_diff_entries()`): mappings,
    dataclasses, namedtuples, model-dump objects, attrs instances, lists and tuples.  Anything else -
    scalars, strings, sets, opaque objects - is yielded as a single leaf, so the paths match the diffs.
    A circular reference yields one ``(path, "<circular ref>")`` leaf and stops, mirroring the cycle guard.
    """
    if _seen is None:
        _seen = set()
    if id(value) in _seen:
        yield (prefix or ".", "<circular ref>")
        return
    if is_mapping_like(value):
        child_seen = _seen | {id(value)}
        for key in value:
            yield from _walk_leaves(value[key], f"{prefix}.{_safe_str(key)}" if prefix else _safe_str(key), child_seen)
        return
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        child_seen = _seen | {id(value)}
        for field in dataclasses.fields(value):
            path = f"{prefix}.{field.name}" if prefix else field.name
            yield from _walk_leaves(getattr(value, field.name), path, child_seen)
        return
    if is_namedtuple(value):
        child_seen = _seen | {id(value)}
        for field_name in value._fields:
            path = f"{prefix}.{field_name}" if prefix else field_name
            yield from _walk_leaves(getattr(value, field_name), path, child_seen)
        return
    if is_model_dump_object(value):
        child_seen = _seen | {id(value)}
        dumped = value.model_dump()
        for key in dumped:
            yield from _walk_leaves(dumped[key], f"{prefix}.{key}" if prefix else str(key), child_seen)
        return
    if is_attrs_instance(value):
        child_seen = _seen | {id(value)}
        for field in value.__attrs_attrs__:
            path = f"{prefix}.{field.name}" if prefix else field.name
            yield from _walk_leaves(getattr(value, field.name), path, child_seen)
        return
    if isinstance(value, (list, tuple)):
        child_seen = _seen | {id(value)}
        for index, item in enumerate(value):
            yield from _walk_leaves(item, f"{prefix}[{index}]" if prefix else f"[{index}]", child_seen)
        return
    yield (prefix or ".", value)
