import contextlib
import json
import os
import subprocess
import sys
import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from _pytest.config.argparsing import Parser

from assertpy2 import _clustering, assert_that, async_assertions, match
from assertpy2 import _satisfies as _satisfies_module
from assertpy2 import errors as errors_module
from assertpy2 import pytest_plugin as pytest_plugin
from assertpy2 import snapshot as snapshot_module
from assertpy2._clustering import Observation, Signature
from assertpy2.errors import AssertionFailure, DiffEntry, DiffResult, PollSample, PollTrace
from assertpy2.pytest_plugin import (
    _PROFILES,
    _diff_to_json,
    _escalate,
    _format_trace,
    _is_full_run,
    _json_safe,
    _setting,
    _trace_to_json,
    _vacuous_guard,
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
        assert_that(parser.addini.call_count).is_equal_to(9)
        names = [call[0][0] for call in parser.addini.call_args_list]
        assert_that(names).contains("assertpy2_allure")
        assert_that(names).contains("assertpy2_diff")
        assert_that(names).contains("assertpy2_diff_max_entries")
        assert_that(names).contains("assertpy2_failure_clusters")
        assert_that(names).contains("assertpy2_dangling")
        assert_that(names).contains("assertpy2_dangling_entries")
        assert_that(names).contains("assertpy2_profile")
        assert_that(names).contains("assertpy2_vacuous")
        # the two a profile answers for carry no default, so `_setting` tells "wrote off" from "wrote nothing"
        defaults = {call[0][0]: call[1].get("default") for call in parser.addini.call_args_list}
        assert_that([defaults[name] for name in ("assertpy2_dangling", "assertpy2_vacuous")]).is_equal_to(["", ""])
        assert_that(defaults["assertpy2_failure_clusters"]).described_as(
            "clustering answers for itself, so it carries a real default rather than a profile's"
        ).is_equal_to(str(_clustering.MINIMUM_SIZE))
        assert_that(defaults["assertpy2_profile"]).is_equal_to("compatible")


class TestTheProfileAnswersForWhatTheSuiteDidNotName:
    """One line of config instead of three, and the three keep working on their own.

    The guards a new suite wants are the ones an inherited suite must not get without asking: each can
    turn a green run red.  So `compatible` is the default and `safe` is the line that turns them on,
    rather than the defaults moving under everybody.

    Failure clustering is deliberately not one of them.  It is asked for by name or not at all, and its
    default is on, because it reads a run that already failed and costs a passing one nothing.
    """

    @staticmethod
    def _config(**written):
        return SimpleNamespace(getini=lambda name: written.get(name, ""), getoption=lambda name: False)

    def test_an_unnamed_setting_takes_its_profile_answer(self):
        compatible, safe = self._config(), self._config(assertpy2_profile="safe")
        assert_that(_setting(compatible, "assertpy2_dangling")).is_equal_to("off")
        assert_that(_setting(safe, "assertpy2_dangling")).is_equal_to("on")
        assert_that(_setting(safe, "assertpy2_vacuous")).is_equal_to("on")

    def test_no_profile_answers_for_failure_clustering(self):
        """The separation itself, which a table with a third key would quietly undo.

        Clustering is on by default, so a profile listing it could only ever turn it off, and the one
        that would is `compatible`.  That is the bundling this was pulled out of: `compatible` speaks
        for what a guard costs a passing suite, and clustering costs one nothing.
        """
        for profile in _PROFILES.values():
            assert_that(profile).does_not_contain_key("assertpy2_failure_clusters")

    def test_a_named_setting_wins_over_the_profile(self):
        config = self._config(assertpy2_profile="safe", assertpy2_dangling="off")
        assert_that(_setting(config, "assertpy2_dangling")).described_as(
            "a suite that named a setting has said what it wants, whatever profile it picked"
        ).is_equal_to("off")
        assert_that(_setting(config, "assertpy2_vacuous")).is_equal_to("on")

    def test_only_strict_writes_the_two_filters(self):
        """The wiring itself, called directly.

        The profile tests below drive a real run in a child process, where nothing measures this
        module, so the lines that add the filters would otherwise be held by nothing.
        """
        written = []
        for profile in ("compatible", "safe", "strict"):
            config = SimpleNamespace(
                getini=lambda name, profile=profile: {"assertpy2_profile": profile}.get(name, ""),
                getoption=lambda name: False,
                addinivalue_line=lambda name, value: written.append((name, value)),
            )
            _escalate(config)
        assert_that(written).described_as("only `strict` escalates, and only its own two").is_equal_to(
            [
                ("filterwarnings", "error::assertpy2.errors.DanglingAssertionWarning"),
                ("filterwarnings", "error::assertpy2.errors.VacuousAssertionWarning"),
            ]
        )

    def test_a_profile_nobody_declared_is_refused_and_named(self):
        config = self._config(assertpy2_profile="paranoid")
        with pytest.warns(UserWarning, match="assertpy2_profile='paranoid' is not one of"):
            assert_that(_setting(config, "assertpy2_dangling")).is_equal_to("off")

    def test_a_mistyped_guard_setting_falls_back_to_the_profile_rather_than_to_off(self):
        """`off` is the answer that hides a mistake, so a value nobody declared must not read as one."""
        config = self._config(assertpy2_profile="safe", assertpy2_vacuous="onn")
        with pytest.warns(UserWarning, match="assertpy2_vacuous='onn' is not 'on' or 'off'"):
            assert_that(_vacuous_guard(config)).is_true()

    def test_a_profile_nobody_declared_is_named_once_rather_than_per_question(self):
        """Both settings ask, and one mistake is one mistake however many of them looked."""
        config = self._config(assertpy2_profile="paranoid")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for name in ("assertpy2_dangling", "assertpy2_vacuous"):
                _setting(config, name)
        assert_that([str(one.message) for one in caught]).is_length(1)


class TestTheProfileFromAConfigFile:
    """The profile as a suite meets it: a config file, a run, and what it says.

    The three tests above hold `_setting()`, which is the resolution and not the wiring.  A refactor
    that stopped `pytest_configure` calling it would leave every one of them green while the profile
    did nothing at all, so this one writes the config and reads the warnings out of a real run.
    """

    _SUITE = (
        "from assertpy2 import assert_that\n\n\n"
        "def test_dangling_statement():\n    assert_that(1)\n\n\n"
        "def test_vacuous_quantifier():\n    assert_that([]).all_satisfy(lambda item: False)\n"
    )

    def _run(self, tmp_path, *settings, **environment):
        (tmp_path / "test_guards.py").write_text(self._SUITE, encoding="utf-8")
        (tmp_path / "pytest.ini").write_text("\n".join(["[pytest]", *settings, ""]), encoding="utf-8")
        return subprocess.run(
            # this interpreter, not `uv run`: the child starts in `tmp_path`, outside the project, where `uv run`
            # resolves whatever it finds. A 3.10 check answered from 3.14 with no plugin installed
            [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=180,
            # one of the three ways to ask for the vacuous guard, so a machine carrying it would answer for the suite
            env={**{key: value for key, value in os.environ.items() if key != "ASSERTPY2_VACUOUS"}, **environment},
        )

    @staticmethod
    def _reported(result):
        """The child's stdout, once the child is known to have run at all.

        Every case here reads stdout, and two of them read it for an absence: a child that died on
        startup prints no warning either, and would pass them both.
        """
        assert_that(result.returncode).described_as(f"the child run failed: {result.stderr}").is_equal_to(0)
        return assert_that(result.stdout).described_as(
            f"exit {result.returncode}, child stderr: {result.stderr.strip() or 'empty'}"
        )

    def test_the_default_leaves_a_run_as_it_found_it(self, tmp_path):
        result = self._run(tmp_path)
        self._reported(result).does_not_contain("DanglingAssertionWarning", "VacuousAssertionWarning")

    def test_the_safe_profile_turns_both_warnings_on(self, tmp_path):
        result = self._run(tmp_path, "assertpy2_profile = safe")
        self._reported(result).contains("DanglingAssertionWarning", "VacuousAssertionWarning")

    def test_a_named_setting_wins_over_the_profile_in_a_real_run(self, tmp_path):
        result = self._run(tmp_path, "assertpy2_profile = safe", "assertpy2_dangling = off")
        self._reported(result).does_not_contain("DanglingAssertionWarning")
        self._reported(result).contains("VacuousAssertionWarning")

    def test_the_safe_profile_leaves_the_run_green(self, tmp_path):
        """What separates `safe` from `strict`, and the reason both exist.

        `safe` shows a suite what it has.  A run full of findings still exits zero, which is a fair
        first look and a poor gate.
        """
        result = self._run(tmp_path, "assertpy2_profile = safe")
        assert_that(result.returncode).described_as("warnings alone do not fail a run").is_equal_to(0)

    def test_the_strict_profile_fails_the_run(self, tmp_path):
        result = self._run(tmp_path, "assertpy2_profile = strict")
        assert_that(result.returncode).described_as(f"strict left the run green: {result.stdout}").is_not_equal_to(0)

    def test_strict_reports_each_finding_where_it_arrives(self, tmp_path):
        """A dangling finding is reported at setup, a vacuous one while the assertion runs.

        The chain is found while the module is collected, but the warning is raised from
        `pytest_runtest_setup`, which is why pytest calls it a setup error rather than a failure.
        Pinned because a reader who expects two failures and is shown one of each will think the plugin
        broke.
        """
        result = self._run(tmp_path, "assertpy2_profile = strict")
        assert_that(result.stdout).described_as("the dangling one, found at collection").contains(
            "ERROR test_guards.py::test_dangling_statement"
        )
        assert_that(result.stdout).described_as("the vacuous one, found while running").contains(
            "FAILED test_guards.py::test_vacuous_quantifier"
        )

    def test_a_named_setting_still_wins_under_strict(self, tmp_path):
        """`strict` escalates the guards that are on, not the ones the suite turned off."""
        result = self._run(tmp_path, "assertpy2_profile = strict", "assertpy2_dangling = off")
        assert_that(result.stdout).does_not_contain("ERROR test_guards.py::test_dangling_statement")
        assert_that(result.stdout).contains("FAILED test_guards.py::test_vacuous_quantifier")

    def test_strict_leaves_another_library_s_warnings_alone(self, tmp_path):
        """Why this is not `filterwarnings = error`.

        A blanket escalation would fail a test for somebody else's `DeprecationWarning`, which is a
        change to the suite this library was never asked to make.
        """
        (tmp_path / "test_neighbour.py").write_text(
            "import warnings\n\n\n"
            "def test_someone_else_warns():\n"
            "    warnings.warn('unrelated', DeprecationWarning, stacklevel=1)\n",
            encoding="utf-8",
        )
        result = self._run(tmp_path, "assertpy2_profile = strict")
        assert_that(result.stdout).does_not_contain("FAILED test_neighbour.py")

    def test_a_value_the_setting_does_not_know_is_refused_rather_than_read_as_off(self, tmp_path):
        """A guard whose setting was mistyped must not go quiet: the quiet answer is the dangerous one.

        The refusal is written at configure time, which is before pytest owns the streams, so it lands
        on stderr while the guard's own warning reaches the report.
        """
        result = self._run(tmp_path, "assertpy2_profile = safe", "assertpy2_vacuous = onn")
        self._reported(result).contains("VacuousAssertionWarning")
        assert_that(result.stderr).described_as("the mistyped setting, refused by name").contains(
            "assertpy2_vacuous='onn' is not 'on' or 'off'"
        )

    def test_the_environment_cannot_outrank_a_suite_that_said_off(self, tmp_path):
        """The variable asks for the guard away from pytest, and a config file is the louder voice."""
        result = self._run(tmp_path, "assertpy2_vacuous = off", ASSERTPY2_VACUOUS="1")
        self._reported(result).does_not_contain("VacuousAssertionWarning")


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


class TestTheValuesSectionShowsOnlyValuesTheAssertionNamed:
    """Every failure carries `actual` now, so "the attribute is set" stopped meaning "the reader has
    not seen this value yet".

    The section exists for values the message elided. A value filled in from the builder is the same
    one the message opens with, so rendering it would put a repeat under every single failure. The
    three tests above still construct the exception by hand, which is the case with no record at all,
    and those keep the older behaviour.
    """

    def test_a_failure_that_never_named_actual_gets_no_values_section(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).contains_key("x")
        report = _make_report()
        _run_hook(report, _make_call(exc=failure.value))
        titles = [title for title, _ in report.sections]
        assert_that(failure.value.actual).is_equal_to({"a": 1})
        assert_that(titles).does_not_contain("AssertionFailure")

    def test_a_failure_that_named_its_values_still_gets_one(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).is_equal_to({"a": 2})
        report = _make_report()
        _run_hook(report, _make_call(exc=failure.value))
        body = dict(report.sections)["AssertionFailure"]
        assert_that(body).contains("actual")
        assert_that(body).contains("expected")

    def test_an_expected_of_none_is_shown_rather_than_read_as_unset(self):
        # `expected is not None` cannot tell "compared against None" from "no expected at all"
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).is_equal_to(None)
        report = _make_report()
        _run_hook(report, _make_call(exc=failure.value))
        body = dict(report.sections)["AssertionFailure"]
        assert_that(body).contains("expected: None")


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
        diff = DiffResult(kind="sequence", entries=[DiffEntry(path="[1]", actual=99, expected=None, absent="expected")])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["Structured Diff"]
        assert_that(body).contains("[1]: - 99")

    def test_sequence_expected_only(self):
        diff = DiffResult(kind="sequence", entries=[DiffEntry(path="[2]", actual=None, absent="actual", expected=42)])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["Structured Diff"]
        assert_that(body).contains("[2]: + 42")

    def test_set_extra_and_missing(self):
        diff = DiffResult(
            kind="set",
            entries=[
                DiffEntry(path="extra", actual=5, expected=None, absent="expected"),
                DiffEntry(path="missing", actual=None, absent="actual", expected=10),
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
        assert_that(body).contains("foo")
        assert_that(body).contains("bar")

    def test_set_extra_only(self):
        diff = DiffResult(kind="set", entries=[DiffEntry(path="extra", actual=5, expected=None, absent="expected")])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(report.sections)["Structured Diff"]
        assert_that(body).contains("extra:")
        assert_that(body).does_not_contain("missing")

    def test_set_missing_only(self):
        diff = DiffResult(kind="set", entries=[DiffEntry(path="missing", actual=None, absent="actual", expected=10)])
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
        # consumers branch on it: 1 repr strings, 2 typed values, 3 a named absent side, 4 a machine-readable path
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="a", actual=1, expected=2)])
        assert_that(json.loads(_diff_to_json(diff))["format"]).is_equal_to(4)

    def test_an_entry_carries_the_steps_that_reached_it(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"users": [{"roles": {7: "admin"}}]}).is_equal_to({"users": [{"roles": {7: "guest"}}]})
        entry = json.loads(_diff_to_json(failure.value.diff))["entries"][0]
        assert_that(entry["path"]).is_equal_to("users[0].roles.7")
        assert_that(entry["steps"]).is_equal_to(
            [
                {"kind": "key", "value": "users"},
                {"kind": "index", "value": 0},
                {"kind": "key", "value": "roles"},
                {"kind": "key", "value": 7},
            ]
        )

    def test_a_step_names_its_side_only_where_the_two_have_shifted_apart(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that([1, 2, 3, 4]).is_equal_to([0, 1, 2, 3, 4])
        entries = json.loads(_diff_to_json(failure.value.diff))["entries"]
        sided = [step for entry in entries for step in entry.get("steps", []) if "side" in step]
        assert_that(sided).is_not_empty()
        assert_that({step["side"] for step in sided}).is_subset_of({"actual", "expected"})

    def test_an_entry_with_no_location_carries_no_steps(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path=".", actual=1, expected=2)])
        assert_that(json.loads(_diff_to_json(diff))["entries"][0]).does_not_contain_key("steps")

    def test_a_step_value_that_json_cannot_express_degrades_rather_than_failing(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({(1, 2): "a"}).is_equal_to({(1, 2): "b"})
        step = json.loads(_diff_to_json(failure.value.diff))["entries"][0]["steps"][0]
        assert_that(step["kind"]).is_equal_to("key")
        assert_that(step["value"]).is_equal_to([1, 2])

    def test_an_absent_side_is_named_in_the_payload(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="b", actual=2, expected=None, absent="expected")])
        assert_that(json.loads(_diff_to_json(diff))["entries"][0]["absent"]).is_equal_to("expected")

    def test_a_value_that_is_none_carries_no_absent_key(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="a", actual=1, expected=None)])
        entry = json.loads(_diff_to_json(diff))["entries"][0]
        assert_that(entry).does_not_contain_key("absent")
        assert_that(entry["expected"]).is_none()

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
        assert_that(_json_safe({(1, 2)})).is_equal_to({"__type__": "set", "__data__": [[1, 2]]})

    def test_a_heterogeneous_set_sorts_by_repr(self):
        assert_that(_json_safe({1, "a"})).is_equal_to({"__type__": "set", "__data__": ["a", 1]})
        assert_that(_json_safe({2, 10})["__data__"]).is_equal_to([10, 2])

    def test_depth_cap_degrades_to_repr_marker(self):
        nested = {"level": 1}
        for _ in range(8):
            nested = {"level": nested}
        blob = json.dumps(_json_safe(nested))
        assert_that(blob).contains("__repr__")

    def test_the_depth_cap_holds_for_sequences_too(self):
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

    def test_a_failure_with_no_diff_at_all_still_attaches_its_expected(self):
        """The case the sibling below does not reach: `contains_key` carries a diff, and a diff is its
        own reason to go on.  `is_true()` has neither a diff nor an actual of its own, so it is the one
        that says whether the early exit reads the record's flags or the terminal section's rule.
        """
        mock = _mock_allure()
        with pytest.raises(AssertionFailure) as failure:
            assert_that(0).is_true()
        report = _make_report()
        _run_hook_with_allure(report, _make_call(exc=failure.value), mock, allure_mode="full")
        attached = {call.kwargs["name"]: call.kwargs["body"] for call in mock.attach.call_args_list}
        assert_that(json.loads(attached["AssertionFailure"])).is_equal_to({"format": 2, "expected": True})
        assert_that([title for title, _ in report.sections]).described_as(
            "the terminal stays quiet: the message already says what was expected"
        ).does_not_contain("AssertionFailure")

    def test_a_failure_that_named_only_an_expected_still_attaches_it(self):
        """Full mode is data, so the rule that keeps the terminal from repeating itself does not apply.

        The terminal section shows values the message did not, and every assertion names an expected
        now, so `expected` alone stopped meaning "the reader has not seen this".  A dashboard reading
        the attachment is in the other position: the message is prose to it, and the field is the value.
        """
        mock = _mock_allure()
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).contains_key("x")
        _run_hook_with_allure(_make_report(), _make_call(exc=failure.value), mock, allure_mode="full")
        attached = {call.kwargs["name"]: call.kwargs["body"] for call in mock.attach.call_args_list}
        assert_that(attached).contains_key("AssertionFailure", "Structured Diff")
        body = json.loads(attached["AssertionFailure"])
        assert_that(body).is_equal_to({"format": 2, "expected": ["x"]})

    def test_an_expected_of_none_is_attached_rather_than_read_as_unset(self):
        mock = _mock_allure()
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).is_equal_to(None)
        _run_hook_with_allure(_make_report(), _make_call(exc=failure.value), mock, allure_mode="full")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body).contains_key("expected")
        assert_that(body["expected"]).is_none()


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


