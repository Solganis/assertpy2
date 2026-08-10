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
from ._engine._path import _ROOT
from .errors import _diff_side, _diff_sides, _json_safe, _render_diff

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

# node ids that reached each snapshot key, shipped by xdist workers and unioned on the controller
_controller_accesses: dict = {}


def pytest_runtest_setup(item):
    """Name the running test, so a snapshot key reached by two of them can be told from a helper that
    snapshots twice inside one."""
    _snapshot._CURRENT_NODE = item.nodeid


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
    accesses = getattr(node, "workeroutput", {}).get("assertpy2_accesses")
    if accesses:
        # unioned here rather than judged in the worker: two parametrised cases on two workers are one
        # node id each locally, so no worker sees a second and only the union does
        for snapname, key, nodes, site in accesses:
            _controller_accesses.setdefault((snapname, key), set()).update(nodes)
            _snapshot._ACCESS_SITES.setdefault((snapname, key), site)


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


def _warn_on_reused_snapshot_keys(session) -> None:
    """Report every reused snapshot key, with the number of tests that reached it.

    `assertpy2.snapshot._record_access()` raises the warning that is worth reading, from inside the
    assertion: pytest attributes it to a nodeid, puts it in the normal summary, and under ``-W error``
    fails that test rather than this hook.  What it cannot do is count.  It fires when the second test
    arrives, with more still to come, and it never sees the other xdist workers - parametrised cases
    split across them are one access each, so no worker sees a second reach and only the union does.

    The count therefore lives here, where every access has been collected, and this runs for every
    reused key rather than only for the ones no worker reported.  Two messages about one key is the
    price: the first says where it happened, this one says how big it is.
    """
    totals: dict = {key: set(nodes) for key, nodes in _snapshot._ACCESS_NODES.items()}
    for key, nodes in _controller_accesses.items():
        totals.setdefault(key, set()).update(nodes)
    _snapshot._ACCESS_NODES.clear()
    _controller_accesses.clear()
    _snapshot._WARNED.clear()
    for (snapname, key), nodes in sorted(totals.items()):
        if len(nodes) < 2:
            continue
        message = _snapshot._reuse_message(snapname, key, _snapshot._ACCESS_SITES.get((snapname, key), ""), len(nodes))
        try:
            warnings.warn(message, _snapshot.SnapshotKeyReusedWarning, stacklevel=1)
        except _snapshot.SnapshotKeyReusedWarning:
            _fail_on_reused_key(session, message)
    _snapshot._ACCESS_SITES.clear()


def _fail_on_reused_key(session, message: str) -> None:
    """Turn an escalated sweep warning into a failed run instead of a broken hook.

    An ``error`` entry in the warning filters raises here rather than at a test, and an exception out
    of a session-finish hook is an INTERNALERROR with this module's traceback in it - which buries the
    message the reader needs under a stack that points at the wrong place.  Print it and go red.
    """
    # only a run that otherwise succeeded. this hook is reached from a ``finally``, so it also runs
    # after Ctrl-C, an internal error and a usage error, and each of those carries an exit code that
    # says more than "tests failed". overwriting one would report a run that never finished as one
    # that did. anything already non-zero is red for its own reason and needs nothing from here
    if session.exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:  # pragma: no cover - the terminal reporter is always present under pytest
        return
    reporter.write_line("")
    reporter.write_line(f"ERROR: {message}", red=True)


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    if hasattr(config, "workeroutput"):  # xdist worker: ship recorded work to the controller, defer the rest
        config.workeroutput["assertpy2_touched"] = [list(item) for item in _snapshot._TOUCHED]
        config.workeroutput["assertpy2_inline"] = [list(record) for record in _inline._RECORDS]
        config.workeroutput["assertpy2_retried"] = [list(row) for row in _retried]
        config.workeroutput["assertpy2_accesses"] = [
            [snapname, key, sorted(nodes), _snapshot._ACCESS_SITES.get((snapname, key), "")]
            for (snapname, key), nodes in _snapshot._ACCESS_NODES.items()
        ]
        return
    # controller / single process: apply inline edits (workers' plus any recorded here) into source
    _report_retries(config)
    _warn_on_reused_snapshot_keys(session)
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

    # what the report can show is what the assertion named, and "the attribute is not None" stopped
    # being able to answer that on either side. `actual` is filled on every failure now, so it would
    # put a block under all of them; `expected` was never able to tell "compared against None" from
    # "no expected at all", and lost the line on both
    outcome = getattr(exc, "_outcome", None)
    if outcome is None:
        # built by hand, by `eventually()` or by a snapshot re-wrap: the values are all there is to go on
        named_actual, named_expected = actual is not None, expected is not None
    else:
        named_actual, named_expected = outcome.actual_provided, outcome.has_expected

    # the cheap exit for a failure with nothing to add to its own message, which is most of them
    if not (named_actual or named_expected) and diff is None and trace is None:
        return

    if named_actual or named_expected:
        # capped like the diff rows: this section is read on a terminal, and the untouched values stay
        # on the exception for anything that wants them
        lines = []
        if named_actual and named_expected:
            # windowed as a pair: capping each side on its own hides the difference when it sits past
            # the cap, and prints two values that look identical under a heading saying they are not
            left, right = _diff_sides(actual, expected)
            lines.append(f"  actual:   {left}")
            lines.append(f"  expected: {right}")
        elif named_actual:
            lines.append(f"  actual:   {_diff_side(actual)}")
        else:
            lines.append(f"  expected: {_diff_side(expected)}")
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
            _attach_allure(
                actual,
                expected,
                diff,
                trace=trace,
                mode=mode,
                max_entries=allure_max_entries,
                named_actual=named_actual,
                named_expected=named_expected,
            )


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
        entries = _sub_diff_entries(previous.value, current.value, _ROOT)
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


