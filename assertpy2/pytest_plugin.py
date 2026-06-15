from __future__ import annotations

import contextlib
import json
import warnings

import pytest

try:
    import allure  # ty: ignore[unresolved-import]  # optional dependency

    _HAS_ALLURE = True  # pragma: no cover - only when allure-pytest is installed
except ImportError:
    _HAS_ALLURE = False

_ALLURE_MODES = {"off", "diff", "full"}


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
            f"assertpy2_allure={mode!r} is not a valid mode ({', '.join(sorted(_ALLURE_MODES))}), falling back to 'diff'",
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
        with contextlib.suppress(Exception):
            _attach_allure(actual, expected, diff, mode=mode)


_RED = "\033[31m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_RESET = "\033[0m"


def _format_diff(diff, *, color: bool = False, max_entries: int = 50) -> str:
    entries = getattr(diff, "entries", None)
    if not entries:
        return str(diff)
    kind = getattr(diff, "kind", "unknown")

    red = _RED if color else ""
    green = _GREEN if color else ""
    cyan = _CYAN if color else ""
    reset = _RESET if color else ""

    truncated = 0
    visible = entries
    if max_entries > 0 and len(entries) > max_entries:
        truncated = len(entries) - max_entries
        visible = entries[:max_entries]

    lines = [f"{cyan}diff ({kind}):{reset}"]

    if kind in {"sequence", "string", "dict", "dataclass", "namedtuple"}:
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


def _diff_to_json(diff):
    entries = getattr(diff, "entries", None)
    if not entries:
        return None
    kind = getattr(diff, "kind", "unknown")
    items = []
    for entry in entries:
        items.append(
            {
                "path": str(getattr(entry, "path", "")),
                "actual": repr(getattr(entry, "actual", None)),
                "expected": repr(getattr(entry, "expected", None)),
            }
        )
    return json.dumps({"kind": kind, "entries": items}, ensure_ascii=False, indent=2)


def _attach_allure(actual, expected, diff, *, mode="diff"):
    if mode == "off":
        return
    if mode == "full" and (actual is not None or expected is not None):
        data = {}
        if actual is not None:
            data["actual"] = repr(actual)
        if expected is not None:
            data["expected"] = repr(expected)
        allure.attach(
            body=json.dumps(data, ensure_ascii=False, indent=2),
            name="AssertionFailure",
            attachment_type=allure.attachment_type.JSON,
        )
    if diff is not None:
        diff_json = _diff_to_json(diff)
        if diff_json is not None:
            allure.attach(
                body=diff_json,
                name="Structured Diff",
                attachment_type=allure.attachment_type.JSON,
            )
