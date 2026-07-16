"""Inline-snapshot recording: locate the ``matches_inline()`` call in the test source and rewrite it
to carry the captured value as a literal.

Only the recording paths (empty call under update mode) live here and touch ``executing``/``asttokens``;
the comparison path in ``snapshot.py`` is a plain equality check that needs none of this.
"""

from __future__ import annotations

import pprint
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import FrameType

# edits to apply at session end: (filename, start, end, replacement) - replace source[start:end]
_RECORDS: list[tuple[str, int, int, str]] = []

_LITERAL_TYPES = (str, int, float, bool, type(None))


def _ensure_inline_tooling():
    try:
        import asttokens  # noqa: F401  # optional dependency, imported to fail early with a clear message
        import executing
    except ImportError:
        raise ImportError(
            "recording inline snapshots requires the 'executing' and 'asttokens' packages."
            " Install them with: pip install assertpy2[inline]"
        ) from None
    return executing


def is_literalable(value: object) -> bool:
    """Whether ``value`` round-trips as a source literal (dict/list/tuple/set of scalars)."""
    if isinstance(value, dict):
        return all(is_literalable(key) and is_literalable(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return all(is_literalable(item) for item in value)
    return isinstance(value, _LITERAL_TYPES)


def _format_literal(value: object, column: int) -> str:
    """Render ``value`` as a source literal, wrapping wide values and indenting to ``column``."""
    raw = pprint.pformat(value, sort_dicts=False, width=max(20, 116 - column))
    lines = raw.split("\n")
    if len(lines) == 1:
        return raw
    pad = " " * column
    return lines[0] + "".join(f"\n{pad}{line}" for line in lines[1:])


def record_create(frame: FrameType, value: object) -> None:
    """Record an insertion of ``value`` as the literal argument of the empty ``matches_inline()`` call
    at ``frame``'s current instruction, applied at session end."""
    executing = _ensure_inline_tooling()
    source = executing.Source.for_frame(frame)
    node = source.executing(frame).node
    if node is None:  # pragma: no cover - executing resolves the call under pytest; guard exotic runners
        raise RuntimeError("could not locate the matches_inline() call to record the inline snapshot")
    _start, end = source.asttokens().get_text_range(node)  # whole call, character offsets (non-ASCII safe)
    insert_at = end - 1  # just inside the closing paren
    column = insert_at - source.text.rfind("\n", 0, insert_at) - 1
    _RECORDS.append((frame.f_code.co_filename, insert_at, insert_at, _format_literal(value, column)))


def record_update(frame: FrameType, value: object) -> None:
    """Record a replacement of the existing ``matches_inline(<literal>)`` argument with ``value``."""
    executing = _ensure_inline_tooling()
    source = executing.Source.for_frame(frame)
    node = source.executing(frame).node
    if node is None or not node.args:  # pragma: no cover - the caller only updates when a literal is present
        raise RuntimeError("could not locate the matches_inline() literal to update")
    start, end = source.asttokens().get_text_range(node.args[0])
    column = start - source.text.rfind("\n", 0, start) - 1
    _RECORDS.append((frame.f_code.co_filename, start, end, _format_literal(value, column)))


def apply_inline_records() -> list[str]:
    """Apply the recorded rewrites, per file, highest offset first so earlier offsets stay valid."""
    touched: list[str] = []
    by_file: dict[str, list[tuple[int, int, str]]] = {}
    for filename, start, end, text in _RECORDS:
        by_file.setdefault(filename, []).append((start, end, text))
    for filename, edits in by_file.items():
        with open(filename, encoding="utf-8") as handle:
            content = handle.read()
        for start, end, text in sorted(edits, reverse=True):
            content = content[:start] + text + content[end:]
        with open(filename, "w", encoding="utf-8") as handle:
            handle.write(content)
        touched.append(filename)
    _RECORDS.clear()
    return touched
