from __future__ import annotations

import contextlib
import json
import math
import warnings
from typing import Final

import pytest

from .errors import _safe_repr, _truncated

try:
    import allure  # ty: ignore[unresolved-import]  # optional dependency

    _HAS_ALLURE = True  # pragma: no cover - only when allure-pytest is installed
except ImportError:
    _HAS_ALLURE = False

_ALLURE_MODES: Final = frozenset({"off", "diff", "full"})


def pytest_addoption(parser):
    parser.addini(
        "assertpy2_allure",
        help="Allure attachment mode: off, diff (default), full",
        default="diff",
    )
    parser.addini(
        "assertpy2_diff",
        help="Structured diff sections in failure reports: on (default), off",
        default="on",
    )
    parser.addini(
        "assertpy2_diff_max_entries",
        help="Max diff entries to show (0 = unlimited, default 50)",
        default="50",
    )


def pytest_configure(config):
    mode = config.getini("assertpy2_allure")
    if mode not in _ALLURE_MODES:
        warnings.warn(
            f"assertpy2_allure={mode!r} is not a valid mode "
            f"({', '.join(sorted(_ALLURE_MODES))}), falling back to 'diff'",
            stacklevel=1,
        )
        config._assertpy2_allure_mode = "diff"
    else:
        config._assertpy2_allure_mode = mode
    config._assertpy2_diff_enabled = config.getini("assertpy2_diff") != "off"
    try:
        config._assertpy2_diff_max = int(config.getini("assertpy2_diff_max_entries"))
    except (ValueError, TypeError):
        config._assertpy2_diff_max = 50


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when != "call" or not report.failed:
        return
    if call.excinfo is None:
        return

    exc = call.excinfo.value
    if not isinstance(exc, AssertionError):
        return

    actual = getattr(exc, "actual", None)
    expected = getattr(exc, "expected", None)
    diff = getattr(exc, "diff", None)

    if actual is None and expected is None and diff is None:
        return

    if actual is not None or expected is not None:
        lines = []
        if actual is not None:
            lines.append(f"  actual:   {actual!r}")
        if expected is not None:
            lines.append(f"  expected: {expected!r}")
        report.sections.append(("AssertionFailure", "\n".join(lines)))

    if diff is not None and getattr(item.config, "_assertpy2_diff_enabled", True):
        use_color = getattr(item.config.option, "color", "no") != "no"
        max_entries = getattr(item.config, "_assertpy2_diff_max", 50)
        report.sections.append(("Structured Diff", _format_diff(diff, color=use_color, max_entries=max_entries)))

    if _HAS_ALLURE:
        mode = getattr(item.config, "_assertpy2_allure_mode", "diff")
        allure_max_entries = getattr(item.config, "_assertpy2_diff_max", 50)
        with contextlib.suppress(Exception):
            _attach_allure(actual, expected, diff, mode=mode, max_entries=allure_max_entries)


def _format_diff(diff, *, color: bool = False, max_entries: int = 50) -> str:
    entries = getattr(diff, "entries", None)
    if not entries:
        return str(diff)
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

    if kind in {"sequence", "string", "dict", "dataclass", "namedtuple", "model"}:
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
    elif kind == "match":
        lines.extend(
            f"  {cyan}{entry.path}{reset}: expected {entry.expected}, but was {red}{entry.actual!r}{reset}"
            for entry in visible
        )
    elif kind in {"set", "contains"}:
        extra = [e for e in visible if e.path == "extra"]
        missing = [e for e in visible if e.path == "missing"]
        if extra:
            items = ", ".join(repr(e.actual) for e in extra)
            lines.append(f"  {red}extra:   {{{items}}}{reset}")
        if missing:
            items = ", ".join(repr(e.expected) for e in missing)
            lines.append(f"  {green}missing: {{{items}}}{reset}")
    else:
        for entry in visible:
            path = entry.path
            lines.append(f"  {path}:")
            lines.append(f"    {red}- {entry.actual!r}{reset}")
            lines.append(f"    {green}+ {entry.expected!r}{reset}")

    if truncated:
        lines.append(f"  ... and {truncated} more entries")

    return "\n".join(lines)


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


def _diff_to_json(diff, max_entries=50):
    entries = getattr(diff, "entries", None)
    if not entries:
        return None
    kind = getattr(diff, "kind", "unknown")
    visible = entries[:max_entries] if max_entries > 0 and len(entries) > max_entries else entries
    truncated = len(entries) - len(visible)
    items = [
        {
            "path": str(getattr(entry, "path", "")),
            "actual": _json_safe(getattr(entry, "actual", None)),
            "expected": _json_safe(getattr(entry, "expected", None)),
        }
        for entry in visible
    ]
    payload = {"format": 2, "kind": kind, "entries": items}
    if truncated:
        payload["truncated"] = truncated
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


def _attach_allure(actual, expected, diff, *, mode="diff", max_entries=50):
    if mode == "off":
        return
    if mode == "full" and (actual is not None or expected is not None):
        data = {"format": 2}
        if actual is not None:
            data["actual"] = _json_safe(actual)
        if expected is not None:
            data["expected"] = _json_safe(expected)
        allure.attach(
            body=json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False),
            name="AssertionFailure",
            attachment_type=allure.attachment_type.JSON,
        )
    if diff is not None:
        diff_json = _diff_to_json(diff, max_entries=max_entries)
        if diff_json is not None:
            allure.attach(
                body=diff_json,
                name="Structured Diff",
                attachment_type=allure.attachment_type.JSON,
            )
