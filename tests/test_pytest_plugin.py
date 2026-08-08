import contextlib
import json
import os
import subprocess
import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from assertpy2 import _satisfies as _satisfies_module
from assertpy2 import assert_that, async_assertions, match
from assertpy2 import errors as errors_module
from assertpy2 import pytest_plugin as pytest_plugin
from assertpy2 import snapshot as snapshot_module
from assertpy2.errors import AssertionFailure, DiffEntry, DiffResult, PollSample, PollTrace
from assertpy2.pytest_plugin import (
    _diff_to_json,
    _format_trace,
    _is_full_run,
    _json_safe,
    _trace_to_json,
    pytest_addoption,
    pytest_configure,
    pytest_runtest_makereport,
    pytest_runtest_setup,
    pytest_sessionfinish,
    pytest_testnodedown,
    pytest_unconfigure,
)


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


def _make_item(*, allure_mode="diff"):
    item = MagicMock()
    item.config._assertpy2_allure_mode = allure_mode
    item.config._assertpy2_diff_enabled = True
    item.config._assertpy2_diff_max = 50
    item.config.option.color = "no"
    return item


def _run_hook(report, call, *, item=None):
    if item is None:
        item = _make_item()
    gen = pytest_runtest_makereport(item=item, call=call)
    next(gen)
    with contextlib.suppress(StopIteration):
        gen.send(_FakeOutcome(report))
    return report


class TestPluginLoaded:
    def test_plugin_is_registered(self):
        pm = pytest.importorskip("assertpy2.pytest_plugin")
        assert_that(hasattr(pm, "pytest_runtest_makereport")).is_true()

    def test_addoption_registers_ini(self):
        parser = MagicMock()
        pytest_addoption(parser)
        assert_that(parser.addini.call_count).is_equal_to(4)
        names = [call[0][0] for call in parser.addini.call_args_list]
        assert_that(names).contains("assertpy2_allure")
        assert_that(names).contains("assertpy2_diff")
        assert_that(names).contains("assertpy2_diff_max_entries")


class TestHookSkipsIrrelevantReports:
    def test_skip_when_not_call_phase(self):
        report = _make_report(when="setup")
        call = _make_call(exc=AssertionError("x"))
        _run_hook(report, call)
        assert_that(report.sections).is_empty()

    def test_skip_when_not_failed(self):
        report = _make_report(failed=False)
        call = _make_call(exc=AssertionError("x"))
        _run_hook(report, call)
        assert_that(report.sections).is_empty()

    def test_skip_when_excinfo_is_none(self):
        report = _make_report()
        call = _make_call(exc=None)
        _run_hook(report, call)
        assert_that(report.sections).is_empty()

    def test_skip_when_not_assertion_error(self):
        report = _make_report()
        call = _make_call(exc=ValueError("not assertion"))
        _run_hook(report, call)
        assert_that(report.sections).is_empty()

    def test_skip_when_no_structured_data(self):
        report = _make_report()
        call = _make_call(exc=AssertionError("plain error"))
        _run_hook(report, call)
        assert_that(report.sections).is_empty()


class TestHookActualExpected:
    def test_both_actual_and_expected(self):
        exc = AssertionFailure("fail", actual=1, expected=2)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        titles = [title for title, _ in report.sections]
        assert_that(titles).contains("AssertionFailure")
        body = dict(report.sections)["AssertionFailure"]
        assert_that(body).contains("actual")
        assert_that(body).contains("expected")

    def test_only_actual(self):
        exc = AssertionFailure("fail", actual=42)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["AssertionFailure"]
        assert_that(body).contains("actual")
        assert_that(body).contains("42")
        assert_that(body).does_not_contain("expected")

    def test_only_expected(self):
        exc = AssertionFailure("fail", expected="abc")
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["AssertionFailure"]
        assert_that(body).contains("expected")
        assert_that(body).contains("abc")
        assert_that(body).does_not_contain("actual")


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
        assert_that(titles).contains("Structured Diff")
        body = dict(report.sections)["Structured Diff"]
        assert_that(body).contains("key1")

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
        assert_that(titles).contains("Structured Diff")
        assert_that(titles).does_not_contain("AssertionFailure")

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
        assert_that(titles).contains("AssertionFailure")
        assert_that(titles).contains("Structured Diff")


class TestFormatDiff:
    def test_sequence_both_present(self):
        diff = DiffResult(kind="sequence", entries=[DiffEntry(path="[0]", actual=1, expected=2)])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["Structured Diff"]
        assert_that(body).contains("[0]:")
        assert_that(body).contains("- 1")
        assert_that(body).contains("+ 2")

    def test_sequence_actual_only(self):
        diff = DiffResult(kind="sequence", entries=[DiffEntry(path="[1]", actual=99, expected=None)])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["Structured Diff"]
        assert_that(body).contains("[1]: - 99")

    def test_sequence_expected_only(self):
        diff = DiffResult(kind="sequence", entries=[DiffEntry(path="[2]", actual=None, expected=42)])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["Structured Diff"]
        assert_that(body).contains("[2]: + 42")

    def test_set_extra_and_missing(self):
        diff = DiffResult(
            kind="set",
            entries=[
                DiffEntry(path="extra", actual=5, expected=None),
                DiffEntry(path="missing", actual=None, expected=10),
            ],
        )
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["Structured Diff"]
        assert_that(body).contains("extra:")
        assert_that(body).contains("5")
        assert_that(body).contains("missing:")
        assert_that(body).contains("10")

    def test_string_diff(self):
        diff = DiffResult(kind="string", entries=[DiffEntry(path="line 1", actual="foo", expected="bar")])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["Structured Diff"]
        assert_that(body).contains("line 1:")
        # string diffs now render the raw line (with intra-line carets), not its repr
        assert_that(body).contains("foo")
        assert_that(body).contains("bar")

    def test_set_extra_only(self):
        diff = DiffResult(kind="set", entries=[DiffEntry(path="extra", actual=5, expected=None)])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["Structured Diff"]
        assert_that(body).contains("extra:")
        assert_that(body).does_not_contain("missing")

    def test_set_missing_only(self):
        diff = DiffResult(kind="set", entries=[DiffEntry(path="missing", actual=None, expected=10)])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["Structured Diff"]
        assert_that(body).contains("missing:")
        assert_that(body).does_not_contain("extra")

    def test_empty_diff_returns_str_repr(self):
        diff = DiffResult(kind="scalar", entries=[])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["Structured Diff"]
        assert_that(body).is_empty()


