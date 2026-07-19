from __future__ import annotations

import difflib
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


def _callable_name(value: object) -> str:
    """A display name for a callable, tolerating those without ``__name__`` (partials, instances)."""
    return getattr(value, "__name__", None) or _safe_repr(value)


def _truncated(text: str, limit: int = 4000) -> str:
    """Cap *text* for embedding into a failure message; normal-sized values stay byte-identical.

    Bounds only the rendered message: the structured payload (`AssertionFailure.actual` /
    ``.expected`` / ``.diff``) always keeps the full data.
    """
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... ({len(text) - limit} more chars)"


def _disambiguated(actual: object, other: object) -> tuple[str, str]:
    """Render two *unequal* values, tagging each with its ``:type`` when their plain reprs would collide.

    So ``is_equal_to`` on ``"1"`` vs ``1`` reads ``<1:str>`` / ``<1:int>`` instead of a baffling
    ``<1>`` / ``<1>``, ``but was not`` - the difference is the type, and now the message says so.
    """
    actual_str, other_str = _truncated(_safe_str(actual)), _truncated(_safe_str(other))
    if actual_str == other_str:
        return f"{actual_str}:{type(actual).__name__}", f"{other_str}:{type(other).__name__}"
    return actual_str, other_str


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
        actual = _truncated(_safe_str(self.actual))
        expected = _truncated(_safe_str(self.expected))
        return f"  at {self.path}: actual=<{actual}>, expected=<{expected}>"


@dataclass(frozen=True, slots=True, kw_only=True)
class DiffResult:
    """Structured diff between two values.

    ``kind`` names the diff *category* - the shape of comparison that produced the entries. It is one
    of ``"dict"``, ``"sequence"``, ``"dataclass"``, ``"namedtuple"``, ``"model"``, ``"attrs"``,
    ``"set"``, ``"string"``, ``"scalar"``, ``"contains"``, ``"match"``, or ``"openapi"``.

    It is unrelated to the assertion builder's ``kind`` argument, which selects the failure mode
    (``None``/``"soft"``/``"warn"``).
    """

    kind: str
    entries: list[DiffEntry] = field(default_factory=list)

    def __str__(self) -> str:
        return _render_diff(self)


def _append_string_entry(lines: list[str], entry: DiffEntry, *, red: str, green: str, reset: str) -> None:
    """Render one string line-pair with difflib's intra-line caret guides, the way pytest does.

    A one-token change in a long line shows the exact span (``? ^^^``) instead of dumping both whole
    lines and leaving the reader to spot the difference.
    """
    if entry.expected is None:
        lines.append(f"  {red}{entry.path}: - {entry.actual!r}{reset}")
        return
    if entry.actual is None:
        lines.append(f"  {green}{entry.path}: + {entry.expected!r}{reset}")
        return
    actual_line, expected_line = _safe_str(entry.actual), _safe_str(entry.expected)
    lines.append(f"  {entry.path}:")
    # ndiff costs ~175x a plain pair even at the cutoff; on long lines skip the carets instead
    if len(actual_line) <= 200 and len(expected_line) <= 200:
        for guide in difflib.ndiff([actual_line], [expected_line]):
            text = guide.rstrip("\n")
            if guide.startswith("-"):
                lines.append(f"    {red}{text}{reset}")
            elif guide.startswith("+"):
                lines.append(f"    {green}{text}{reset}")
            else:  # the "? ^^^" caret guide row (ndiff emits nothing else for a changed single line)
                lines.append(f"    {text}")
    else:
        lines.append(f"    {red}- {actual_line!r}{reset}")
        lines.append(f"    {green}+ {expected_line!r}{reset}")


