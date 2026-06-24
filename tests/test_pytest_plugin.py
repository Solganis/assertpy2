import contextlib
import json
import warnings
from unittest.mock import MagicMock, patch

import pytest

from assertpy2 import assert_that, match
from assertpy2.errors import AssertionFailure, DiffEntry, DiffResult
from assertpy2.pytest_plugin import (
    _diff_to_json,
    pytest_addoption,
    pytest_configure,
    pytest_runtest_makereport,
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
        assert_that(body).contains("'foo'")
        assert_that(body).contains("'bar'")

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

    def test_returns_valid_json(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="a", actual=1, expected=2)])
        result = json.loads(_diff_to_json(diff))
        assert_that(result["kind"]).is_equal_to("dict")
        assert_that(result["entries"]).is_length(1)
        assert_that(result["entries"][0]["path"]).is_equal_to("a")
        assert_that(result["entries"][0]["actual"]).is_equal_to("1")
        assert_that(result["entries"][0]["expected"]).is_equal_to("2")

    def test_preserves_repr_format(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual="<b>", expected="&")])
        result = json.loads(_diff_to_json(diff))
        assert_that(result["entries"][0]["actual"]).is_equal_to("'<b>'")
        assert_that(result["entries"][0]["expected"]).is_equal_to("'&'")

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
        assert_that(actuals["role"]).is_equal_to("'superadmin'")
        assert_that(actuals["email"]).is_equal_to("<missing>")


class TestAllureFullMode:
    def test_actual_expected_when_full(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual=1, expected=2)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        assert_that(mock.attach.call_count).is_equal_to(1)
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body).is_equal_to({"actual": "1", "expected": "2"})
        assert_that(mock.attach.call_args_list[0].kwargs["name"]).is_equal_to("AssertionFailure")
        assert_that(mock.attach.call_args_list[0].kwargs["attachment_type"]).is_equal_to("json")

    def test_only_actual_when_full(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual=42)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body).is_equal_to({"actual": "42"})

    def test_only_expected_when_full(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", expected="abc")
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body).is_equal_to({"expected": "'abc'"})

    def test_repr_preserves_types(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual={"a": 1}, expected=[1, 2])
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body["actual"]).is_equal_to("{'a': 1}")
        assert_that(body["expected"]).is_equal_to("[1, 2]")

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


class TestPytestConfigure:
    def test_valid_mode_stored(self):
        config = MagicMock()
        config.getini.return_value = "full"
        pytest_configure(config)
        assert_that(config._assertpy2_allure_mode).is_equal_to("full")

    def test_default_diff_mode_stored(self):
        config = MagicMock()
        config.getini.return_value = "diff"
        pytest_configure(config)
        assert_that(config._assertpy2_allure_mode).is_equal_to("diff")

    def test_invalid_mode_warns_and_falls_back(self):
        config = MagicMock()
        config.getini.return_value = "unknown"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_configure(config)
        assert_that(config._assertpy2_allure_mode).is_equal_to("diff")
        assert_that(caught).is_length(1)
        assert_that(str(caught[0].message)).contains("unknown")


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