class TestDiffToJson:
    def test_returns_none_for_empty_entries(self):
        diff = DiffResult(kind="dict")
        assert_that(_diff_to_json(diff)).is_none()

    def test_payload_carries_format_version(self):
        # consumers can branch on the attachment schema: 1 = repr-strings (implicit), 2 = typed values
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="a", actual=1, expected=2)])
        assert_that(json.loads(_diff_to_json(diff))["format"]).is_equal_to(2)

    def test_returns_valid_json(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="a", actual=1, expected=2)])
        result = json.loads(_diff_to_json(diff))
        assert_that(result["kind"]).is_equal_to("dict")
        assert_that(result["entries"]).is_length(1)
        assert_that(result["entries"][0]["path"]).is_equal_to("a")
        assert_that(result["entries"][0]["actual"]).is_equal_to(1)
        assert_that(result["entries"][0]["expected"]).is_equal_to(2)

    def test_string_values_stay_native_strings(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual="<b>", expected="&")])
        result = json.loads(_diff_to_json(diff))
        assert_that(result["entries"][0]["actual"]).is_equal_to("<b>")
        assert_that(result["entries"][0]["expected"]).is_equal_to("&")

    def test_multiple_entries(self):
        diff = DiffResult(
            kind="dict",
            entries=[
                DiffEntry(path="x", actual=1, expected=2),
                DiffEntry(path="y", actual=3, expected=4),
            ],
        )
        result = json.loads(_diff_to_json(diff))
        assert_that(result["entries"]).is_length(2)
        assert_that(result["entries"][0]["path"]).is_equal_to("x")
        assert_that(result["entries"][1]["path"]).is_equal_to("y")

    def test_truncates_to_max_entries(self):
        diff = DiffResult(
            kind="dict",
            entries=[DiffEntry(path=f"k{i}", actual=i, expected=i + 1) for i in range(5)],
        )
        result = json.loads(_diff_to_json(diff, max_entries=2))
        assert_that(result["entries"]).is_length(2)
        assert_that(result["truncated"]).is_equal_to(3)


class _RaisingRepr:
    def __repr__(self):
        raise RuntimeError("broken repr")


class TestJsonSafe:
    """The attachment sanitizer is typed where possible, and total and bounded everywhere else."""

    def test_native_scalars_pass_through(self):
        assert_that(_json_safe(None)).is_none()
        assert_that(_json_safe(True)).is_true()
        assert_that(_json_safe(7)).is_equal_to(7)
        assert_that(_json_safe(1.5)).is_equal_to(1.5)
        assert_that(_json_safe("text")).is_equal_to("text")

    def test_non_finite_floats_become_markers(self):
        assert_that(_json_safe(float("nan"))).is_equal_to({"__repr__": "nan"})
        assert_that(_json_safe(float("inf"))).is_equal_to({"__repr__": "inf"})

    def test_huge_string_is_truncated(self):
        result = _json_safe("x" * 10_000)
        assert_that(result).contains("more chars")
        assert_that(len(result)).is_less_than(5_000)

    def test_containers_stay_typed(self):
        assert_that(_json_safe({"a": [1, (2, 3)]})).is_equal_to({"a": [1, [2, 3]]})

    def test_non_string_keys_become_reprs(self):
        assert_that(_json_safe({1: "a", (2, 3): "b"})).is_equal_to({"1": "a", "(2, 3)": "b"})

    def test_oversized_dict_gets_truncation_marker(self):
        result = _json_safe({f"k{i:03d}": i for i in range(150)})
        assert_that(result["__truncated__"]).is_equal_to("... and 50 more keys")
        assert_that(result).is_length(101)

    def test_oversized_list_gets_truncation_marker(self):
        result = _json_safe(list(range(150)))
        assert_that(result).is_length(101)
        assert_that(result[-1]).is_equal_to({"__repr__": "... and 50 more items"})

    def test_set_uses_snapshot_envelope(self):
        assert_that(_json_safe({2, 1})).is_equal_to({"__type__": "set", "__data__": [1, 2]})
        assert_that(_json_safe(frozenset({"a"}))).is_equal_to({"__type__": "set", "__data__": ["a"]})

    def test_a_set_of_composites_still_recurses(self):
        # the members above are all int/str, which return at the fast path; a tuple member is the only
        # thing that makes the recursive call, and its arguments, observable
        assert_that(_json_safe({(1, 2)})).is_equal_to({"__type__": "set", "__data__": [[1, 2]]})

    def test_a_heterogeneous_set_sorts_by_repr(self):
        # sorting a mixed set is only possible through the repr key, and dropping the key is silent on
        # a homogeneous one, so both halves need pinning
        assert_that(_json_safe({1, "a"})).is_equal_to({"__type__": "set", "__data__": ["a", 1]})
        assert_that(_json_safe({2, 10})["__data__"]).is_equal_to([10, 2])

    def test_depth_cap_degrades_to_repr_marker(self):
        nested = {"level": 1}
        for _ in range(8):
            nested = {"level": nested}
        blob = json.dumps(_json_safe(nested))
        assert_that(blob).contains("__repr__")

    def test_the_depth_cap_holds_for_sequences_too(self):
        # only the dict branch was pinned, so a sequence walker that counted the wrong way stayed
        # invisible: nesting kept expanding and a deep enough structure would recurse until it blew up
        nested = [1]
        for _ in range(8):
            nested = [nested]
        blob = json.dumps(_json_safe(nested))
        assert_that(blob).contains("__repr__")

    def test_cycle_degrades_to_marker(self):
        cyclic = [1]
        cyclic.append(cyclic)
        assert_that(_json_safe(cyclic)).is_equal_to([1, {"__repr__": "<circular ref>"}])

    def test_arbitrary_object_becomes_repr_marker(self):
        class Point:
            def __repr__(self):
                return "Point(1, 2)"

        assert_that(_json_safe(Point())).is_equal_to({"__repr__": "Point(1, 2)"})

    def test_raising_repr_never_loses_the_attachment(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=_RaisingRepr(), expected=1)])
        body = json.loads(_diff_to_json(diff))
        assert_that(body["entries"][0]["actual"]).is_equal_to({"__repr__": "<unreprable _RaisingRepr>"})

    def test_output_is_strict_json(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=float("nan"), expected=1)])
        assert_that(json.loads(_diff_to_json(diff))["entries"][0]["actual"]).is_equal_to({"__repr__": "nan"})