def _entry_to_json(entry):
    """One diff entry, with the side that had no value at all named rather than left to inference.

    ``format`` 2 wrote ``null`` for both an absent key and a key whose value really is ``None``, so a
    consumer of the attachment could not tell "this field is missing" from "this field is null" - the
    same ambiguity `assertpy2.errors.DiffEntry.absent` exists to remove inside the library.  The key
    appears only where a side is genuinely absent, so an entry that simply holds ``None`` is
    unchanged, and the format is bumped because the meaning of a bare ``null`` is what changed.
    """
    item = {
        "path": str(getattr(entry, "path", "")),
        "actual": _json_safe(getattr(entry, "actual", None)),
        "expected": _json_safe(getattr(entry, "expected", None)),
    }
    absent = getattr(entry, "absent", None)
    if absent is not None:
        item["absent"] = absent
    steps = getattr(entry, "steps", ())
    if steps:
        # `path` is written for a person and cannot be read back: a mapping key goes through `str()`, so
        # `{3: ...}` and `{"3": ...}` render alike.  A consumer that wants to walk back into the payload
        # needs the keys themselves, which is what these are.  Absent where there is no location to
        # give: the root, and a containment entry whose path is a label
        item["steps"] = [_step_to_json(step) for step in steps]
    return item


def _step_to_json(step):
    """One hop of a diff entry's machine-readable path.

    ``side`` appears only where it means something: a sequence whose two sides have shifted apart, where
    an index without a side names two different elements.
    """
    item = {"kind": step.kind, "value": _json_safe(step.value)}
    if step.side is not None:
        item["side"] = step.side
    return item


def _diff_to_json(diff, max_entries=50):
    entries = getattr(diff, "entries", None)
    if not entries:
        return None
    kind = getattr(diff, "kind", "unknown")
    visible = entries[:max_entries] if max_entries > 0 and len(entries) > max_entries else entries
    truncated = len(entries) - len(visible)
    items = [_entry_to_json(entry) for entry in visible]
    payload = {"format": 4, "kind": kind, "entries": items}
    if truncated:
        payload["truncated"] = truncated
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


def _attach_allure(actual, expected, diff, *, named_actual, named_expected, trace=None, mode="diff", max_entries=50):
    # the two flags carry the terminal section's decision, so an Allure run and a pytest report agree
    # on which values the assertion named. Required rather than defaulted: a caller that reads them
    # off the values instead is the reading this phase removed
    if mode == "off":
        return
    if mode == "full" and (named_actual or named_expected):
        data = {"format": 2}
        if named_actual:
            data["actual"] = _json_safe(actual)
        if named_expected:
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
