import contextlib
import json
import os
import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from assertpy2 import assert_that, match
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
        assert_that(parser.addini.call_count).is_equal_to(3)
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

    def test_depth_cap_degrades_to_repr_marker(self):
        nested = {"level": 1}
        for _ in range(8):
            nested = {"level": nested}
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


def _make_config(*, ini="diff", snapshot_update=False):
    # a bare MagicMock returns a truthy mock from getoption(), which would flip the snapshot-update
    # module flag and leak update mode into unrelated tests
    config = MagicMock()
    config.getini.return_value = ini
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