def _make_trace():
    samples = [
        PollSample(elapsed=0.0, outcome="error", value=None, detail="ConnectionError('boot')", repeats=2),
        PollSample(elapsed=0.4, outcome="fail", value={"s": "PENDING"}, detail="Expected <...>"),
        PollSample(elapsed=0.8, outcome="fail", value={"s": "SHIPPED"}, detail="Expected <...>", repeats=3),
    ]
    return PollTrace(samples=samples, total_polls=6, dropped=0, elapsed=1.2, summary="probe recovered")


class TestPollingTrace:
    def test_terminal_section_renders_timeline(self):
        report = _make_report()
        exc = AssertionFailure("fail", trace=_make_trace())
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["Polling Trace"]
        assert_that(body).contains("polled 6 times over 1.2s; probe recovered")
        assert_that(body).contains("t=+0.0s error x2: ConnectionError('boot')")
        assert_that(body).contains("t=+0.8s fail x3:")

    def test_terminal_section_reports_dropped_samples(self):
        trace = PollTrace(samples=_make_trace().samples, total_polls=40, dropped=10, elapsed=9.0, summary="s")
        assert_that(_format_trace(trace)).contains("10 middle samples dropped")

    def test_trace_json_schema_and_deltas(self):
        body = json.loads(_trace_to_json(_make_trace()))
        assert_that(body["format"]).is_equal_to(2)
        assert_that(body["kind"]).is_equal_to("polling-trace")
        assert_that(body["total_polls"]).is_equal_to(6)
        assert_that(body["samples"]).is_length(3)
        assert_that(body["samples"][0]).does_not_contain_key("value")
        assert_that(body["samples"][0]["repeats"]).is_equal_to(2)
        assert_that(body["deltas"]).is_length(1)
        assert_that(body["deltas"][0]["entries"]).is_equal_to(
            [{"path": "s", "actual": "PENDING", "expected": "SHIPPED"}]
        )

    def test_trace_json_scalar_delta_falls_back_to_root_path(self):
        samples = [
            PollSample(elapsed=0.0, outcome="fail", value=1, detail="d"),
            PollSample(elapsed=0.5, outcome="fail", value=2, detail="d"),
        ]
        trace = PollTrace(samples=samples, total_polls=2, dropped=0, elapsed=1.0, summary="s")
        body = json.loads(_trace_to_json(trace))
        assert_that(body["deltas"][0]["entries"]).is_equal_to([{"path": ".", "actual": 1, "expected": 2}])

    def test_trace_json_reports_dropped_and_skips_equal_neighbors(self):
        samples = [
            PollSample(elapsed=0.0, outcome="fail", value={"s": 1}, detail="d"),
            PollSample(elapsed=0.4, outcome="error", value=None, detail="ConnectionError('x')"),
            PollSample(elapsed=0.8, outcome="fail", value={"s": 1}, detail="d"),
        ]
        trace = PollTrace(samples=samples, total_polls=30, dropped=7, elapsed=2.0, summary="s")
        body = json.loads(_trace_to_json(trace))
        assert_that(body["dropped"]).is_equal_to(7)
        assert_that(body).does_not_contain_key("deltas")

    def test_trace_json_without_changes_has_no_deltas(self):
        samples = [PollSample(elapsed=0.0, outcome="fail", value=1, detail="d", repeats=4)]
        trace = PollTrace(samples=samples, total_polls=4, dropped=0, elapsed=1.0, summary="s")
        assert_that(json.loads(_trace_to_json(trace))).does_not_contain_key("deltas")

    def test_trace_attached_to_allure(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", trace=_make_trace())
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock)
        names = [call.kwargs["name"] for call in mock.attach.call_args_list]
        assert_that(names).contains("Polling Trace")

    def test_trace_not_attached_when_off(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", trace=_make_trace())
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="off")
        mock.attach.assert_not_called()


def _mock_allure():
    mock = MagicMock()
    mock.attachment_type.JSON = "json"
    return mock


def _run_hook_with_allure(report, call_obj, mock_allure, *, allure_mode="diff"):
    item = _make_item(allure_mode=allure_mode)
    with (
        patch("assertpy2.pytest_plugin._HAS_ALLURE", True),
        patch("assertpy2.pytest_plugin.allure", mock_allure, create=True),
    ):
        _run_hook(report, call_obj, item=item)


class TestAllureDiffMode:
    def test_no_actual_expected_in_diff_mode(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual=1, expected=2)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock)
        mock.attach.assert_not_called()

    def test_diff_attached_in_diff_mode(self):
        mock = _mock_allure()
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        exc = AssertionFailure("fail", diff=diff)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock)
        assert_that(mock.attach.call_count).is_equal_to(1)
        assert_that(mock.attach.call_args_list[0].kwargs["name"]).is_equal_to("Structured Diff")
        assert_that(mock.attach.call_args_list[0].kwargs["attachment_type"]).is_equal_to("json")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body["kind"]).is_equal_to("dict")
        assert_that(body["entries"][0]["path"]).is_equal_to("k")

    def test_diff_with_actual_expected_only_diff_attached(self):
        mock = _mock_allure()
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="x", actual=1, expected=2)])
        exc = AssertionFailure("fail", actual={"x": 1}, expected={"x": 2}, diff=diff)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock)
        assert_that(mock.attach.call_count).is_equal_to(1)
        assert_that(mock.attach.call_args_list[0].kwargs["name"]).is_equal_to("Structured Diff")

    def test_empty_diff_entries_no_attachment(self):
        mock = _mock_allure()
        diff = DiffResult(kind="dict", entries=[])
        exc = AssertionFailure("fail", diff=diff)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock)
        mock.attach.assert_not_called()

    def test_match_diff_from_real_failure_attaches_json(self):
        mock = _mock_allure()
        try:
            assert_that({"role": "superadmin"}).matches_structure(
                {"role": match.is_in("admin", "user"), "email": match.is_non_empty_string()}
            )
        except AssertionFailure as exc:
            _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock)
        else:
            raise AssertionError("expected AssertionFailure") from None
        assert_that(mock.attach.call_count).is_equal_to(1)
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body["kind"]).is_equal_to("match")
        actuals = {entry["path"]: entry["actual"] for entry in body["entries"]}
        assert_that(actuals).contains_key("role", "email")
        assert_that(actuals["role"]).is_equal_to("superadmin")
        assert_that(actuals["email"]).is_equal_to({"__repr__": "<missing>"})