def _make_config(
    *,
    ini="diff",
    snapshot_update=False,
    poll_report="0.7",
    clusters="3",
    dangling="off",
    entries=(),
    profile="compatible",
    vacuous="off",
):
    config = MagicMock()
    # every key answered by name: a catch-all fed the allure mode to every other reader, and a guard was
    # handed `diff` for its own setting and refused it as a value it does not know
    per_key = {
        "assertpy2_allure": ini,
        "assertpy2_diff": "on",
        "assertpy2_diff_max_entries": "50",
        "assertpy2_poll_report": poll_report,
        "assertpy2_failure_clusters": clusters,
        "assertpy2_dangling": dangling,
        "assertpy2_dangling_entries": entries,
        "assertpy2_profile": profile,
        "assertpy2_vacuous": vacuous,
    }

    def answer(name):
        if name not in per_key:
            raise KeyError(f"{name} is read by the plugin and not answered by this fake config")
        return per_key[name]

    config.getini.side_effect = answer
    config.getoption.return_value = snapshot_update
    # the profile is cached here, and a mock answers an unset attribute with a mock, reading as a profile
    config._assertpy2_profile = None
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
        assert_that(str(caught[0].message)).contains("unknown").contains("(diff, full, off)")

    def test_configure_disables_diff_in_message_and_unconfigure_restores(self, monkeypatch):
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
        monkeypatch.setattr(snapshot_module, "_CI_MODE", True)
        config = _make_config()
        config.getoption.side_effect = lambda name: name == "assertpy2_snapshot_no_ci"
        pytest_configure(config)
        assert_that(snapshot_module._CI_MODE).is_false()
        pytest_unconfigure(config)
        assert_that(snapshot_module._CI_MODE).is_none()


