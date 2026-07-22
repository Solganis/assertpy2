from __future__ import annotations

import contextlib
import json
import warnings
from itertools import pairwise
from typing import Final

import pytest

from . import _inline, _satisfies, async_assertions, errors
from . import snapshot as _snapshot
from ._engine._diff import _sub_diff_entries
from .errors import _json_safe, _render_diff

try:
    import allure  # ty: ignore[unresolved-import]  # optional dependency

    _HAS_ALLURE = True  # pragma: no cover - only when allure-pytest is installed
except ImportError:
    _HAS_ALLURE = False

_ALLURE_MODES: Final = frozenset({"off", "diff", "full"})


def pytest_addoption(parser):
    parser.addoption(
        "--assertpy2-snapshot-update",
        action="store_true",
        default=False,
        help="Overwrite failing assertpy2 snapshots with the current values instead of failing",
    )
    parser.addoption(
        "--assertpy2-vacuous",
        action="store_true",
        default=False,
        help="Warn when a universal assertion passes over an empty value, having checked nothing",
    )
    parser.addoption(
        "--assertpy2-snapshot-ci",
        action="store_true",
        default=False,
        help="Fail instead of creating a missing assertpy2 snapshot (auto-enabled when a CI env is detected)",
    )
    parser.addoption(
        "--assertpy2-snapshot-no-ci",
        action="store_true",
        default=False,
        help="Disable CI mode / its autodetection, allowing missing snapshots to be created",
    )
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
    parser.addini(
        "assertpy2_poll_report",
        help="Name polls that converged this close to their deadline: off, or a fraction (default 0.7)",
        default="0.7",
    )


def _poll_threshold(raw: object) -> float | None:
    """Parse the near-timeout reporting bar: ``off`` silences the report, a fraction moves it.

    A slow CI box converges late on every poll, where the default bar turns a signal into a line of
    noise per run.  ``None`` means the report is off, and collection is skipped with it.
    """
    if str(raw).strip().lower() == "off":
        return None
    try:
        value = float(raw)  # ty: ignore[invalid-argument-type]  # guarded by the except below
    except (ValueError, TypeError):
        value = 0.0
    if not 0.0 < value <= 1.0:
        warnings.warn(
            f"assertpy2_poll_report={raw!r} is not 'off' or a fraction in (0, 1], falling back to 0.7",
            stacklevel=1,
        )
        return 0.7
    return value


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
    # under pytest the plugin renders the diff as its own colored report section, so keep it out of the
    # message to avoid showing it twice; off pytest the message stays the only carrier. save/restore the
    # prior value (rather than forcing True back) so tests that drive these hooks directly stay balanced
    config._assertpy2_prev_diff_in_message = errors._RENDER_DIFF_IN_MESSAGE
    errors._RENDER_DIFF_IN_MESSAGE = False
    config._assertpy2_poll_threshold = _poll_threshold(config.getini("assertpy2_poll_report"))
    # nothing reads the samples once the report is off, so stop paying for them at the poll site
    async_assertions._COLLECT_RETRIES = config._assertpy2_poll_threshold is not None
    # save/restore rather than force False back: the environment variable may have turned the guard on
    # before import, and unconfigure must not silently undo that
    config._assertpy2_prev_vacuous = _satisfies._VACUOUS_GUARD
    if config.getoption("assertpy2_vacuous"):
        _satisfies._VACUOUS_GUARD = True
    if config.getoption("assertpy2_snapshot_update"):
        _snapshot._UPDATE_ALL = True
    if config.getoption("assertpy2_snapshot_ci"):
        _snapshot._CI_MODE = True
    elif config.getoption("assertpy2_snapshot_no_ci"):
        _snapshot._CI_MODE = False


def pytest_unconfigure(config):
    errors._RENDER_DIFF_IN_MESSAGE = getattr(config, "_assertpy2_prev_diff_in_message", True)
    async_assertions._COLLECT_RETRIES = False
    async_assertions._RETRIES.clear()
    _satisfies._VACUOUS_GUARD = getattr(config, "_assertpy2_prev_vacuous", _satisfies._env_enabled())
    if config.getoption("assertpy2_snapshot_update"):
        _snapshot._UPDATE_ALL = False
    if config.getoption("assertpy2_snapshot_ci") or config.getoption("assertpy2_snapshot_no_ci"):
        _snapshot._CI_MODE = None


