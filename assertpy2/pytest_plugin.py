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

    if diff is not None:
        report.sections.append(("Structured Diff", str(diff)))

    if _HAS_ALLURE:
        mode = getattr(item.config, "_assertpy2_allure_mode", "diff")
        with contextlib.suppress(Exception):
            _attach_allure(actual, expected, diff, mode=mode)


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
