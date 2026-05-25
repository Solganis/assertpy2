import contextlib
from unittest.mock import MagicMock

import pytest

from assertpy2.errors import AssertionFailure, DiffEntry, DiffResult
from assertpy2.pytest_plugin import pytest_runtest_makereport


class _FakeOutcome:
    def __init__(self, report):
        self._report = report

    def get_result(self):
        return self._report


def _make_report(*, when="call", failed=True, sections=None):
    report = MagicMock()
    report.when = when
    report.failed = failed
    report.sections = sections if sections is not None else []
    return report


def _make_call(*, exc=None):
    call = MagicMock()
    if exc is None:
        call.excinfo = None
    else:
        call.excinfo = MagicMock()
        call.excinfo.value = exc
    return call


def _run_hook(report, call):
    gen = pytest_runtest_makereport(item=MagicMock(), call=call)
    next(gen)
    with contextlib.suppress(StopIteration):
        gen.send(_FakeOutcome(report))
    return report


class TestPluginLoaded:
    def test_plugin_is_registered(self):
        pm = pytest.importorskip("assertpy2.pytest_plugin")
        assert hasattr(pm, "pytest_runtest_makereport")


class TestHookSkipsIrrelevantReports:
    def test_skip_when_not_call_phase(self):
        report = _make_report(when="setup")
        call = _make_call(exc=AssertionError("x"))
        _run_hook(report, call)
        assert report.sections == []

    def test_skip_when_not_failed(self):
        report = _make_report(failed=False)
        call = _make_call(exc=AssertionError("x"))
        _run_hook(report, call)
        assert report.sections == []

    def test_skip_when_excinfo_is_none(self):
        report = _make_report()
        call = _make_call(exc=None)
        _run_hook(report, call)
        assert report.sections == []

    def test_skip_when_not_assertion_error(self):
        report = _make_report()
        call = _make_call(exc=ValueError("not assertion"))
        _run_hook(report, call)
        assert report.sections == []

    def test_skip_when_no_structured_data(self):
        report = _make_report()
        call = _make_call(exc=AssertionError("plain error"))
        _run_hook(report, call)
        assert report.sections == []


class TestHookActualExpected:
    def test_both_actual_and_expected(self):
        exc = AssertionFailure("fail", actual=1, expected=2)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        titles = [title for title, _ in report.sections]
        assert "AssertionFailure" in titles
        body = dict(report.sections)["AssertionFailure"]
        assert "actual" in body
        assert "expected" in body

    def test_only_actual(self):
        exc = AssertionFailure("fail", actual=42)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["AssertionFailure"]
        assert "actual" in body
        assert "42" in body
        assert "expected" not in body

    def test_only_expected(self):
        exc = AssertionFailure("fail", expected="abc")
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["AssertionFailure"]
        assert "expected" in body
        assert "abc" in body
        assert "actual" not in body


class TestHookDiff:
    def test_diff_section_added(self):
        diff = DiffResult(
            kind="dict",
            entries=[
                DiffEntry(path="key1", actual="a", expected="b"),
            ],
        )
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        titles = [title for title, _ in report.sections]
        assert "Structured Diff" in titles
        body = dict(report.sections)["Structured Diff"]
        assert "key1" in body

    def test_diff_without_actual_expected(self):
        diff = DiffResult(
            kind="scalar",
            entries=[
                DiffEntry(path=".", actual=1, expected=2),
            ],
        )
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        titles = [title for title, _ in report.sections]
        assert "Structured Diff" in titles
        assert "AssertionFailure" not in titles

    def test_actual_expected_and_diff_together(self):
        diff = DiffResult(
            kind="dict",
            entries=[
                DiffEntry(path="x", actual=1, expected=2),
            ],
        )
        exc = AssertionFailure("fail", actual={"x": 1}, expected={"x": 2}, diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        titles = [title for title, _ in report.sections]
        assert "AssertionFailure" in titles
        assert "Structured Diff" in titles
