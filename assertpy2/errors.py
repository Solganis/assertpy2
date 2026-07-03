from __future__ import annotations

import math
from dataclasses import dataclass, field


def _safe_repr(value: object) -> str:
    """``repr(value)`` that never raises: error rendering must survive a broken user ``__repr__``."""
    try:
        return repr(value)
    except Exception:  # any user exception here must not shadow the assertion failure being rendered
        return f"<unreprable {type(value).__name__}>"


def _safe_str(value: object) -> str:
    """``str(value)`` that never raises, falling back to `_safe_repr`."""
    try:
        return str(value)
    except Exception:
        return _safe_repr(value)


def _truncated(text: str, limit: int = 4000) -> str:
    """Cap *text* for embedding into a failure message; normal-sized values stay byte-identical.

    Bounds only the rendered message: the structured payload (`AssertionFailure.actual` /
    ``.expected`` / ``.diff``) always keeps the full data.
    """
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... ({len(text) - limit} more chars)"


def _json_safe(value, _depth=0, _seen=None):
    """Convert *value* to JSON-native data for an attachment: typed where possible, bounded and total.

    Scalars and containers pass through as real JSON values so the Allure viewer renders a tree and
    consumers can parse them.  Everything else degrades to a marked fallback instead of failing the
    attachment: ``{"__repr__": ...}`` for non-JSON values (objects, datetimes, non-finite floats,
    cycles, over-deep nesting), the snapshot codec's ``{"__type__": "set", "__data__": [...]}``
    envelope for sets, and `_truncated` caps on strings and container sizes.
    """
    if _seen is None:
        _seen = set()
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"__repr__": repr(value)}
    if isinstance(value, str):
        return _truncated(value)
    if _depth >= 6:
        return {"__repr__": _truncated(_safe_repr(value))}
    if id(value) in _seen:
        return {"__repr__": "<circular ref>"}
    if isinstance(value, dict):
        seen = _seen | {id(value)}
        items = list(value.items())
        out = {}
        for key, val in items[:100]:
            out[key if isinstance(key, str) else _safe_repr(key)] = _json_safe(val, _depth + 1, seen)
        if len(items) > 100:
            out["__truncated__"] = f"... and {len(items) - 100} more keys"
        return out
    if isinstance(value, (list, tuple)):
        seen = _seen | {id(value)}
        out = [_json_safe(item, _depth + 1, seen) for item in value[:100]]
        if len(value) > 100:
            out.append({"__repr__": f"... and {len(value) - 100} more items"})
        return out
    if isinstance(value, (set, frozenset)):
        items = sorted(value, key=_safe_repr)
        return {"__type__": "set", "__data__": [_json_safe(item, _depth + 1, _seen) for item in items[:100]]}
    return {"__repr__": _truncated(_safe_repr(value))}


@dataclass(frozen=True, slots=True, kw_only=True)
class DiffEntry:
    """Single difference between actual and expected values at a specific path."""

    path: str
    actual: object = None
    expected: object = None

    def __str__(self) -> str:
        return f"  at {self.path}: actual=<{_truncated(str(self.actual))}>, expected=<{_truncated(str(self.expected))}>"


@dataclass(frozen=True, slots=True, kw_only=True)
class DiffResult:
    """Structured diff between two values.

    ``kind`` is the diff *category* - which shape of comparison produced the entries (``"dict"``,
    ``"sequence"``, ``"dataclass"``, ``"namedtuple"``, ``"model"``, ``"set"``, ``"string"``,
    ``"scalar"``, ``"contains"``, or ``"match"``).  It is unrelated to the assertion builder's
    ``kind`` argument, which selects the failure mode (``None``/``"soft"``/``"warn"``).
    """

    kind: str
    entries: list[DiffEntry] = field(default_factory=list)

    def __str__(self) -> str:
        if not self.entries:
            return ""
        lines = [f"diff ({self.kind}):"]
        lines.extend(str(entry) for entry in self.entries[:50])
        if len(self.entries) > 50:
            lines.append(f"  ... and {len(self.entries) - 50} more entries")
        return "\n".join(lines)


class AssertionFailure(AssertionError):  # noqa: N818  # public exception name; kept for backward compatibility
    """Structured assertion failure with optional diff data.

    Subclasses AssertionError for full backward compatibility:
    existing ``except AssertionError`` handlers catch it transparently.
    """

    def __init__(
        self,
        message: str,
        *,
        actual: object = None,
        expected: object = None,
        diff: DiffResult | None = None,
    ):
        super().__init__(message)
        self.actual = actual
        self.expected = expected
        self.diff = diff