class TestAllureFullMode:
    def test_actual_expected_when_full(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual=1, expected=2)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        assert_that(mock.attach.call_count).is_equal_to(1)
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body).is_equal_to({"format": 2, "actual": 1, "expected": 2})
        assert_that(mock.attach.call_args_list[0].kwargs["name"]).is_equal_to("AssertionFailure")
        assert_that(mock.attach.call_args_list[0].kwargs["attachment_type"]).is_equal_to("json")

    def test_only_actual_when_full(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual=42)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body).is_equal_to({"format": 2, "actual": 42})

    def test_only_expected_when_full(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", expected="abc")
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body).is_equal_to({"format": 2, "expected": "abc"})

    def test_containers_attach_as_typed_json(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual={"a": 1}, expected=[1, 2])
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body["actual"]).is_equal_to({"a": 1})
        assert_that(body["expected"]).is_equal_to([1, 2])

    def test_all_three_produces_two_attachments(self):
        mock = _mock_allure()
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="x", actual=1, expected=2)])
        exc = AssertionFailure("fail", actual={"x": 1}, expected={"x": 2}, diff=diff)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        assert_that(mock.attach.call_count).is_equal_to(2)
        names = [call.kwargs["name"] for call in mock.attach.call_args_list]
        assert_that(names).contains("AssertionFailure")
        assert_that(names).contains("Structured Diff")


class TestAllureOffMode:
    def test_no_attachments_when_off(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual=1, expected=2)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="off")
        mock.attach.assert_not_called()

    def test_no_diff_attachment_when_off(self):
        mock = _mock_allure()
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        exc = AssertionFailure("fail", diff=diff)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="off")
        mock.attach.assert_not_called()

    def test_no_attachments_with_all_data_when_off(self):
        mock = _mock_allure()
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="x", actual=1, expected=2)])
        exc = AssertionFailure("fail", actual={"x": 1}, expected={"x": 2}, diff=diff)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="off")
        mock.attach.assert_not_called()


def _make_config(*, ini="diff", snapshot_update=False, poll_report="0.7"):
    # a bare MagicMock returns a truthy mock from getoption(), which would flip the snapshot-update
    # module flag and leak update mode into unrelated tests
    config = MagicMock()
    # dispatch per key: a single return value would feed the allure mode to every other ini reader
    config.getini.side_effect = lambda name: poll_report if name == "assertpy2_poll_report" else ini
    config.getoption.return_value = snapshot_update
    return config


class TestPytestConfigure:
    def test_valid_mode_stored(self):
        config = _make_config(ini="full")
        pytest_configure(config)
        assert_that(config._assertpy2_allure_mode).is_equal_to("full")

    def test_default_diff_mode_stored(self):
        config = _make_config(ini="diff")
        pytest_configure(config)
        assert_that(config._assertpy2_allure_mode).is_equal_to("diff")

    def test_invalid_mode_warns_and_falls_back(self):
        config = _make_config(ini="unknown")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_configure(config)
        assert_that(config._assertpy2_allure_mode).is_equal_to("diff")
        assert_that(caught).is_length(1)
        assert_that(str(caught[0].message)).contains("unknown")

    def test_configure_disables_diff_in_message_and_unconfigure_restores(self, monkeypatch):
        # under a real session the plugin renders the diff itself, so it keeps it out of the message; the
        # prior value is saved and restored so nested/direct hook calls stay balanced
        monkeypatch.setattr(errors_module, "_RENDER_DIFF_IN_MESSAGE", True)
        config = _make_config()
        pytest_configure(config)
        assert_that(errors_module._RENDER_DIFF_IN_MESSAGE).is_false()
        pytest_unconfigure(config)
        assert_that(errors_module._RENDER_DIFF_IN_MESSAGE).is_true()


