"""Recursive diff engine shared by the equality assertions and the dict error path.

Three walkers coexist on purpose and must not be merged: `_build_equality_diff()` dispatches a
top-level pair (top-level dicts are handled by `HelpersMixin._dict_err()` instead, so its ladder
starts at namedtuples), `_sub_diff_entries()` decomposes nested values (mappings first), and
`_walk_leaves()` iterates scalar leaves for the recursive leaf assertions.  Their dispatch orders
differ deliberately; a shared type classifier was investigated and rejected, because a single global
precedence changes behavior for values that quack like several container shapes at once.
`_sequence_diff_entries()` and `_dataclass_diff_entries()` are the pieces genuinely shared by the
diff builders.
"""

from __future__ import annotations

import dataclasses
from typing import Final

from ._compare import _node_decision
from ._introspection import is_attrs_instance, is_mapping_like, is_model_dump_object, is_namedtuple
from .errors import DiffEntry, DiffResult, _safe_repr, _safe_str

__tracebackhide__ = True

_SENTINEL: Final = object()


def _field_dict(obj, is_model):
    """Field mapping of a pydantic-style model (``model_dump()``) or an attrs instance (shallow)."""
    if is_model:
        return obj.model_dump()
    return {field.name: getattr(obj, field.name) for field in obj.__attrs_attrs__}


def _sequence_diff_entries(actual, expected, prefix, seen, config=None) -> list[DiffEntry]:
    """Diff two sequences element-by-element, recursing into nested containers.

    ``seen`` must already include the ids of ``actual``/``expected`` so a self-referential element
    is caught.  Shared by the top-level (`_build_equality_diff()`) and nested
    (`_sub_diff_entries()`) paths so both decompose sequences identically.  Elements have no field
    name, so a ``config`` applies only type comparators and tolerance to them.
    """
    entries: list[DiffEntry] = []
    max_len = max(len(actual), len(expected))
    for i in range(max_len):
        path = f"{prefix}[{i}]" if prefix else f"[{i}]"
        if i >= len(actual):
            entries.append(DiffEntry(path=path, actual=None, expected=expected[i]))
        elif i >= len(expected):
            entries.append(DiffEntry(path=path, actual=actual[i], expected=None))
        else:
            decision = _node_decision(actual[i], expected[i], config)
            if decision == "leaf":
                entries.append(DiffEntry(path=path, actual=actual[i], expected=expected[i]))
            elif decision == "recurse":
                sub_entries = _sub_diff_entries(actual[i], expected[i], path, _seen=seen, config=config)
                if sub_entries is not None:
                    entries.extend(sub_entries)
                else:
                    entries.append(DiffEntry(path=path, actual=actual[i], expected=expected[i]))
    return entries


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
            elif decision == "recurse":
                sub_entries = _sub_diff_entries(actual_value, expected_value, path, _seen=seen, config=config)
                if sub_entries is not None:
                    entries.extend(sub_entries)
                else:
                    entries.append(DiffEntry(path=path, actual=actual_value, expected=expected_value))
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

    if config is not None:
        decision = _node_decision(actual, expected, config)
        if decision == "equal":
            return DiffResult(kind="scalar", entries=[])
        if decision == "leaf":
            return DiffResult(kind="scalar", entries=[DiffEntry(path=_prefix or ".", actual=actual, expected=expected)])

    def _field_entries(field_actual: object, field_expected: object, field_path: str) -> list[DiffEntry]:
        nested = _sub_diff_entries(field_actual, field_expected, field_path, _seen=_seen, config=config)
        if nested is not None:
            return nested
        return [DiffEntry(path=field_path, actual=field_actual, expected=field_expected)]

    if is_namedtuple(actual) and is_namedtuple(expected):
        entries: list[DiffEntry] = []
        for field in actual._fields:
            actual_value = getattr(actual, field)
            expected_value = getattr(expected, field, _SENTINEL)
            path = f"{_prefix}.{field}"
            if expected_value is _SENTINEL:
                entries.append(DiffEntry(path=path, actual=actual_value, expected=None))
            else:
                decision = _node_decision(actual_value, expected_value, config, field=field)
                if decision == "leaf":
                    entries.append(DiffEntry(path=path, actual=actual_value, expected=expected_value))
                elif decision == "recurse":
                    entries.extend(_field_entries(actual_value, expected_value, path))
        entries.extend(
            DiffEntry(path=f"{_prefix}.{field}", actual=None, expected=getattr(expected, field))
            for field in expected._fields
            if not hasattr(actual, field)
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
                elif decision == "recurse":
                    sub_entries = _sub_diff_entries(
                        actual_dict[key], expected_dict[key], path, _seen=_seen, config=config
                    )
                    if sub_entries is not None:
                        entries.extend(sub_entries)
                    else:
                        entries.append(DiffEntry(path=path, actual=actual_dict[key], expected=expected_dict[key]))
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
    if isinstance(actual, str) and isinstance(expected, str):
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
                elif decision == "recurse":
                    sub_entries = _sub_diff_entries(actual[key], expected[key], path, _seen=child_seen, config=config)
                    if sub_entries is not None:
                        entries.extend(sub_entries)
                    else:
                        entries.append(DiffEntry(path=path, actual=actual[key], expected=expected[key]))
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
            expected_value = getattr(expected, field_name, _SENTINEL)
            if expected_value is _SENTINEL:
                entries.append(DiffEntry(path=f"{prefix}.{field_name}", actual=actual_value, expected=None))
            else:
                decision = _node_decision(actual_value, expected_value, config, field=field_name)
                if decision == "leaf":
                    entries.append(
                        DiffEntry(path=f"{prefix}.{field_name}", actual=actual_value, expected=expected_value)
                    )
                elif decision == "recurse":
                    sub_entries = _sub_diff_entries(
                        actual_value, expected_value, f"{prefix}.{field_name}", _seen=child_seen, config=config
                    )
                    if sub_entries is not None:
                        entries.extend(sub_entries)
                    else:
                        entries.append(
                            DiffEntry(path=f"{prefix}.{field_name}", actual=actual_value, expected=expected_value)
                        )
        for field_name in expected._fields:
            if not hasattr(actual, field_name):
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
                elif decision == "recurse":
                    sub_entries = _sub_diff_entries(
                        actual_dict[key], expected_dict[key], path, _seen=child_seen, config=config
                    )
                    if sub_entries is not None:
                        entries.extend(sub_entries)
                    else:
                        entries.append(DiffEntry(path=path, actual=actual_dict[key], expected=expected_dict[key]))
        return entries
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        child_seen = _seen | {id(actual), id(expected)}
        return _sequence_diff_entries(actual, expected, prefix, child_seen, config)
    return None


def _walk_leaves(value, prefix="", _seen=None):
    """Yield ``(path, leaf)`` for every scalar leaf of an object graph, depth-first.

    Recurses into the same containers as the rich-diff engine (`_sub_diff_entries()`): mappings,
    dataclasses, namedtuples, model-dump objects, lists and tuples.  Anything else - scalars, strings,
    sets, opaque objects - is yielded as a single leaf, so the paths match the diffs.  A circular
    reference yields one ``(path, "<circular ref>")`` leaf and stops, mirroring the cycle guard.
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
    if isinstance(value, (list, tuple)):
        child_seen = _seen | {id(value)}
        for index, item in enumerate(value):
            yield from _walk_leaves(item, f"{prefix}[{index}]" if prefix else f"[{index}]", child_seen)
        return
    yield (prefix or ".", value)