# snapshots touched by xdist workers, collected on the controller as each worker finishes
_controller_touched: set = set()

# inline-snapshot source edits recorded by xdist workers, applied on the controller (workers must not
# rewrite shared source files in parallel)
_controller_inline: list = []


@pytest.hookimpl(optionalhook=True)  # xdist-provided hook: silently ignored when xdist is not installed
def pytest_testnodedown(node, error):
    """xdist controller hook: collect the touched snapshots and inline edits each worker shipped."""
    touched = getattr(node, "workeroutput", {}).get("assertpy2_touched")
    if touched:
        _controller_touched.update(tuple(item) for item in touched)
    retried = getattr(node, "workeroutput", {}).get("assertpy2_retried")
    if retried:
        _retried.extend(tuple(row) for row in retried)
    inline = getattr(node, "workeroutput", {}).get("assertpy2_inline")
    if inline:
        _controller_inline.extend(tuple(record) for record in inline)


def _is_full_run(config) -> bool:
    """Whether the run selected all tests (no ``-k`` / ``-m`` / ``--lf`` / ``--ff`` and no nodeid
    selection).  Orphan detection is only reliable on a full run, since a deselected or nodeid-selected
    live test would otherwise look obsolete."""
    opt = config.option
    if any("::" in str(arg) for arg in getattr(opt, "file_or_dir", None) or ()):
        return False  # a nodeid selection (path::test) runs only a subset of a file's tests
    return not (
        getattr(opt, "keyword", "")
        or getattr(opt, "markexpr", "")
        or getattr(opt, "last_failed", False)
        or getattr(opt, "failed_first", False)
    )


_retried: list[tuple[str, int, float, float]] = []


def _drain_retries(nodeid: str) -> None:
    """Move any retried polls this test performed onto the run-level list, tagged with the test."""
    for attempts, elapsed, budget in async_assertions._RETRIES:
        _retried.append((nodeid, attempts, elapsed, budget))
    async_assertions._RETRIES.clear()


def _report_retries(config) -> None:
    """Name the polls that converged against their deadline: that run passed, the next one may not.

    Retrying is what ``eventually()`` is for, so a retry on its own says nothing.  Spending most of the
    budget before converging is what turns into a failure on a slower machine.
    """
    threshold = getattr(config, "_assertpy2_poll_threshold", 0.7)
    if threshold is None:
        return
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:  # pragma: no cover - the terminal reporter is always present under pytest
        return
    late = [row for row in _retried if row[3] and row[2] / row[3] >= threshold]
    if not late:
        return
    reporter.write_line("")
    reporter.write_line("assertpy2 polls that nearly timed out:")
    for nodeid, attempts, elapsed, budget in late:
        reporter.write_line(
            f"  {nodeid}: converged on attempt {attempts} at {elapsed:.2f}s of {budget:.1f}s"
            f" ({elapsed / budget:.0%} of the budget)"
        )


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    if hasattr(config, "workeroutput"):  # xdist worker: ship recorded work to the controller, defer the rest
        config.workeroutput["assertpy2_touched"] = [list(item) for item in _snapshot._TOUCHED]
        config.workeroutput["assertpy2_inline"] = [list(record) for record in _inline._RECORDS]
        config.workeroutput["assertpy2_retried"] = [list(row) for row in _retried]
        return
    # controller / single process: apply inline edits (workers' plus any recorded here) into source
    _report_retries(config)
    _inline._RECORDS.extend(_controller_inline)
    _controller_inline.clear()
    _inline.apply_inline_records()
    touched = set(_snapshot._TOUCHED) | _controller_touched
    _controller_touched.clear()
    if not touched or not _is_full_run(config):
        # on a subset run the touched set is incomplete, so orphan detection is unreliable: skip both
        # pruning (which would delete a live but un-run sibling) and reporting (a false positive)
        return
    sub_orphans, whole_orphans = _snapshot._find_orphans(touched)
    if not sub_orphans and not whole_orphans:
        return
    pruned = []
    # prune obsolete sub-snaps only under update mode; whole files are always report-only
    if sub_orphans and _snapshot._update_enabled():
        _snapshot._prune_sub_key_orphans(sub_orphans)
        pruned, sub_orphans = sub_orphans, []
    _report_snapshot_orphans(config, sub_orphans, whole_orphans, pruned)


