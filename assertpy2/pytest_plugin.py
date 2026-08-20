from __future__ import annotations

import contextlib
import json
import warnings
from itertools import pairwise
from typing import Final

import pytest

from . import _clustering, _dangling, _inline, _satisfies, async_assertions, errors
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
        "--assertpy2-dangling",
        action="store_true",
        default=False,
        help="Warn when assert_that() is used as a statement without asserting anything",
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
        "assertpy2_dangling",
        help="Warn about assert_that() statements that assert nothing: off (default), on",
        default="off",
    )
    parser.addini(
        "assertpy2_dangling_entries",
        help="Names of your own assert_that wrappers the dangling check should also read as builders",
        type="args",
        default=[],
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
        "assertpy2_failure_clusters",
        help="Group failures sharing one difference: off (default), or the failing tests a cluster must hold",
        default="off",
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


def _cluster_minimum(raw: object) -> int | None:
    """Parse how many failing tests a cluster must hold: ``off`` silences the summary, a count moves it.

    ``None`` means the summary is off, and the per-failure recording is skipped with it, so a run that
    does not want the summary pays nothing for it.

    A count rather than a share of the run, which was tried first and measured strictly worse: under a
    share every additional cause raises the bar for all the others, so a run splitting cleanly into
    five causes of eight printed nothing at all.
    """
    if str(raw).strip().lower() == "off":
        return None
    try:
        value = int(raw)  # ty: ignore[invalid-argument-type]  # guarded by the except below
    except (ValueError, TypeError):
        value = 0
    if value < 2:
        warnings.warn(
            f"assertpy2_failure_clusters={raw!r} is not 'off' or a count of 2 or more, "
            f"falling back to {_clustering.MINIMUM_SIZE}",
            stacklevel=1,
        )
        return _clustering.MINIMUM_SIZE
    return value


def _dangling_enabled(config) -> bool:
    """Whether the dangling check runs, from the flag or the ini setting.

    The flag wins: a run that asks for the check on the command line gets it whatever the file says,
    which is how somebody tries it once without editing a config they share with everybody else.
    """
    if config.getoption("assertpy2_dangling"):
        return True
    setting = str(config.getini("assertpy2_dangling")).strip().lower()
    if setting not in {"on", "off"}:
        warnings.warn(
            f"assertpy2_dangling={setting!r} is not 'on' or 'off', falling back to 'off'",
            stacklevel=1,
        )
        return False
    return setting == "on"


def _dangling_entries(config) -> frozenset[str]:
    """The project's own wrapper names the dangling check should treat as builder factories.

    Only a plain name can bind through an import, so anything else is dropped with a warning rather
    than kept to match nothing: `helpers.check` in a config file looks like it works, and a check that
    silently covers none of what it was told to cover is worse than one that is off.
    """
    names = {str(name).strip() for name in config.getini("assertpy2_dangling_entries") or ()}
    usable = {name for name in names if name.isidentifier()}
    if rejected := sorted(names - usable):
        warnings.warn(
            f"assertpy2_dangling_entries: {', '.join(repr(name) for name in rejected)} "
            f"{'is not a plain name' if len(rejected) == 1 else 'are not plain names'} "
            f"and cannot be matched, ignoring",
            stacklevel=1,
        )
    return frozenset(usable)


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
    config._assertpy2_dangling_enabled = _dangling_enabled(config)
    config._assertpy2_dangling_entries = _dangling_entries(config)
    config._assertpy2_diff_enabled = config.getini("assertpy2_diff") != "off"
    try:
        config._assertpy2_diff_max = int(config.getini("assertpy2_diff_max_entries"))
    except (ValueError, TypeError):
        config._assertpy2_diff_max = 50
    # under pytest the plugin renders the diff as its own report section, so it stays out of the message; the prior
    # value is restored rather than forced back, so tests driving these hooks stay balanced
    config._assertpy2_prev_diff_in_message = errors._RENDER_DIFF_IN_MESSAGE
    errors._RENDER_DIFF_IN_MESSAGE = False
    config._assertpy2_cluster_minimum = _cluster_minimum(config.getini("assertpy2_failure_clusters"))
    _session_config[0] = config
    config._assertpy2_failures = []
    config._assertpy2_failure_count = 0
    config._assertpy2_poll_threshold = _poll_threshold(config.getini("assertpy2_poll_report"))
    # nothing reads the samples once the report is off, so stop paying for them at the poll site
    async_assertions._COLLECT_RETRIES = config._assertpy2_poll_threshold is not None
    # save and restore rather than force back: the environment variable may have turned the guard on before import
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
    # module-level, so a second session in the same process would open with the first one's failures counted; these
    # are consumed by a hook that may not run
    _controller_failures.clear()
    _controller_failure_count[0] = 0
    _controller_lost_workers[0] = 0
    _controller_unreadable_workers[0] = 0
    _controller_collect_errors[0] = 0
    _session_config[0] = None
    _satisfies._VACUOUS_GUARD = getattr(config, "_assertpy2_prev_vacuous", _satisfies._env_enabled())
    if config.getoption("assertpy2_snapshot_update"):
        _snapshot._UPDATE_ALL = False
    if config.getoption("assertpy2_snapshot_ci") or config.getoption("assertpy2_snapshot_no_ci"):
        _snapshot._CI_MODE = None


# snapshots touched by xdist workers, collected on the controller as each worker finishes
_controller_touched: set = set()

# workers must not rewrite shared source files in parallel
_controller_inline: list = []

# node ids that reached each snapshot key, shipped by xdist workers and unioned on the controller
_controller_accesses: dict = {}

# the summary is written on the controller, and a worker's own config is not the controller's
_controller_failures: list = []
_controller_failure_count: list = [0]
_controller_lost_workers: list = [0]
_controller_unreadable_workers: list = [0]
_controller_collect_errors: list = [0]

# the session's config, for the one hook that is handed a report and no way back to it
_session_config: list = [None]


def pytest_collection_modifyitems(session, config, items):
    """Read every collected test file once and record the statements that assert nothing.

    Collection rather than runtime: the check is static (see `_dangling`), so a selected subset
    (`-k`, `--lf`) is the subset that gets read, and each path is read once however many items it
    contributed.  The findings are only *recorded* here; they are reported from `runtest_setup`,
    because a warning raised out of a collection hook under `-W error` aborts pytest with an
    INTERNALERROR instead of failing anything a reader can act on.
    """
    config._assertpy2_dangling = {}
    if not getattr(config, "_assertpy2_dangling_enabled", False):
        return
    for item in items:
        path = getattr(item, "path", None)
        if path is None or path in config._assertpy2_dangling:  # pragma: no cover - items carry a path
            continue
        try:
            source = path.read_text(encoding="utf-8")
            entries = getattr(config, "_assertpy2_dangling_entries", frozenset())
            config._assertpy2_dangling[path] = _dangling.findings(source, str(path), entries)
        except (OSError, SyntaxError):  # pragma: no cover - pytest imported the module, so it read and parsed
            config._assertpy2_dangling[path] = []


def _item_scope(item) -> tuple[str, ...]:
    """The test's own scope chain, matching what the static pass recorded: ``("TestOne", "test_same")``.

    Read from `__qualname__` rather than assembled from `item.cls`, which names only the innermost
    class: a method of a class nested in another class is `TestOuter.TestInner.test_it` to the source
    and only `TestInner.test_it` to that attribute, and the two chains then failed to line up.

    A function name alone is worse than either: two classes in one file may each define `test_same`,
    and a finding matched by name went to whichever ran first.
    """
    qualname = getattr(getattr(item, "function", None), "__qualname__", None)
    if not qualname:
        return ()
    return tuple(part for part in qualname.split(".") if part != "<locals>")


def _report_dangling(item):
    """Warn once per file, on the first test to run from it, so pytest attributes it to that node.

    `warn_explicit` rather than `warn`: the location that matters is the offending statement, not
    this line, and a reader jumping to the warning should land in their own test file.
    """
    config = getattr(item, "config", None)  # a hook driven directly in a test carries no config
    recorded = getattr(config, "_assertpy2_dangling", {})
    found = recorded.get(getattr(item, "path", None))
    if not found:
        return
    here = _item_scope(item)
    # a finding outside any def has no test to attach to, so the first item takes it
    mine = [one for one in found if not one.scope or (here and one.scope[: len(here)] == here)]
    if not mine:
        return
    recorded[item.path] = [one for one in recorded[item.path] if one not in mine]
    # one warning for the whole test: under `-W error` the first leaves this function as an exception, so a second
    # would never be reported
    first, rest = mine[0], mine[1:]
    message = first.message
    if rest:
        lines = ", ".join(str(one.lineno) for one in rest)
        message = f"{message} (and {len(rest)} more in this test, at line{'' if len(rest) == 1 else 's'} {lines})"
    warnings.warn_explicit(message, errors.DanglingAssertionWarning, first.path, first.lineno)


def pytest_runtest_setup(item):
    """Name the running test, so a snapshot key reached by two of them can be told from a helper that
    snapshots twice inside one."""
    _snapshot._CURRENT_NODE = item.nodeid
    _report_dangling(item)


def pytest_collectreport(report):
    """Note a collection that failed, which is red and never reaches a test report.

    `--continue-on-collection-errors` runs the rest of the suite, so pytest ends with `3 failed, 1 error`
    while the summary saw only the three and said `3 of 3`.  Counted on its own line rather than into the
    denominator, because a collector is not a test and `3 of 4 failing tests` would name a fourth test
    that does not exist.  Without that flag the run stops and no summary is written, so this costs nothing in
    the ordinary case.

    The report arrives without its config, and this hook is the only place a collection failure is
    visible, which is what the session-level reference is for.
    """
    config = _session_config[0]
    if config is None or not report.failed or hasattr(config, "workeroutput"):
        # not on a worker: every worker collects the whole suite, so counting there turned one broken module into one
        # red result per worker
        return
    if getattr(config, "_assertpy2_cluster_minimum", None) is not None:
        _controller_collect_errors[0] += 1


@pytest.hookimpl(optionalhook=True)  # xdist-provided hook: silently ignored when xdist is not installed
def pytest_testnodedown(node, error):
    """xdist controller hook: collect the touched snapshots and inline edits each worker shipped.

    ``error`` is set when the worker died rather than finished.  Then it never ran its `sessionfinish`,
    so whatever it had recorded never left it, and the cluster summary would otherwise report a share
    of the failures it happened to receive as though that were the whole run.
    """
    if error is not None:
        _controller_lost_workers[0] += 1
    _collect_worker_failures(node, died=error is not None)
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
        # unioned here rather than judged in the worker: two parametrised cases on two workers are one node id each
        # locally
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
    # only a run that otherwise succeeded: this hook is reached from a `finally`, so Ctrl-C and an internal error
    # land here too
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
        config.workeroutput["assertpy2_failures"] = [
            [nodeid, [_observation_to_wire(one) for one in found]]
            for nodeid, found in getattr(config, "_assertpy2_failures", [])
        ]
        config.workeroutput["assertpy2_failure_count"] = getattr(config, "_assertpy2_failure_count", 0)
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
        # on a subset run the touched set is incomplete, so pruning would delete a live sibling and reporting would
        # be a false positive
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


def _refuse(value: object) -> bool:
    """Raise, from inside a comprehension's condition, where a plain `raise` cannot go."""
    raise TypeError(value)


def _collect_worker_failures(node, died: bool = False) -> None:
    """Take one worker's recorded failures, or leave the worker counted as lost.

    Everything here came off the wire, and a controller running one version of this library against a
    worker running another is a real installation.  A row that does not unpack must not take down a hook
    that pytest answers with INTERNALERROR, and it must not be silently dropped either: the summary
    reports what share of the run it explains, so a worker whose failures went missing is the same
    situation as a worker that died.

    Unreadable is counted apart from dead (``died``), because the two are different claims about the run
    and a worker that finished must not be reported as having crashed.  A worker that already counted as
    dead is not looked at here at all: it has one thing wrong with it, not two.

    Both wire values are read outright rather than defaulted, which is what makes a worker that shipped
    neither unreadable rather than invisible.  This version ships both from every worker, summary on or
    off, so their absence is a worker that does not speak this protocol, and its failures are missing from
    the denominator: leaving that unsaid is how a run of twelve prints a confident `6 of 6`.

    Node ids are prefixed with the worker's own name because two workers can legitimately report the
    same test: `--dist=each` runs the whole suite on every worker.  Without the prefix the denominator
    counted both executions and the cluster counted one, and the summary reported a run half unexplained
    when nothing was unexplained at all.
    """
    if died:  # already counted, and a worker that never finished has nothing to have shipped
        return
    output = getattr(node, "workeroutput", {})
    worker = getattr(node, "gateway", None)
    prefix = getattr(worker, "id", "") or ""
    try:
        received = [
            (f"{prefix}::{nodeid}", [_observation_from_wire(one) for one in found])
            for nodeid, found in output["assertpy2_failures"]
            if isinstance(nodeid, str) or _refuse(nodeid)
        ]
        counted = output["assertpy2_failure_count"]
        # both halves or neither: rows without a count add members to a denominator they never raised.  Checked
        # rather than coerced, since `int()` would take `True` and `3.9`
        if isinstance(counted, bool) or not isinstance(counted, int):
            raise TypeError(counted)
        if counted < len({nodeid for nodeid, _ in received}):
            raise ValueError(counted)
    except Exception:  # pragma: no cover - the guard itself; a malformed payload is tested through it
        _controller_unreadable_workers[0] += 1
        return
    _controller_failures.extend(received)
    _controller_failure_count[0] += counted


def _observation_to_wire(one):
    """An observation as plain lists, which is all execnet can carry between worker and controller."""
    key = one.signature
    steps = [list(step) for step in key.steps]
    return [key.located, key.where, steps, key.label, list(key.values), one.actual, one.expected]


def _observation_from_wire(row):
    """Rebuild an observation the controller can group by, refusing anything it could not group by.

    Tuples again, not lists: the signature *is* the cluster key, so it has to hash, and a list inside it
    would raise the moment the controller tried to group anything a worker sent.

    Each field is checked rather than trusted, because a row of the right length can still hold the wrong
    thing.  A list where a value belongs unpacks happily and then raises out of the grouping, past the
    point where the worker could be reported as unreadable: the summary simply vanished, and the run said
    nothing about why.
    """
    located, where, steps, label, values, actual, expected = row
    if not (
        isinstance(located, bool)
        and all(isinstance(field, str) for field in (where, label, actual, expected))
        and all(isinstance(one, str) for one in values)
        and all(len(step) == 2 and all(isinstance(part, str) for part in step) for step in steps)
    ):
        raise TypeError(row)
    key = _clustering.Signature(located, where, tuple(tuple(step) for step in steps), label, tuple(values))
    if not _clustering.is_well_formed(key):
        raise ValueError(key)
    return _clustering.Observation(key, actual, expected)


def _record_for_clustering(config, nodeid, exc):
    """Note what one failure differed at, for the end-of-run summary.

    Counted even when it carries no diff, and even when there is no exception to ask - a strict xfail
    that passed is red and holds nothing - because the summary reports how much of the run it accounts
    for, and that is only meaningful against every failure.

    The failure's own diagnostic line keys the differences that have no location, so it is asked for
    here, while the values are still at hand.
    """
    if getattr(config, "_assertpy2_cluster_minimum", None) is None:
        return
    # a set of node ids rather than a counter: a retried test is reported failing once per attempt, and
    # counting attempts made the run look larger than it was
    failed = getattr(config, "_assertpy2_failed_ids", None)
    if failed is None:
        failed = config._assertpy2_failed_ids = set()
    failed.add(nodeid)
    config._assertpy2_failure_count = len(failed)
    try:
        # inside the guard, reads included: `diff` is our own attribute name on somebody else's
        # exception, and reading a property runs their code. One that raised took the whole run down
        # with INTERNALERROR, which is the cost of every line here being outside the net rather than in
        diff = getattr(exc, "diff", None)
        # the hint the failure already computed for its own message, rather than a second run of the
        # same analysis. `_outcome` is absent on a failure raised outside the fluent path
        outcome = getattr(exc, "_outcome", None)
        label = getattr(outcome, "hint", None)
        found = _clustering.observations_of(diff, label)
    except Exception:
        # a summary is a convenience and a report hook is not a place to raise from: pytest answers an
        # exception here with INTERNALERROR, which costs the reader the entire run's results
        return
    if found:
        config._assertpy2_failures.append((nodeid, found))


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Say in a line what the failures had in common, when enough of them had anything in common.

    This hook rather than `pytest_sessionfinish`, which runs before the tracebacks are printed and puts
    the summary above all of them.  Here it lands in the closing block, immediately above
    `short test summary info`.

    Not below it, and that is not a choice: the terminal reporter writes that list from the `finally`
    of its own wrapper around this hook, so every third-party implementation runs first.  Measured with
    a plain implementation, with `trylast`, and with a wrapper printing after its yield - all three
    land in the same place.
    """
    try:
        _write_cluster_summary(terminalreporter, config)
    except Exception as exc:  # pragma: no cover - the barrier itself; its parts are tested directly
        # a summary is a convenience and this hook is not a place to raise from: everything below is
        # optional, and taking a run's whole report down to print it would be the worst possible trade.
        # `Exception`, not `BaseException`: a Ctrl-C or a SystemExit through here still has to travel
        with contextlib.suppress(Exception):
            # the notice is itself suppressed rather than trusted: under `-W error` a warning raises,
            # which would put the barrier's own traceback in the report in place of the failure it caught
            warnings.warn(f"assertpy2 could not write its failure-cluster summary: {exc!r}", stacklevel=1)


def _write_cluster_summary(terminalreporter, config) -> None:
    """Build and print the summary, or return having printed nothing."""
    minimum = getattr(config, "_assertpy2_cluster_minimum", None)
    # a worker's failures arrive through `pytest_testnodedown`, and the controller runs none of its own
    total = getattr(config, "_assertpy2_failure_count", 0) + _controller_failure_count[0]
    recorded = [*getattr(config, "_assertpy2_failures", []), *_controller_failures]
    if minimum is None or total < minimum:
        return
    found = _clustering.clusters(recorded, total, minimum=minimum)
    lines = _clustering.render(
        found,
        total,
        _controller_lost_workers[0],
        _controller_unreadable_workers[0],
        minimum=minimum,
        collect_errors=_controller_collect_errors[0],
    )
    if not lines:
        return
    terminalreporter.write_line("")
    terminalreporter.write_line("assertpy2 failure clusters:")
    for line in lines:
        terminalreporter.write_line(f"  {line}")


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
    if not report.failed:
        return

    # ahead of the "call" and AssertionError gates, and without requiring an exception at all: the
    # summary counts against every red result, including an erroring fixture and a strict xpass
    exc = call.excinfo.value if call.excinfo is not None else None
    _record_for_clustering(item.config, report.nodeid, exc)

    if call.excinfo is None or report.when != "call" or not isinstance(exc, AssertionError):
        return

    try:
        _attach_report_sections(item, report, exc)
    except Exception:  # pragma: no cover - the barrier; everything under it is tested directly
        # the sections are built from attributes of somebody else's exception, and reading one runs
        # their code: an `AssertionError` subclass whose `diff` property raised took the whole run down
        # with INTERNALERROR. A failure that cannot be decorated is still a failure worth reporting
        return


def _attach_report_sections(item, report, exc) -> None:
    """Build the report sections a failure of ours can add to its own entry."""
    actual = getattr(exc, "actual", None)
    expected = getattr(exc, "expected", None)
    diff = getattr(exc, "diff", None)
    trace = getattr(exc, "trace", None)

    # read from the record, not from a test against `None`: `actual` is filled on every failure, and
    # `expected` cannot tell "compared against None" from "no expected value at all"
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
        # `path` is lossy, since a mapping key goes through `str()`, so a consumer that wants to walk
        # back into the payload needs the keys themselves.  Absent at the root, which has no location
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