class TestSnapshotUpdateOption:
    def test_addoption_registers_flag(self):
        parser = MagicMock()
        pytest_addoption(parser)
        names = [call[0][0] for call in parser.addoption.call_args_list]
        assert_that(names).contains("--assertpy2-snapshot-update")

    def test_the_boolean_flags_are_opt_in(self):
        # nothing pinned the defaults, so each of these flipped to default=True unnoticed: update mode
        # would silently rewrite a changed snapshot, and CI mode would fail a first local capture.
        # named one by one rather than swept over every registered option, which would also forbid ever
        # adding one that takes a value
        parser = MagicMock()
        pytest_addoption(parser)
        registered = {call[0][0]: call[1] for call in parser.addoption.call_args_list}
        for name in (
            "--assertpy2-snapshot-update",
            "--assertpy2-vacuous",
            "--assertpy2-snapshot-ci",
            "--assertpy2-snapshot-no-ci",
        ):
            assert_that(registered).contains_key(name)
            assert_that(registered[name]).described_as(name).contains_entry(
                {"action": "store_true"}, {"default": False}
            )

    def test_flag_toggles_module_state_and_unconfigure_resets(self):
        config = _make_config(snapshot_update=True)
        try:
            pytest_configure(config)
            assert_that(snapshot_module._UPDATE_ALL).is_true()
        finally:
            pytest_unconfigure(config)
        assert_that(snapshot_module._UPDATE_ALL).is_false()

    def test_without_flag_module_state_untouched(self):
        config = _make_config(snapshot_update=False)
        pytest_configure(config)
        assert_that(snapshot_module._UPDATE_ALL).is_false()
        pytest_unconfigure(config)
        assert_that(snapshot_module._UPDATE_ALL).is_false()

    def test_ci_flag_sets_mode_true_and_unconfigure_resets(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_CI_MODE", None)
        config = _make_config()
        config.getoption.side_effect = lambda name: name == "assertpy2_snapshot_ci"
        pytest_configure(config)
        assert_that(snapshot_module._CI_MODE).is_true()
        pytest_unconfigure(config)
        assert_that(snapshot_module._CI_MODE).is_none()

    def test_no_ci_flag_sets_mode_false_and_unconfigure_resets(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_CI_MODE", True)  # start from a distinct state
        config = _make_config()
        config.getoption.side_effect = lambda name: name == "assertpy2_snapshot_no_ci"
        pytest_configure(config)
        assert_that(snapshot_module._CI_MODE).is_false()  # elif no-ci branch set it False
        pytest_unconfigure(config)
        assert_that(snapshot_module._CI_MODE).is_none()


def _controller_config(reporter, *, full=True):
    # a controller (non-xdist-worker) config: no ``workeroutput`` attr, so pytest_sessionfinish takes
    # the aggregation-and-report branch instead of the worker ship-out branch
    option = SimpleNamespace(keyword="" if full else "somekeyword", markexpr="", last_failed=False, failed_first=False)
    pluginmanager = SimpleNamespace(get_plugin=lambda name: reporter if name == "terminalreporter" else None)
    return SimpleNamespace(option=option, pluginmanager=pluginmanager)


class TestSnapshotOrphans:
    def test_worker_ships_touched_to_controller(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {("/x/snap-a.json", "10")})
        config = SimpleNamespace(workeroutput={})
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy2_touched"]).is_equal_to([["/x/snap-a.json", "10"]])

    def test_testnodedown_collects_worker_touches(self):
        pytest_plugin._controller_touched.clear()
        node = SimpleNamespace(workeroutput={"assertpy2_touched": [["/x/snap-a.json", "10"]]})
        pytest_testnodedown(node, None)
        assert_that(pytest_plugin._controller_touched).contains(("/x/snap-a.json", "10"))
        pytest_plugin._controller_touched.clear()

    def test_testnodedown_ignores_node_without_touches(self):
        pytest_plugin._controller_touched.clear()
        pytest_testnodedown(SimpleNamespace(workeroutput={}), None)
        assert_that(pytest_plugin._controller_touched).is_empty()

    def test_the_prune_locks_the_file_it_rewrites(self, tmp_path, monkeypatch):
        # nothing asserted which path the lock was taken on, so it could be taken on a constant and
        # stop excluding a concurrent write of the same snapshot, littering the cwd on the way
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        locked = []
        real_lock = snapshot_module._file_lock
        monkeypatch.setattr(
            snapshot_module, "_file_lock", lambda target, **kw: locked.append(target) or real_lock(target, **kw)
        )
        snapshot_module._prune_sub_key_orphans([(snapname, "30")])
        assert_that(locked).is_equal_to([snapname])

    def test_is_full_run_variants(self):
        def config(**opt):
            base = {"keyword": "", "markexpr": "", "last_failed": False, "failed_first": False, "file_or_dir": []}
            return SimpleNamespace(option=SimpleNamespace(**{**base, **opt}))

        assert_that(_is_full_run(config())).is_true()
        assert_that(_is_full_run(config(keyword="k"))).is_false()
        assert_that(_is_full_run(config(markexpr="m"))).is_false()
        assert_that(_is_full_run(config(last_failed=True))).is_false()
        assert_that(_is_full_run(config(failed_first=True))).is_false()
        # a nodeid selection (path::test) runs only a subset of a file's tests
        assert_that(_is_full_run(config(file_or_dir=["tests/test_x.py::test_a"]))).is_false()
        # a whole-file or directory selection still runs all of that file's tests
        assert_that(_is_full_run(config(file_or_dir=["tests/test_x.py"]))).is_true()

    def test_sessionfinish_no_touches_is_quiet(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_TOUCHED", set())
        pytest_plugin._controller_touched.clear()
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter)), 0)
        reporter.write_line.assert_not_called()

    def test_sessionfinish_no_orphans_is_quiet(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w") as handle:
            json.dump({"10": 1}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter)), 0)
        reporter.write_line.assert_not_called()

    def test_reports_sub_key_orphan_without_pruning(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", False)
        monkeypatch.delenv("ASSERTPY2_SNAPSHOT_UPDATE", raising=False)
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter)), 0)
        text = " ".join(str(call) for call in reporter.write_line.call_args_list)
        assert_that(text).contains("::30").contains("full run to remove")
        assert_that(json.loads((tmp_path / "snap-mod.json").read_text())).contains_key("30")  # not pruned

    def test_prunes_sub_key_under_update_full_run(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", True)
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter, full=True)), 0)
        text = " ".join(str(call) for call in reporter.write_line.call_args_list)
        assert_that(text).contains("removed")
        assert_that(json.loads((tmp_path / "snap-mod.json").read_text())).does_not_contain_key("30")  # pruned

    def test_no_prune_on_filtered_run(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", True)
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter, full=False)), 0)
        assert_that(json.loads((tmp_path / "snap-mod.json").read_text())).contains_key("30")  # not pruned

    def test_no_prune_on_nodeid_selected_run(self, tmp_path, monkeypatch):
        # nodeid selection (path::test) runs only a subset of a file's tests, so a live but un-run
        # sibling sub-snap must not be pruned as obsolete even under update mode
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", True)
        reporter = MagicMock()
        option = SimpleNamespace(
            keyword="", markexpr="", last_failed=False, failed_first=False, file_or_dir=["tests/test_mod.py::test_a"]
        )
        pluginmanager = SimpleNamespace(get_plugin=lambda name: reporter if name == "terminalreporter" else None)
        config = SimpleNamespace(option=option, pluginmanager=pluginmanager)
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(json.loads((tmp_path / "snap-mod.json").read_text())).contains_key("30")  # not pruned

    def test_whole_file_orphan_is_report_only_even_under_update(self, tmp_path, monkeypatch):
        live = str(tmp_path / "snap-live.json")
        dead = str(tmp_path / "snap-dead.json")
        for target in (live, dead):
            with open(target, "w") as handle:
                json.dump({"10": 1}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(live, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", True)
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter, full=True)), 0)
        assert_that(os.path.isfile(dead)).is_true()  # whole file is never auto-pruned
        text = " ".join(str(call) for call in reporter.write_line.call_args_list)
        assert_that(text).contains("obsolete snapshot file")


class TestAllureExceptionSafety:
    def test_allure_attach_failure_does_not_break_report(self):
        mock = _mock_allure()
        mock.attach.side_effect = RuntimeError("allure broken")
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook_with_allure(report, _make_call(exc=exc), mock)
        assert_that(report.sections).is_length(1)
        assert_that(report.sections[0][0]).is_equal_to("Structured Diff")


class TestAllureNotAvailable:
    def test_no_attach_when_allure_missing(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual=1, expected=2)
        report = _make_report()
        with (
            patch("assertpy2.pytest_plugin._HAS_ALLURE", False),
            patch("assertpy2.pytest_plugin.allure", mock, create=True),
        ):
            _run_hook(report, _make_call(exc=exc))
        mock.attach.assert_not_called()

    def test_sections_still_added_without_allure(self):
        exc = AssertionFailure("fail", actual=1, expected=2)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        assert_that(report.sections).is_length(1)
        assert_that(report.sections[0][0]).is_equal_to("AssertionFailure")