def _report_snapshot_orphans(config, sub_orphans, whole_orphans, pruned):
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:  # pragma: no cover - the terminal reporter is always present under pytest
        return
    lines = [f"removed obsolete snapshot: {snap}::{key}" for snap, key in pruned]
    lines += [
        f"obsolete snapshot (run --assertpy2-snapshot-update on a full run to remove): {snap}::{key}"
        for snap, key in sub_orphans
    ]
    lines += [f"obsolete snapshot file (delete manually if its test is gone): {snap}" for snap in whole_orphans]
    reporter.write_line("")
    reporter.write_line("assertpy2 snapshots:")
    for line in lines:
        reporter.write_line(f"  {line}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    # every phase, not just "call": a fixture that polls in teardown runs after the call report, so
    # draining only there would tag its retries with the next test that happens to run
    _drain_retries(report.nodeid)
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
    trace = getattr(exc, "trace", None)

    if actual is None and expected is None and diff is None and trace is None:
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

    if trace is not None and getattr(item.config, "_assertpy2_diff_enabled", True):
        report.sections.append(("Polling Trace", _format_trace(trace)))

    if _HAS_ALLURE:
        mode = getattr(item.config, "_assertpy2_allure_mode", "diff")
        allure_max_entries = getattr(item.config, "_assertpy2_diff_max", 50)
        with contextlib.suppress(Exception):
            _attach_allure(actual, expected, diff, trace=trace, mode=mode, max_entries=allure_max_entries)


def _format_diff(diff, *, color: bool = False, max_entries: int = 50) -> str:
    return _render_diff(diff, color=color, max_entries=max_entries)


def _format_trace(trace) -> str:
    """Render a `PollTrace` as a compact per-poll timeline for the terminal report section."""
    lines = [f"polled {trace.total_polls} times over {trace.elapsed:.1f}s; {trace.summary}"]
    if trace.dropped:
        lines.append(f"  ... {trace.dropped} middle samples dropped")
    for sample in trace.samples:
        repeats = f" x{sample.repeats}" if sample.repeats > 1 else ""
        lines.append(f"  t=+{sample.elapsed:.1f}s {sample.outcome}{repeats}: {sample.detail}")
    return "\n".join(lines)


def _trace_to_json(trace):
    """Serialize a `PollTrace` to the typed attachment JSON, with diffs between distinct samples."""
    samples = []
    for sample in trace.samples:
        item = {"t": round(sample.elapsed, 3), "outcome": sample.outcome, "detail": sample.detail}
        if sample.value is not None:
            item["value"] = sample.value
        if sample.repeats > 1:
            item["repeats"] = sample.repeats
        samples.append(item)
    deltas = []
    fails = [sample for sample in trace.samples if sample.outcome == "fail"]
    for previous, current in pairwise(fails):
        if current.value == previous.value:
            continue
        entries = _sub_diff_entries(previous.value, current.value, "")
        if entries is None:
            entries_json = [{"path": ".", "actual": previous.value, "expected": current.value}]
        else:
            entries_json = [
                {"path": entry.path, "actual": entry.actual, "expected": entry.expected} for entry in entries
            ]
        deltas.append(
            {"from_t": round(previous.elapsed, 3), "to_t": round(current.elapsed, 3), "entries": entries_json}
        )
    payload = {
        "format": 2,
        "kind": "polling-trace",
        "total_polls": trace.total_polls,
        "elapsed": round(trace.elapsed, 3),
        "summary": trace.summary,
        "samples": samples,
    }
    if trace.dropped:
        payload["dropped"] = trace.dropped
    if deltas:
        payload["deltas"] = deltas
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


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


def _attach_allure(actual, expected, diff, *, trace=None, mode="diff", max_entries=50):
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
    if trace is not None:
        allure.attach(
            body=_trace_to_json(trace),
            name="Polling Trace",
            attachment_type=allure.attachment_type.JSON,
        )