def _controller_config(reporter, *, full=True):
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

    def test_testnodedown_collects_worker_failures(self):
        pytest_plugin._controller_failures.clear()
        pytest_plugin._controller_failure_count[0] = 0
        node = SimpleNamespace(
            gateway=SimpleNamespace(id="gw3"),
            workeroutput={
                "assertpy2_failures": [
                    [
                        "t.py::test_x",
                        [[True, "user.role", [["key", "'user'"], ["key", "'role'"]], "", [], "'s'", "'a'"]],
                    ]
                ],
                "assertpy2_failure_count": 7,
            },
        )
        pytest_testnodedown(node, None)
        assert_that(pytest_plugin._controller_failures).is_length(1)
        assert_that(pytest_plugin._controller_failure_count[0]).is_equal_to(7)
        nodeid, found = pytest_plugin._controller_failures[0]
        assert_that(nodeid).is_equal_to("gw3::t.py::test_x")
        assert_that(found[0].signature.where).is_equal_to("user.role")
        pytest_plugin._controller_failures.clear()
        pytest_plugin._controller_failure_count[0] = 0

    def test_sessionfinish_ships_the_failures_a_worker_recorded(self):
        config = SimpleNamespace(
            workeroutput={},
            _assertpy2_failures=[("t.py::test_x", [Observation(Signature(True, "a.b", (("key", "'a'"),)), "1", "2")])],
            _assertpy2_failure_count=4,
        )
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy2_failure_count"]).is_equal_to(4)
        assert_that(config.workeroutput["assertpy2_failures"][0][0]).is_equal_to("t.py::test_x")

    def test_testnodedown_ignores_node_without_touches(self):
        pytest_plugin._controller_touched.clear()
        pytest_testnodedown(SimpleNamespace(workeroutput={}), None)
        assert_that(pytest_plugin._controller_touched).is_empty()

    def test_the_prune_locks_the_file_it_rewrites(self, tmp_path, monkeypatch):
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
        assert_that(_is_full_run(config(file_or_dir=["tests/test_x.py::test_a"]))).is_false()
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
        assert_that(json.loads((tmp_path / "snap-mod.json").read_text())).contains_key("30")

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
        assert_that(json.loads((tmp_path / "snap-mod.json").read_text())).does_not_contain_key("30")

    def test_no_prune_on_filtered_run(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", True)
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter, full=False)), 0)
        assert_that(json.loads((tmp_path / "snap-mod.json").read_text())).contains_key("30")

    def test_no_prune_on_nodeid_selected_run(self, tmp_path, monkeypatch):
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
        assert_that(json.loads((tmp_path / "snap-mod.json").read_text())).contains_key("30")

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
        assert_that(os.path.isfile(dead)).is_true()
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