class TestNearTimeoutReport:
    """Retrying is what eventually() is for, so only a poll that burned its budget is worth naming."""

    @pytest.fixture(autouse=True)
    def _clean(self):
        pytest_plugin._retried.clear()
        yield
        pytest_plugin._retried.clear()

    @staticmethod
    def _lines(rows):
        pytest_plugin._retried.extend(rows)
        reporter = MagicMock()
        config = SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter))
        pytest_plugin._report_retries(config)
        return [call.args[0] for call in reporter.write_line.call_args_list]

    def test_a_poll_against_the_deadline_is_named(self):
        lines = self._lines([("t.py::test_x", 41, 0.81, 1.0)])
        assert_that("\n".join(lines)).contains("t.py::test_x").contains("81% of the budget")

    def test_a_healthy_retry_is_not_named(self):
        # converging at 2% of the budget is eventually() working, not a test about to go flaky
        assert_that(self._lines([("t.py::test_x", 3, 0.04, 2.0)])).is_empty()

    def test_nothing_collected_stays_quiet(self):
        assert_that(self._lines([])).is_empty()

    def test_a_zero_budget_is_not_divided_by(self):
        assert_that(self._lines([("t.py::test_x", 2, 0.0, 0.0)])).is_empty()

    def test_draining_tags_each_poll_with_its_test(self):
        async_assertions._RETRIES.append((41, 0.81, 1.0))
        pytest_plugin._drain_retries("t.py::test_x")
        assert_that(pytest_plugin._retried).is_equal_to([("t.py::test_x", 41, 0.81, 1.0)])
        assert_that(async_assertions._RETRIES).is_empty()

    def test_a_teardown_phase_retry_keeps_its_own_test(self):
        # teardown runs after the call report, so draining only on "call" would leave the retry sitting
        # in the list until the NEXT test's call phase claimed it
        async_assertions._RETRIES.append((41, 0.81, 1.0))
        report = _make_report(when="teardown", failed=False)
        report.nodeid = "t.py::test_owner"
        _run_hook(report, _make_call())
        assert_that([row[0] for row in pytest_plugin._retried]).is_equal_to(["t.py::test_owner"])
        assert_that(async_assertions._RETRIES).is_empty()

    def test_worker_ships_retries_to_controller(self):
        pytest_plugin._retried.append(("t.py::test_x", 41, 0.81, 1.0))
        config = SimpleNamespace(workeroutput={})
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy2_retried"]).is_equal_to([["t.py::test_x", 41, 0.81, 1.0]])

    def test_testnodedown_collects_worker_retries(self):
        node = SimpleNamespace(workeroutput={"assertpy2_retried": [["t.py::test_x", 41, 0.81, 1.0]]})
        pytest_testnodedown(node, None)
        assert_that(pytest_plugin._retried).contains(("t.py::test_x", 41, 0.81, 1.0))


class TestPollReportIni:
    """The report prints on its own; without a bar to move or an off switch it cannot be lived with."""

    @pytest.fixture(autouse=True)
    def _clean(self):
        pytest_plugin._retried.clear()
        yield
        pytest_plugin._retried.clear()

    @staticmethod
    def _lines(rows, threshold):
        pytest_plugin._retried.extend(rows)
        reporter = MagicMock()
        config = SimpleNamespace(
            pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter),
            _assertpy2_poll_threshold=threshold,
        )
        pytest_plugin._report_retries(config)
        return [call.args[0] for call in reporter.write_line.call_args_list]

    def test_addini_registers_the_key(self):
        parser = MagicMock()
        pytest_addoption(parser)
        assert_that([call[0][0] for call in parser.addini.call_args_list]).contains("assertpy2_poll_report")

    def test_off_silences_the_report(self):
        assert_that(self._lines([("t.py::test_x", 41, 0.81, 1.0)], None)).is_empty()

    def test_off_also_stops_collecting(self):
        config = _make_config(poll_report="off")
        try:
            pytest_configure(config)
            assert_that(config._assertpy2_poll_threshold).is_none()
            assert_that(async_assertions._COLLECT_RETRIES).is_false()
        finally:
            pytest_unconfigure(config)

    def test_a_lower_bar_names_a_poll_the_default_would_not(self):
        rows = [("t.py::test_x", 5, 0.4, 1.0)]
        assert_that(self._lines(rows, 0.7)).is_empty()
        pytest_plugin._retried.clear()
        assert_that("\n".join(self._lines(rows, 0.3))).contains("t.py::test_x")

    def test_a_fraction_is_parsed_from_the_ini(self):
        config = _make_config(poll_report="0.95")
        try:
            pytest_configure(config)
            assert_that(config._assertpy2_poll_threshold).is_equal_to(0.95)
            assert_that(async_assertions._COLLECT_RETRIES).is_true()
        finally:
            pytest_unconfigure(config)

    @pytest.mark.parametrize("raw", ["loud", "0", "-0.5", "1.5"])
    def test_an_unusable_value_warns_and_falls_back(self, raw):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            threshold = pytest_plugin._poll_threshold(raw)
        assert_that(threshold).is_equal_to(0.7)
        assert_that(str(caught[0].message)).contains("falling back to 0.7")


class TestVacuityGuardSwitch:
    """The environment is read once, so the plugin must not leave the module flag where it found it."""

    def test_env_switch_reads_truthy_spellings(self, monkeypatch):
        for raw in ("1", "true", "YES", " on "):
            monkeypatch.setenv("ASSERTPY2_VACUOUS", raw)
            assert_that(_satisfies_module._env_enabled()).described_as(raw).is_true()

    def test_env_switch_rejects_anything_else(self, monkeypatch):
        monkeypatch.setenv("ASSERTPY2_VACUOUS", "maybe")
        assert_that(_satisfies_module._env_enabled()).is_false()
        monkeypatch.delenv("ASSERTPY2_VACUOUS")
        assert_that(_satisfies_module._env_enabled()).is_false()

    def test_flag_sets_the_guard_and_unconfigure_restores_it(self, monkeypatch):
        monkeypatch.setattr(_satisfies_module, "_VACUOUS_GUARD", False)
        config = _make_config()
        config.getoption.side_effect = lambda name: name == "assertpy2_vacuous"
        pytest_configure(config)
        assert_that(_satisfies_module._VACUOUS_GUARD).is_true()
        pytest_unconfigure(config)
        assert_that(_satisfies_module._VACUOUS_GUARD).is_false()

    def test_unconfigure_keeps_a_guard_the_environment_turned_on(self, monkeypatch):
        # without the flag the plugin changes nothing, so restoring must not clear an env-set guard
        monkeypatch.setattr(_satisfies_module, "_VACUOUS_GUARD", True)
        config = _make_config()
        pytest_configure(config)
        pytest_unconfigure(config)
        assert_that(_satisfies_module._VACUOUS_GUARD).is_true()

    def test_unconfigure_without_configure_falls_back_to_the_environment(self, monkeypatch):
        monkeypatch.setattr(_satisfies_module, "_VACUOUS_GUARD", True)
        monkeypatch.delenv("ASSERTPY2_VACUOUS", raising=False)
        pytest_unconfigure(SimpleNamespace(getoption=lambda name: False))
        assert_that(_satisfies_module._VACUOUS_GUARD).is_false()


