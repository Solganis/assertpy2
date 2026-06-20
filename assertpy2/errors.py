from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DiffEntry:
    """Single difference between actual and expected values at a specific path."""

    path: str
    actual: object = None
    expected: object = None

    def __str__(self) -> str:
        return f"  at {self.path}: actual=<{self.actual}>, expected=<{self.expected}>"


@dataclass
class DiffResult:
    """Structured diff between two values."""

    kind: str
    entries: list[DiffEntry] = field(default_factory=list)

    def __str__(self) -> str:
        if not self.entries:
            return ""
        lines = [f"diff ({self.kind}):"]
        for entry in self.entries:
            lines.append(str(entry))
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
