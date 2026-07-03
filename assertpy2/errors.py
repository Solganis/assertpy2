from __future__ import annotations

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