class TestSnapshotKeyReuseWarning:
    """One key reached by two tests means only the first one's value was ever asserted."""

    @pytest.fixture(autouse=True)
    def _clean_registries(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_ACCESS_NODES", {})
        monkeypatch.setattr(snapshot_module, "_ACCESS_SITES", {})
        monkeypatch.setattr(snapshot_module, "_WARNED", set())
        monkeypatch.setattr(snapshot_module, "_TOUCHED", set())
        monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", "test_mod.py::test_a")
        pytest_plugin._controller_accesses.clear()

    def test_runtest_setup_names_the_running_test(self, monkeypatch):
        pytest_runtest_setup(SimpleNamespace(nodeid="test_mod.py::test_z"))
        assert_that(snapshot_module._CURRENT_NODE).is_equal_to("test_mod.py::test_z")

    def test_a_second_test_on_one_key_warns_where_it_happened(self, monkeypatch):
        snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", "test_mod.py::test_b")
            snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        assert_that(caught).is_length(1)
        assert_that(caught[0].category).is_equal_to(snapshot_module.SnapshotKeyReusedWarning)
        # the message has to carry the cause, not just the fact: a key alone is not actionable
        # no count here: this fires on the second reach, a third may follow, and the other xdist
        # workers are invisible from inside a test. any number would read as a total
        assert_that(str(caught[0].message)).contains("test_mod.py:17").contains("reached by more than one test")
        assert_that(str(caught[0].message)).does_not_contain("shared by")
        assert_that(str(caught[0].message)).contains("snapshot(id=...)")

    def test_the_warning_points_at_the_line_that_reused_the_key(self, monkeypatch, tmp_path):
        # catch_warnings records the message but not where pytest will attribute it, so the stack
        # level was free to drift onto our own frame or into pytest internals, where a module-scoped
        # filterwarnings rule would stop matching it. driven through snapshot() because the depth is
        # only right on the real call path
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert_that({"u": 1}).snapshot(id="shared", path=str(tmp_path))
            monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", "test_mod.py::test_b")
            assert_that({"u": 1}).snapshot(id="shared", path=str(tmp_path))
        reuse = [w for w in caught if w.category is snapshot_module.SnapshotKeyReusedWarning]
        assert_that(reuse).is_length(1)
        assert_that(reuse[0].filename).is_equal_to(__file__)

    def test_one_test_reaching_a_key_twice_is_left_alone(self):
        # the legitimate case: a helper that snapshots twice inside one test asserts both values
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for _ in range(4):
                snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        assert_that(caught).is_empty()
        assert_that(snapshot_module._ACCESS_NODES["/x/snap.json", "17"]).is_length(1)

    def test_a_third_test_does_not_warn_again(self, monkeypatch):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for node in ("test_a", "test_b", "test_c"):
                monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", node)
                snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        assert_that(caught).is_length(1)

    def test_off_pytest_nothing_is_recorded(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", None)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
            snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        assert_that(caught).is_empty()
        assert_that(snapshot_module._ACCESS_NODES).is_empty()
        assert_that(snapshot_module._TOUCHED).contains(("/x/snap.json", "17"))  # orphan tracking is unaffected

    def test_a_custom_id_reads_as_a_whole_file(self, monkeypatch):
        snapshot_module._record_access("/x/snap.json", "", "id='payload'")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", "test_mod.py::test_b")
            snapshot_module._record_access("/x/snap.json", "", "id='payload'")
        assert_that(str(caught[0].message)).contains("<whole file>").contains("id='payload'")

    def test_worker_ships_node_ids_and_the_controller_unions_them(self):
        # two parametrised cases on two workers are one node id each locally, so only the union sees it
        config = SimpleNamespace(workeroutput={})
        snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy2_accesses"]).is_equal_to(
            [["/x/snap.json", "17", ["test_mod.py::test_a"], "test_mod.py:17"]]
        )
        for node in ("test_mod.py::test_a", "test_mod.py::test_b"):
            pytest_testnodedown(
                SimpleNamespace(workeroutput={"assertpy2_accesses": [["/x/s.json", "9", [node], "s:9"]]}), None
            )
        assert_that(pytest_plugin._controller_accesses["/x/s.json", "9"]).is_length(2)

    def test_the_sweep_reports_what_no_worker_could_see(self):
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        snapshot_module._ACCESS_SITES["/x/s.json", "9"] = "test_mod.py:9"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_sessionfinish(SimpleNamespace(config=_controller_config(MagicMock())), 0)
        reported = [str(w.message) for w in caught if w.category is snapshot_module.SnapshotKeyReusedWarning]
        assert_that(reported).is_length(1)
        # the sweep has counted every test that reached the key, so it states a total rather than the
        # "at least" the in-test warning has to settle for
        assert_that(reported[0]).contains("shared by 2 tests").does_not_contain("at least")

    def test_the_sweep_counts_a_key_a_test_already_reported(self):
        # the in-test warning says where it happened and cannot say how many, so the sweep runs for
        # every reused key rather than only for the ones nobody reported. two messages about one key
        # is the price of the count being right
        snapshot_module._WARNED.add(("/x/s.json", "9"))
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b", "test_c"}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_sessionfinish(SimpleNamespace(config=_controller_config(MagicMock())), 0)
        reported = [str(w.message) for w in caught if w.category is snapshot_module.SnapshotKeyReusedWarning]
        assert_that(reported).is_length(1)
        assert_that(reported[0]).contains("shared by 3 tests")

    def test_a_key_reached_once_does_not_stop_the_sweep(self):
        # the sweep walks the keys in sorted order and skips the ones reached by a single test. a
        # `break` in place of that `continue` would report nothing after the first such key, and every
        # other test here has exactly one key in play, where the two are indistinguishable
        pytest_plugin._controller_accesses[("/x/a.json", "1")] = {"test_a"}
        pytest_plugin._controller_accesses[("/x/b.json", "9")] = {"test_a", "test_b"}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_sessionfinish(SimpleNamespace(config=_controller_config(MagicMock())), 0)
        reported = [str(w.message) for w in caught if w.category is snapshot_module.SnapshotKeyReusedWarning]
        assert_that(reported).is_length(1)
        assert_that(reported[0]).contains("/x/b.json")

    def test_an_escalated_sweep_warning_fails_the_run_rather_than_the_hook(self):
        # under `-W error` the warning raises here instead of at a test, and an exception out of a
        # session-finish hook is an INTERNALERROR whose traceback points at the plugin
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        reporter = MagicMock()
        session = SimpleNamespace(config=_controller_config(reporter), exitstatus=0)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_sessionfinish(session, 0)
        assert_that(session.exitstatus).is_equal_to(pytest.ExitCode.TESTS_FAILED)
        printed = " ".join(str(call) for call in reporter.write_line.call_args_list)
        assert_that(printed).contains("shared by 2 tests")

    def test_a_run_that_died_for_another_reason_keeps_its_own_exit_status(self):
        # this hook is reached from a `finally`, so Ctrl-C lands here too. rewriting that to
        # TESTS_FAILED would report a run that never finished as one that ran and failed
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        reporter = MagicMock()
        session = SimpleNamespace(config=_controller_config(reporter), exitstatus=pytest.ExitCode.INTERRUPTED)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_sessionfinish(session, 0)
        assert_that(session.exitstatus).is_equal_to(pytest.ExitCode.INTERRUPTED)
        # the key is still worth naming: the exit code is about the run, the message about the snapshot
        printed = " ".join(str(call) for call in reporter.write_line.call_args_list)
        assert_that(printed).contains("shared by 2 tests")

    def test_the_registries_are_drained(self):
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a"}
        snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(MagicMock())), 0)
        assert_that(snapshot_module._ACCESS_NODES).is_empty()
        assert_that(snapshot_module._ACCESS_SITES).is_empty()
        assert_that(pytest_plugin._controller_accesses).is_empty()