def _render_diff(diff: object, *, color: bool = False, max_entries: int = 50) -> str:
    """Render a `DiffResult` as aligned ``- actual`` / ``+ expected`` lines, optionally colored.

    Single source of truth for every place a diff surfaces: the pytest report section, the plain-text
    `AssertionFailure` message off pytest, and ``str(DiffResult)``.  So the diff reads identically wherever
    it is shown.
    """
    entries = getattr(diff, "entries", None)
    if not entries:
        return ""
    kind = getattr(diff, "kind", "unknown")

    red = "\033[31m" if color else ""
    green = "\033[32m" if color else ""
    cyan = "\033[36m" if color else ""
    reset = "\033[0m" if color else ""

    truncated = 0
    visible = entries
    if max_entries > 0 and len(entries) > max_entries:
        truncated = len(entries) - max_entries
        visible = entries[:max_entries]

    lines = [f"{cyan}diff ({kind}):{reset}"]

    if kind == "string":
        for entry in visible:
            _append_string_entry(lines, entry, red=red, green=green, reset=reset)
    elif kind == "match":
        lines.extend(
            f"  {cyan}{entry.path}{reset}: expected {entry.expected}, but was {red}{entry.actual!r}{reset}"
            for entry in visible
        )
    elif kind in {"set", "contains"}:
        extra = ", ".join(repr(entry.actual) for entry in visible if entry.path == "extra")
        missing = ", ".join(repr(entry.expected) for entry in visible if entry.path == "missing")
        if extra:
            lines.append(f"  {red}extra:   {{{extra}}}{reset}")
        if missing:
            lines.append(f"  {green}missing: {{{missing}}}{reset}")
    else:
        for entry in visible:
            path = entry.path
            if entry.expected is None:
                lines.append(f"  {red}{path}: - {entry.actual!r}{reset}")
            elif entry.actual is None:
                lines.append(f"  {green}{path}: + {entry.expected!r}{reset}")
            else:
                lines.append(f"  {path}:")
                lines.append(f"    {red}- {entry.actual!r}{reset}")
                lines.append(f"    {green}+ {entry.expected!r}{reset}")

    if truncated:
        lines.append(f"  ... and {truncated} more entries")

    return "\n".join(lines)


_RENDER_DIFF_IN_MESSAGE: bool = True
"""Whether `AssertionFailure.__str__` appends the rendered diff to its message.

The pytest plugin renders the diff itself as a dedicated colored report section, so it turns this off at
configure time to avoid showing the diff twice.  Off pytest (unittest, plain scripts, CI logs) it stays on,
so the structured diff travels with ``str(exc)`` instead of being lost.
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class PollSample:
    """One recorded poll of an [`eventually()`][assertpy2.assertpy.AssertionBuilder.eventually] probe.

    ``outcome`` is ``"fail"`` (the probe returned a value and the assertion on it failed) or
    ``"error"`` (the probe raised an ignored exception before producing a value).

    ``value`` is a JSON-safe point-in-time snapshot of the probed value, ``None`` for ``"error"``
    samples, and ``detail`` carries the failure message or the exception repr.

    Consecutive identical polls are collapsed into one sample: ``repeats`` counts the run, and
    ``elapsed`` is its first occurrence, in seconds from the start of polling.
    """

    elapsed: float
    outcome: str
    value: object
    detail: str
    repeats: int = 1


@dataclass(frozen=True, slots=True, kw_only=True)
class PollTrace:
    """Convergence telemetry attached to an ``eventually()`` timeout failure.

    ``samples`` keeps the first and last polls, with middle entries beyond the retention window
    counted in ``dropped``, and ``total_polls`` is the real number of polls.

    ``summary`` is a one-line trend classification of why the condition never held.
    """

    samples: list[PollSample]
    total_polls: int
    dropped: int
    elapsed: float
    summary: str


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
        trace: PollTrace | None = None,
    ):
        super().__init__(message)
        self._message = message
        self.actual = actual
        self.expected = expected
        self.diff = diff
        self.trace = trace

    def __str__(self) -> str:
        if _RENDER_DIFF_IN_MESSAGE and self.diff is not None:
            rendered = _render_diff(self.diff)
            if rendered:
                return f"{self._message}\n{rendered}"
        return self._message