@pytest.fixture
def _clean_registries(monkeypatch):
    """The snapshot access registries are module-level, so a test that fills them has to empty them."""
    monkeypatch.setattr(snapshot_module, "_ACCESS_NODES", {})
    monkeypatch.setattr(snapshot_module, "_ACCESS_SITES", {})
    monkeypatch.setattr(snapshot_module, "_WARNED", set())
    monkeypatch.setattr(snapshot_module, "_TOUCHED", set())
    monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", "test_mod.py::test_a")
    pytest_plugin._controller_accesses.clear()
    yield
    pytest_plugin._controller_accesses.clear()


@pytest.mark.usefixtures("_clean_registries")
class TestSnapshotKeyReuseWarning:
    """One key reached by two tests means only the first one's value was ever asserted."""

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
        assert_that(str(caught[0].message)).contains("test_mod.py:17").contains("reached by more than one test")
        assert_that(str(caught[0].message)).does_not_contain("shared by")
        assert_that(str(caught[0].message)).contains("snapshot(id=...)")

    def test_the_warning_points_at_the_line_that_reused_the_key(self, monkeypatch, tmp_path):
        # `catch_warnings` records the message, not where pytest attributes it, so the stack level could drift
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
        assert_that(snapshot_module._TOUCHED).contains(("/x/snap.json", "17"))

    def test_a_custom_id_reads_as_a_whole_file(self, monkeypatch):
        snapshot_module._record_access("/x/snap.json", "", "id='payload'")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", "test_mod.py::test_b")
            snapshot_module._record_access("/x/snap.json", "", "id='payload'")
        assert_that(str(caught[0].message)).contains("<whole file>").contains("id='payload'")

    def test_worker_ships_node_ids_and_the_controller_unions_them(self):
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
        assert_that(reported[0]).contains("shared by 2 tests").does_not_contain("at least")

    def test_the_sweep_counts_a_key_a_test_already_reported(self):
        snapshot_module._WARNED.add(("/x/s.json", "9"))
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b", "test_c"}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_sessionfinish(SimpleNamespace(config=_controller_config(MagicMock())), 0)
        reported = [str(w.message) for w in caught if w.category is snapshot_module.SnapshotKeyReusedWarning]
        assert_that(reported).is_length(1)
        assert_that(reported[0]).contains("shared by 3 tests")

    def test_a_key_reached_once_does_not_stop_the_sweep(self):
        pytest_plugin._controller_accesses[("/x/a.json", "1")] = {"test_a"}
        pytest_plugin._controller_accesses[("/x/b.json", "9")] = {"test_a", "test_b"}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_sessionfinish(SimpleNamespace(config=_controller_config(MagicMock())), 0)
        reported = [str(w.message) for w in caught if w.category is snapshot_module.SnapshotKeyReusedWarning]
        assert_that(reported).is_length(1)
        assert_that(reported[0]).contains("/x/b.json")

    def test_an_escalated_sweep_warning_fails_the_run_rather_than_the_hook(self):
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
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        reporter = MagicMock()
        session = SimpleNamespace(config=_controller_config(reporter), exitstatus=pytest.ExitCode.INTERRUPTED)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_sessionfinish(session, 0)
        assert_that(session.exitstatus).is_equal_to(pytest.ExitCode.INTERRUPTED)
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
        (tmp_path / "test_reuse.py").write_text(_SHARED_KEY_MODULE.format(id=snapshot_id), encoding="utf-8")
        try:
            return self._spawn(tmp_path, extra)
        except subprocess.TimeoutExpired as expired:
            raise AssertionError(
                f"the child run did not finish in {expired.timeout}s\n"
                f"stdout:\n{expired.stdout}\nstderr:\n{expired.stderr}"
            ) from expired

    def _spawn(self, tmp_path, extra):
        return subprocess.run(
            [
                "uv",
                "run",
                "--no-sync",
                "pytest",
                str(tmp_path / "test_reuse.py"),
                "-q",
                "--no-header",
                "--rootdir",
                str(tmp_path),
                "--confcutdir",
                str(tmp_path),
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

    @staticmethod
    def _report(result):
        """The child's stdout, with everything a failure here needs to be explainable attached.

        These checks read stdout and nothing else, so a child that failed to start, lost a worker or
        rebuilt its environment showed up only as text that did not match. The reason was in the
        captured stderr, which no assertion ever surfaced.
        """
        context = f"exit {result.returncode}, child stderr:\n{result.stderr.strip() or '<empty>'}\n"
        return assert_that(result.stdout).described_as(context)

    def test_one_key_split_across_workers_still_warns(self, tmp_path):
        report = self._report(self._run(tmp_path, '"one-key"'))
        report.contains("3 passed")
        report.contains("SnapshotKeyReusedWarning").contains("shared by 3 tests")
        report.contains("pytest_plugin.py")

    def test_a_key_per_case_stays_silent(self, tmp_path):
        report = self._report(self._run(tmp_path, 'f"key-{name}"'))
        report.contains("3 passed")
        report.does_not_contain("SnapshotKeyReusedWarning")

    def test_the_filters_turning_it_into_an_error_fail_the_run_not_the_hook(self, tmp_path):
        result = self._run(tmp_path, '"one-key"', "-W", "error::assertpy2.SnapshotKeyReusedWarning")
        report = self._report(result)
        report.does_not_contain("INTERNALERROR")
        report.contains("ERROR: snapshot key").contains("shared by 3 tests")
        report.contains("3 passed")
        assert_that(result.returncode).described_as(f"child stderr:\n{result.stderr}").is_equal_to(1)


def _registered_parser():
    """The plugin's options on the parser pytest itself hands to `pytest_addoption`.

    A `MagicMock` records any call at all, so it cannot tell a registration pytest accepts from one it
    refuses: an unknown action, an ini type outside the supported set, a missing help.
    """
    parser = Parser(_ispytest=True)
    pytest_addoption(parser)
    return parser


def _addoption_calls():
    """The switches as they were registered, which is where the action and the default are visible."""
    parser = MagicMock()
    pytest_addoption(parser)
    return parser.addoption.call_args_list


class _RegisteredConfig:
    """A config that answers only the keys the plugin registered, refusing others as pytest does."""

    def __init__(self, *, ini=None, options=None):
        parser = _registered_parser()
        self._ini = {name: spec[-1] for name, spec in parser._inidict.items()} | dict(ini or {})
        self._options = vars(parser.parse([])) | dict(options or {})

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(f"unknown configuration value: {name!r}")
        return self._ini[name]

    def getoption(self, name):
        if name not in self._options:
            raise ValueError(f"no option named {name!r}")
        return self._options[name]


def _configured_item(**settings):
    """An item whose config carries exactly the attributes named, as a real config would."""
    option = SimpleNamespace(**settings.pop("option", {}))
    return SimpleNamespace(config=SimpleNamespace(option=option, **settings))


def _diff_of(count):
    entries = [DiffEntry(path=f"k{index}", actual=index, expected=index + 1) for index in range(count)]
    return DiffResult(kind="dict", entries=entries)


def _one_sample_trace(**sample):
    base = {"elapsed": 0.0, "outcome": "fail", "value": 1, "detail": "d"}
    return PollTrace(samples=[PollSample(**(base | sample))], total_polls=1, dropped=0, elapsed=0.5, summary="s")


class TestTheOptionsRegisterWithPytestItself:
    """Every switch and ini key has to survive the parser pytest builds, not only a recording mock."""

    def test_the_switches_are_flags_the_parser_accepts_bare(self):
        options = _registered_parser().parse(["--assertpy2-dangling", "--assertpy2-snapshot-update"])
        assert_that(options.assertpy2_dangling).is_true()
        assert_that(options.assertpy2_snapshot_update).is_true()

    def test_every_switch_and_key_documents_itself(self):
        parser = _registered_parser()
        documented = [(option.names()[0], option.attrs().get("help")) for option in parser._anonymous.options]
        documented += [(name, spec[0]) for name, spec in parser._inidict.items()]
        assert_that([name for name, help_text in documented if not help_text]).is_empty()

    def test_the_wrapper_names_key_is_shell_split_rather_than_one_string(self):
        assert_that(_registered_parser()._inidict["assertpy2_dangling_entries"][1]).is_equal_to("args")

    def test_the_dangling_switch_is_opt_in_like_the_others(self):
        registered = {call[0][0]: call[1] for call in _addoption_calls()}
        assert_that(registered).contains_key("--assertpy2-dangling")
        assert_that(registered["--assertpy2-dangling"]).contains_entry({"action": "store_true"}, {"default": False})


class TestTheSettingsAProjectGets:
    """What `pytest_configure` reads, against a config that refuses a key it never registered."""

    def test_a_project_that_configures_nothing_gets_the_documented_defaults(self):
        config = _RegisteredConfig()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_configure(config)
        try:
            assert_that(config._assertpy2_allure_mode).is_equal_to("diff")
            assert_that(config._assertpy2_dangling_enabled).is_equal_to(False)
            assert_that(config._assertpy2_dangling_entries).is_equal_to(frozenset())
            assert_that(config._assertpy2_diff_enabled).is_equal_to(True)
            assert_that(config._assertpy2_diff_max).is_equal_to(50)
            assert_that(config._assertpy2_cluster_minimum).described_as(
                "clustering is the one report a project gets without configuring it"
            ).is_equal_to(_clustering.MINIMUM_SIZE)
            assert_that(config._assertpy2_poll_threshold).is_equal_to(0.7)
        finally:
            pytest_unconfigure(config)

    def test_a_blank_value_for_any_setting_leaves_the_run_alone(self):
        """An ini line written and left empty has to resolve to the default, in silence.

        A warning raised while resolving settings comes out of `pytest_configure`, and under `-W error`
        that is an INTERNALERROR rather than a message, since pytest is inside its own hook with nothing
        to attribute the failure to.  Three settings were found doing it: the poll report and the Allure
        mode took the run down that way, and failure clustering joined them the moment it stopped being
        answered by a profile.

        Written against every string setting rather than those three, because the one to get this wrong
        next is the one nobody thought to check.  It compares the whole resolved state rather than the
        silence, so a setting that stops warning and lands on the wrong value fails here too.
        """
        registered = _registered_parser()._inidict
        blank = {name: "" for name, spec in registered.items() if isinstance(spec[-1], str)}
        assert_that(blank).described_as("the settings an empty ini line can reach").is_not_empty()
        assert_that(self._resolved(blank)).described_as(
            "what a blank ini line resolved to, against what writing nothing resolves to"
        ).is_equal_to(self._resolved({}))

    @staticmethod
    def _resolved(ini):
        """Everything `pytest_configure` settled, from a config that carries these ini values.

        Configured and unconfigured inside the call rather than two at a time: the hooks save and
        restore module state, and a second config configured over the first would restore what the
        first had already changed.
        """
        config = _RegisteredConfig(ini=ini)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_configure(config)
        try:
            return {name: value for name, value in vars(config).items() if name.startswith("_assertpy2_")}
        finally:
            pytest_unconfigure(config)

    def test_every_key_reaches_the_setting_it_names(self):
        config = _RegisteredConfig(
            ini={
                "assertpy2_allure": "full",
                "assertpy2_dangling": "on",
                "assertpy2_dangling_entries": ["check_that"],
                "assertpy2_diff": "off",
                "assertpy2_diff_max_entries": "5",
                "assertpy2_failure_clusters": "4",
                "assertpy2_poll_report": "0.9",
            }
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_configure(config)
        try:
            assert_that(config._assertpy2_allure_mode).is_equal_to("full")
            assert_that(config._assertpy2_dangling_enabled).is_equal_to(True)
            assert_that(config._assertpy2_dangling_entries).is_equal_to(frozenset({"check_that"}))
            assert_that(config._assertpy2_diff_enabled).is_equal_to(False)
            assert_that(config._assertpy2_diff_max).is_equal_to(5)
            assert_that(config._assertpy2_cluster_minimum).is_equal_to(4)
            assert_that(config._assertpy2_poll_threshold).is_equal_to(0.9)
        finally:
            pytest_unconfigure(config)

    def test_an_unusable_entry_cap_falls_back_to_the_documented_fifty(self):
        config = _RegisteredConfig(ini={"assertpy2_diff_max_entries": "lots"})
        try:
            pytest_configure(config)
            assert_that(config._assertpy2_diff_max).is_equal_to(50)
        finally:
            pytest_unconfigure(config)

    def test_configure_opens_the_run_with_an_empty_ledger_and_claims_the_session(self):
        config = _RegisteredConfig()
        try:
            pytest_configure(config)
            assert_that(config._assertpy2_failures).is_equal_to([])
            assert_that(config._assertpy2_failure_count).is_equal_to(0)
            assert_that(pytest_plugin._session_config[0]).is_same_as(config)
        finally:
            pytest_unconfigure(config)

    def test_the_no_ci_switch_forces_ci_mode_off_rather_than_back_to_autodetection(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_CI_MODE", True)
        config = _RegisteredConfig(options={"assertpy2_snapshot_no_ci": True})
        try:
            pytest_configure(config)
            assert_that(snapshot_module._CI_MODE).is_equal_to(False)
        finally:
            pytest_unconfigure(config)
        assert_that(snapshot_module._CI_MODE).is_none()


class TestUnconfigureLeavesTheProcessAsItFoundIt:
    """A second session in the same process must not inherit the first one's state."""

    def test_the_diff_in_message_setting_goes_back_to_what_it_was_not_to_on(self, monkeypatch):
        monkeypatch.setattr(errors_module, "_RENDER_DIFF_IN_MESSAGE", False)
        config = _RegisteredConfig()
        pytest_configure(config)
        pytest_unconfigure(config)
        assert_that(errors_module._RENDER_DIFF_IN_MESSAGE).is_equal_to(False)

    def test_unconfigure_without_configure_leaves_the_diff_in_the_message(self, monkeypatch):
        monkeypatch.setattr(errors_module, "_RENDER_DIFF_IN_MESSAGE", False)
        pytest_unconfigure(SimpleNamespace(getoption=lambda name: False))
        assert_that(errors_module._RENDER_DIFF_IN_MESSAGE).is_equal_to(True)

    def test_poll_samples_stop_being_collected(self, monkeypatch):
        monkeypatch.setattr(async_assertions, "_COLLECT_RETRIES", False)
        config = _RegisteredConfig()
        pytest_configure(config)
        pytest_unconfigure(config)
        assert_that(async_assertions._COLLECT_RETRIES).is_false()

    def test_the_controller_tallies_are_released(self):
        pytest_plugin._controller_lost_workers[0] = 2
        pytest_plugin._controller_unreadable_workers[0] = 3
        pytest_plugin._controller_collect_errors[0] = 4
        pytest_plugin._controller_failure_count[0] = 5
        pytest_unconfigure(SimpleNamespace(getoption=lambda name: False))
        assert_that(
            [
                pytest_plugin._controller_lost_workers[0],
                pytest_plugin._controller_unreadable_workers[0],
                pytest_plugin._controller_collect_errors[0],
                pytest_plugin._controller_failure_count[0],
            ]
        ).is_equal_to([0, 0, 0, 0])

    def test_without_a_saved_value_the_vacuous_guard_comes_back_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("ASSERTPY2_VACUOUS", "1")
        monkeypatch.setattr(_satisfies_module, "_VACUOUS_GUARD", False)
        pytest_unconfigure(SimpleNamespace(getoption=lambda name: False))
        assert_that(_satisfies_module._VACUOUS_GUARD).is_true()


class TestTheBarsAtTheEdgeOfTheirRange:
    """Both parsers accept their extreme value rather than warning it away."""

    def test_a_poll_bar_of_one_means_only_a_poll_that_used_the_whole_budget(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert_that(pytest_plugin._poll_threshold("1.0")).is_equal_to(1.0)

    def test_a_cluster_of_two_is_a_cluster(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert_that(pytest_plugin._cluster_minimum("2")).is_equal_to(2)


class TestFullRunDetectionOnAStrippedDownConfig:
    """Every selector is read with a default, and only a namespace missing them can show it."""

    def test_a_run_whose_plugins_registered_none_of_the_selectors_is_still_a_full_run(self):
        assert_that(_is_full_run(SimpleNamespace(option=SimpleNamespace()))).is_true()


class TestTheNearTimeoutReportReachesTheTerminal:
    """The report goes to the terminal reporter by name, and measures a poll against its own budget."""

    @staticmethod
    def _lines(monkeypatch, rows, threshold=0.7):
        monkeypatch.setattr(pytest_plugin, "_retried", list(rows))
        reporter = MagicMock()
        config = SimpleNamespace(
            pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter if name == "terminalreporter" else None),
            _assertpy2_poll_threshold=threshold,
        )
        pytest_plugin._report_retries(config)
        return [call.args[0] for call in reporter.write_line.call_args_list]

    def test_the_report_names_itself_and_the_share_of_the_budget_the_poll_used(self, monkeypatch):
        lines = self._lines(monkeypatch, [("t.py::test_x", 7, 1.8, 2.0)])
        assert_that(lines[0]).described_as("held off the run's output by a blank line").is_empty()
        assert_that(lines).contains("assertpy2 polls that nearly timed out:")
        assert_that("\n".join(lines)).contains("90% of the budget")

    def test_a_poll_measured_against_its_own_budget_not_against_the_product(self, monkeypatch):
        assert_that(self._lines(monkeypatch, [("t.py::test_x", 3, 0.4, 2.0)])).is_empty()

    def test_a_poll_landing_exactly_on_the_bar_is_named(self, monkeypatch):
        lines = self._lines(monkeypatch, [("t.py::test_x", 3, 0.7, 1.0)])
        assert_that("\n".join(lines)).contains("t.py::test_x")


class TestTheDiffSectionReadsItsSettingsOffTheConfig:
    """Every setting the sections read comes off the config, including the defaults for a config
    that never went through configure."""

    def test_the_entry_cap_the_ini_set_reaches_the_section(self):
        report = _make_report()
        item = _configured_item(option={"color": "no"}, _assertpy2_diff_enabled=True, _assertpy2_diff_max=2)
        _run_hook(report, _make_call(exc=AssertionFailure("fail", diff=_diff_of(5))), item=item)
        assert_that(dict(report.sections)["Structured Diff"]).contains("and 3 more entries")

    def test_turning_the_sections_off_drops_both_the_diff_and_the_trace(self):
        report = _make_report()
        item = _configured_item(option={"color": "no"}, _assertpy2_diff_enabled=False, _assertpy2_diff_max=50)
        exc = AssertionFailure("fail", diff=_diff_of(5), trace=_make_trace())
        _run_hook(report, _make_call(exc=exc), item=item)
        assert_that([title for title, _ in report.sections]).does_not_contain("Structured Diff", "Polling Trace")

    def test_a_config_that_never_configured_still_gets_its_sections(self):
        report = _make_report()
        exc = AssertionFailure("fail", diff=_diff_of(51), trace=_make_trace())
        _run_hook(report, _make_call(exc=exc), item=_configured_item())
        body = dict(report.sections)
        assert_that(body).contains_key("Structured Diff", "Polling Trace")
        assert_that(body["Structured Diff"]).does_not_contain("\x1b[").contains("and 1 more entries")

    def test_a_terminal_that_takes_colour_gets_a_coloured_diff(self):
        report = _make_report()
        item = _configured_item(option={"color": "yes"}, _assertpy2_diff_enabled=True, _assertpy2_diff_max=50)
        _run_hook(report, _make_call(exc=AssertionFailure("fail", diff=_diff_of(5))), item=item)
        assert_that(dict(report.sections)["Structured Diff"]).contains("\x1b[")

    def test_a_terminal_without_colour_gets_none(self):
        report = _make_report()
        item = _configured_item(option={"color": "no"}, _assertpy2_diff_enabled=True, _assertpy2_diff_max=50)
        _run_hook(report, _make_call(exc=AssertionFailure("fail", diff=_diff_of(5))), item=item)
        assert_that(dict(report.sections)["Structured Diff"]).does_not_contain("\x1b[")


class TestTheAllureAttachmentReadsItsSettingsOffTheConfig:
    """The attachment reads the same settings, and survives an allure that raises."""

    def test_a_config_that_never_configured_attaches_in_diff_mode(self):
        mock = _mock_allure()
        item = _configured_item()
        exc = AssertionFailure("fail", actual=1, expected=2, diff=_diff_of(51))
        with (
            patch("assertpy2.pytest_plugin._HAS_ALLURE", True),
            patch("assertpy2.pytest_plugin.allure", mock, create=True),
        ):
            _run_hook(_make_report(), _make_call(exc=exc), item=item)
        names = [call.kwargs["name"] for call in mock.attach.call_args_list]
        assert_that(names).is_equal_to(["Structured Diff"])
        assert_that(json.loads(mock.attach.call_args_list[0].kwargs["body"])["truncated"]).is_equal_to(1)

    def test_the_entry_cap_the_ini_set_reaches_the_attachment(self):
        mock = _mock_allure()
        item = _configured_item(option={"color": "no"}, _assertpy2_allure_mode="diff", _assertpy2_diff_max=2)
        exc = AssertionFailure("fail", diff=_diff_of(5))
        with (
            patch("assertpy2.pytest_plugin._HAS_ALLURE", True),
            patch("assertpy2.pytest_plugin.allure", mock, create=True),
        ):
            _run_hook(_make_report(), _make_call(exc=exc), item=item)
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body["entries"]).is_length(2)
        assert_that(body["truncated"]).is_equal_to(3)

    def test_an_allure_that_raises_is_swallowed_where_it_happens(self):
        mock = _mock_allure()
        mock.attach.side_effect = RuntimeError("allure broken")
        report = _make_report()
        with (
            patch("assertpy2.pytest_plugin._HAS_ALLURE", True),
            patch("assertpy2.pytest_plugin.allure", mock, create=True),
        ):
            exc = AssertionFailure("f", actual=1, expected=2, diff=_diff_of(5))
            pytest_plugin._attach_report_sections(_make_item(), report, exc)
        assert_that(report.sections).is_length(2)


class TestTheValuesSectionOnAForeignException:
    """`actual` and friends are read off somebody else's `AssertionError`, which may carry only some."""

    def test_an_exception_carrying_only_actual_still_gets_its_section(self):
        exc = AssertionError("fail")
        exc.actual = 42
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        assert_that(dict(report.sections)["AssertionFailure"]).contains("42")

    def test_an_exception_carrying_only_a_diff_still_gets_its_section(self):
        exc = AssertionError("fail")
        exc.diff = _diff_of(5)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        assert_that(dict(report.sections)).contains_key("Structured Diff")

    def test_an_exception_carrying_only_a_trace_still_gets_its_section(self):
        exc = AssertionError("fail")
        exc.trace = _make_trace()
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        assert_that(dict(report.sections)).contains_key("Polling Trace")

    def test_the_pair_is_windowed_together_so_neither_side_is_dropped(self):
        exc = AssertionFailure("fail", actual="a" * 400 + "L", expected="a" * 400 + "R")
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        lines = dict(report.sections)["AssertionFailure"].splitlines()
        assert_that(lines).is_length(2)
        assert_that(lines[0].strip()).starts_with("actual:").contains("L")
        assert_that(lines[1].strip()).starts_with("expected:").contains("R")


class TestTheTerminalTimeline:
    """A repeat count is marked only where a sample was seen more than once, one line per sample."""

    def test_a_sample_seen_once_carries_no_repeat_count(self):
        lines = _format_trace(_one_sample_trace()).splitlines()
        assert_that(lines).is_length(2)
        assert_that(lines[1]).starts_with("  t=+").contains("fail: d")

    def test_a_sample_seen_twice_carries_one(self):
        assert_that(_format_trace(_one_sample_trace(repeats=2))).contains("fail x2: d")


class TestTheTraceAttachmentSchema:
    """The attachment is a documented wire format; a consumer branches on `format` and reads by name."""

    def test_every_field_a_consumer_reads_is_named(self):
        body = json.loads(_trace_to_json(_make_trace()))
        assert_that(body).contains_key("format", "kind", "total_polls", "elapsed", "summary", "samples")
        assert_that(body["samples"][0]).contains_key("t", "outcome", "detail", "repeats")
        assert_that(body["samples"][1]).contains_key("value")
        assert_that(body["deltas"][0]).contains_key("from_t", "to_t", "entries")

    def test_timings_are_rounded_to_the_millisecond(self):
        samples = [
            PollSample(elapsed=0.123456, outcome="fail", value=1, detail="d"),
            PollSample(elapsed=0.987654, outcome="fail", value=2, detail="d"),
        ]
        trace = PollTrace(samples=samples, total_polls=2, dropped=0, elapsed=1.234567, summary="s")
        body = json.loads(_trace_to_json(trace))
        assert_that(body["elapsed"]).is_equal_to(1.235)
        assert_that(body["samples"][0]["t"]).is_equal_to(0.123)
        assert_that(body["deltas"][0]["from_t"]).is_equal_to(0.123)
        assert_that(body["deltas"][0]["to_t"]).is_equal_to(0.988)

    def test_a_sample_seen_once_carries_its_value_and_no_repeat_count(self):
        sample = json.loads(_trace_to_json(_one_sample_trace()))["samples"][0]
        assert_that(sample["value"]).is_equal_to(1)
        assert_that(sample).does_not_contain_key("repeats")

    def test_an_unchanged_pair_is_skipped_without_ending_the_walk(self):
        samples = [
            PollSample(elapsed=0.0, outcome="fail", value=1, detail="d"),
            PollSample(elapsed=0.4, outcome="fail", value=1, detail="d"),
            PollSample(elapsed=0.8, outcome="fail", value=2, detail="d"),
        ]
        trace = PollTrace(samples=samples, total_polls=3, dropped=0, elapsed=1.0, summary="s")
        assert_that(json.loads(_trace_to_json(trace))["deltas"]).is_length(1)

    def test_a_non_ascii_detail_stays_readable_in_the_attachment(self):
        assert_that(_trace_to_json(_one_sample_trace(detail="значение"))).contains("значение")

    def test_the_attachment_is_indented_for_a_person_to_read(self):
        assert_that(_trace_to_json(_make_trace())).contains('\n  "')

    def test_a_sample_value_json_cannot_express_is_refused_rather_than_written(self):
        with pytest.raises(ValueError):
            _trace_to_json(_one_sample_trace(value=float("nan")))


class TestTheDiffAttachmentOnForeignObjects:
    """`diff` is read off somebody else's exception, so every field is asked for rather than assumed."""

    def test_an_entry_with_no_fields_at_all_degrades_rather_than_raising(self):
        assert_that(pytest_plugin._entry_to_json(SimpleNamespace())).is_equal_to(
            {"path": "", "actual": None, "expected": None}
        )

    def test_a_diff_without_entries_attaches_nothing(self):
        assert_that(_diff_to_json(SimpleNamespace())).is_none()

    def test_a_diff_that_does_not_name_its_kind_is_marked_unknown(self):
        diff = SimpleNamespace(entries=[DiffEntry(path="k", actual=1, expected=2)])
        assert_that(json.loads(_diff_to_json(diff))["kind"]).is_equal_to("unknown")

    def test_a_cap_of_zero_means_unlimited(self):
        assert_that(json.loads(_diff_to_json(_diff_of(5), max_entries=0))["entries"]).is_length(5)

    def test_a_cap_of_one_shows_one_and_counts_the_rest(self):
        body = json.loads(_diff_to_json(_diff_of(3), max_entries=1))
        assert_that(body["entries"]).is_length(1)
        assert_that(body["truncated"]).is_equal_to(2)

    def test_the_default_cap_is_the_documented_fifty(self):
        assert_that(json.loads(_diff_to_json(_diff_of(51)))["entries"]).is_length(50)

    def test_a_non_ascii_value_stays_readable_in_the_attachment(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual="значение", expected="✓")])
        assert_that(_diff_to_json(diff)).contains("значение").contains("✓")

    def test_the_attachment_is_indented_for_a_person_to_read(self):
        assert_that(_diff_to_json(_diff_of(2))).contains('\n  "')


class TestTheAllureBodiesCarryWhatTheyClaim:
    """The name alone left the body and the attachment type of every attachment unasserted."""

    @staticmethod
    def _attached(exc, *, mode="diff"):
        mock = _mock_allure()
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode=mode)
        return {call.kwargs["name"]: call.kwargs for call in mock.attach.call_args_list}

    def test_the_trace_attachment_carries_the_trace_as_typed_json(self):
        attached = self._attached(AssertionFailure("fail", trace=_make_trace()))["Polling Trace"]
        assert_that(attached["attachment_type"]).is_equal_to("json")
        assert_that(json.loads(attached["body"])["kind"]).is_equal_to("polling-trace")

    def test_a_non_ascii_value_stays_readable_in_the_values_attachment(self):
        exc = AssertionFailure("fail", actual="значение", expected="✓")
        assert_that(self._attached(exc, mode="full")["AssertionFailure"]["body"]).contains("значение").contains("✓")

    def test_the_values_attachment_is_indented_for_a_person_to_read(self):
        exc = AssertionFailure("fail", actual=1, expected=2)
        assert_that(self._attached(exc, mode="full")["AssertionFailure"]["body"]).contains('\n  "')


@pytest.mark.usefixtures("_clean_registries")
class TestTheSweepMessageIsActionable:
    """A count alone is not: the reader needs the key and the line that reached it."""

    @staticmethod
    def _swept():
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_sessionfinish(SimpleNamespace(config=_controller_config(MagicMock())), 0)
        return [str(one.message) for one in caught if one.category is snapshot_module.SnapshotKeyReusedWarning]

    def test_it_names_the_key_and_where_it_was_reached(self):
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        snapshot_module._ACCESS_SITES["/x/s.json", "9"] = "test_mod.py:9"
        assert_that(self._swept()[0]).contains("/x/s.json::9").contains("from test_mod.py:9")

    def test_a_key_whose_site_was_never_recorded_names_no_site(self):
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        assert_that(self._swept()[0]).contains("/x/s.json::9").does_not_contain(" from ")

    def test_the_escalated_warning_is_printed_in_red(self):
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        reporter = MagicMock()
        session = SimpleNamespace(config=_controller_config(reporter), exitstatus=0)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_sessionfinish(session, 0)
        written = reporter.write_line.call_args_list
        assert_that(written[0].args[0]).described_as("held off the run's output by a blank line").is_empty()
        error_line = [call for call in written if "ERROR" in str(call.args[0])]
        assert_that(error_line[0].kwargs).is_equal_to({"red": True})


@pytest.mark.usefixtures("_clean_registries")
class TestWhatAWorkerShipsWhenItRecordedNothing:
    """A worker that recorded nothing ships zeroes and empties, not invented values."""

    def test_a_worker_that_never_configured_ships_a_count_of_zero(self):
        config = SimpleNamespace(workeroutput={})
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy2_failure_count"]).is_equal_to(0)

    def test_an_access_whose_site_was_never_recorded_ships_an_empty_one(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_ACCESS_NODES", {("/x/s.json", "9"): {"t.py::test_a"}})
        monkeypatch.setattr(snapshot_module, "_ACCESS_SITES", {})
        config = SimpleNamespace(workeroutput={})
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy2_accesses"]).is_equal_to([["/x/s.json", "9", ["t.py::test_a"], ""]])


@pytest.mark.usefixtures("_clean_registries")
class TestTheSnapshotReportNamesItself:
    """The orphan block opens with a blank separator and its own heading, read line by line."""

    def test_the_orphan_report_carries_its_own_heading(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", False)
        monkeypatch.delenv("ASSERTPY2_SNAPSHOT_UPDATE", raising=False)
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter)), 0)
        lines = [call.args[0] for call in reporter.write_line.call_args_list]
        assert_that(lines[0]).described_as("held off the run's output by a blank line").is_empty()
        assert_that(lines).contains("assertpy2 snapshots:")