_SHARED_KEY_MODULE = """\
import pathlib

import pytest
from assertpy2 import assert_that

SNAPS = pathlib.Path(__file__).parent / "snaps"


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("alice", marks=pytest.mark.xdist_group("g1")),
        pytest.param("bob", marks=pytest.mark.xdist_group("g2")),
        pytest.param("carol", marks=pytest.mark.xdist_group("g3")),
    ],
)
def test_case(name):
    SNAPS.mkdir(exist_ok=True)
    assert_that({{"user": name}}).matches_contract_snapshot(id={id}, path=str(SNAPS))
"""


class TestSnapshotKeyReuseUnderXdist:
    """The reuse gate across real worker processes, rather than at the seam.

    Every other test here drives the hooks directly with a fake node, which pins the logic but takes
    the plumbing on trust: the ``workeroutput`` key names matching on both sides, the payload
    surviving xdist's serialisation, the controller sweep running late enough to have every worker's
    numbers and early enough for pytest to still collect the warning.  None of that is reachable
    without spawning workers, and all of it is what silently stops a cross-process guarantee from
    ever firing again.

    Three cases in three ``xdist_group``s over three workers puts exactly one case on each, so no
    worker sees a second reach and the warning can only come from the union on the controller.  That
    split is guaranteed rather than lucky: with as many groups as workers, xdist's scheduler hands out
    one work unit per node and the queue is empty afterwards.

    Deliberately not guarded by a skip on pytest-xdist being importable.  It is a dev dependency like
    hypothesis, and a guard here would turn "the dependency went missing" into a silently skipped
    check, which is the same blindness this class exists to remove.
    """

    def _run(self, tmp_path, snapshot_id, *extra):
        # written under tmp_path on purpose: pytest would otherwise find the repository's own ini and
        # apply its `-p no:assertpy2`, disabling the very plugin under test
        (tmp_path / "test_reuse.py").write_text(_SHARED_KEY_MODULE.format(id=snapshot_id), encoding="utf-8")
        return subprocess.run(
            [
                "uv",
                "run",
                # --no-sync: this runs in the middle of the suite, and a re-resolve here would rebuild
                # the environment the remaining tests are using
                "--no-sync",
                "pytest",
                str(tmp_path / "test_reuse.py"),
                "-q",
                "--no-header",
                # the generated module writes a throwaway snapshot into tmp_path, so the first call has
                # to create one. CI mode forbids exactly that, and it turns itself on whenever `CI` is
                # set, which is every run on a build machine and no run on a developer's
                "--assertpy2-snapshot-no-ci",
                "-n",
                "3",
                "--dist",
                "loadgroup",
                "-p",
                "no:cacheprovider",
                *extra,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )

    def test_one_key_split_across_workers_still_warns(self, tmp_path):
        output = self._run(tmp_path, '"one-key"').stdout
        assert_that(output).contains("3 passed")
        assert_that(output).contains("SnapshotKeyReusedWarning").contains("shared by 3 tests")
        # the sweep's own frame: attribution to the test module would mean a single worker saw both
        # reaches, which is the case this test exists to rule out
        assert_that(output).contains("pytest_plugin.py")

    def test_a_key_per_case_stays_silent(self, tmp_path):
        # without this the check above passes just as well against a gate that warns unconditionally
        output = self._run(tmp_path, 'f"key-{name}"').stdout
        assert_that(output).contains("3 passed")
        assert_that(output).does_not_contain("SnapshotKeyReusedWarning")

    def test_the_filters_turning_it_into_an_error_fail_the_run_not_the_hook(self, tmp_path):
        # `error` in the filters raises the sweep's warning inside session finish, and pytest renders an
        # exception from there as an INTERNALERROR: exit code aside, the reader gets this plugin's
        # traceback instead of the snapshot that needs fixing. only a real run shows which one it is
        result = self._run(tmp_path, '"one-key"', "-W", "error::assertpy2.SnapshotKeyReusedWarning")
        assert_that(result.stdout).does_not_contain("INTERNALERROR")
        assert_that(result.stdout).contains("ERROR: snapshot key").contains("shared by 3 tests")
        # the tests themselves have to pass: without this the check below is happy with a run that went
        # red for any other reason, which is how a broken environment reads as a working sweep
        assert_that(result.stdout).contains("3 passed")
        assert_that(result.returncode).is_equal_to(1)
