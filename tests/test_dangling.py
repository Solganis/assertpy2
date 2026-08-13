"""The static check for `assert_that()` statements that assert nothing.

Both halves matter equally.  A check that misses the shape it exists for is useless, and a check that
reports a working chain gets switched off after the first false alarm and never switched back on, so
the negative cases below are the ones that keep it usable.
"""

from __future__ import annotations

import textwrap
import warnings
from types import SimpleNamespace

import pytest

from assertpy2 import DanglingAssertionWarning, assert_that
from assertpy2._dangling import _NO_ASSERTION, _NOT_CALLED, ALLOW_MARKER, findings
from assertpy2.pytest_plugin import (
    _dangling_enabled,
    _dangling_entries,
    _report_dangling,
    pytest_collection_modifyitems,
)

PREAMBLE = "from assertpy2 import assert_that, assert_warn, fail, soft_assertions\n"


def scan(body: str, preamble: str = PREAMBLE):
    return findings(preamble + textwrap.dedent(body), "sample.py")


class TestTheShapesItReports:
    def test_a_builder_built_and_thrown_away(self):
        found = scan("""
            def test_x():
                assert_that([1, 2, 3])
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NO_ASSERTION.format(name="assert_that"))
        assert_that(found[0].function).is_equal_to("test_x")

    def test_an_assertion_looked_up_and_never_called(self):
        found = scan("""
            def test_x():
                assert_that(1).is_equal_to
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NOT_CALLED)

    def test_a_longer_chain_that_is_never_called(self):
        found = scan("""
            def test_x():
                assert_that(1).not_.is_none
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NOT_CALLED)

    def test_assert_warn_is_an_entry_point_too(self):
        assert_that(scan("def test_x():\n    assert_warn('x')\n")).is_length(1)

    @pytest.mark.parametrize(
        ("preamble", "call"),
        [
            ("from assertpy2 import assert_that as at\n", "at(1)"),
            ("import assertpy2\n", "assertpy2.assert_that(1)"),
            ("import assertpy2 as ap\n", "ap.assert_that(1)"),
            ("from assertpy2 import *  # noqa: F403\n", "assert_that(1)  # noqa: F405"),
        ],
        ids=["aliased", "module", "aliased module", "star"],
    )
    def test_every_spelling_of_the_import_is_resolved(self, preamble, call):
        assert_that(scan(f"def test_x():\n    {call}\n", preamble)).is_length(1)

    def test_the_message_quotes_the_module_spelling_when_that_is_what_was_written(self):
        found = scan("def test_x():\n    ap.assert_that(1)\n", "import assertpy2 as ap\n")
        assert_that(found[0].message).is_equal_to(_NO_ASSERTION.format(name="ap.assert_that"))

    def test_a_finding_at_module_scope_names_no_function(self):
        found = scan("assert_that(1)\n")
        assert_that(found).is_length(1)
        assert_that(found[0].function).is_none()

    def test_a_nested_def_is_named_rather_than_its_parent(self):
        found = scan("""
            def test_x():
                def inner():
                    assert_that(1)
                inner()
            """)
        assert_that(found).extracting("function").is_equal_to(["inner"])

    def test_findings_come_back_in_source_order(self):
        found = scan("""
            def test_x():
                assert_that(2)
                assert_that(3)
            """)
        assert_that(found).extracting("lineno").is_equal_to(sorted(found and [f.lineno for f in found]))


class TestWhatItLeavesAlone:
    @pytest.mark.parametrize(
        "body",
        [
            "assert_that(1).is_equal_to(1)",
            "assert_that(lambda: None).raises(ValueError).when_called_with()",
            "assert_that([{'k': 1}]).extracting('k').is_equal_to([1])",
            "assert_that(assert_that('x')).is_instance_of(object)",
            "builder = assert_that(1)",
            "print(assert_that(1).value)",
            "fail('boom')",
            "return assert_that(1)",
        ],
        ids=[
            "terminal assertion",
            "pivot then assertion",
            "extracting then assertion",
            "builder as the value under test",
            "bound to a name",
            "read as a value",
            "a function that asserts on its own",
            "returned to the caller",
        ],
    )
    def test_working_usage_is_not_reported(self, body):
        assert_that(scan(f"def test_x():\n    {body}\n")).is_empty()

    def test_a_soft_block_is_not_reported(self):
        found = scan("""
            def test_x():
                with soft_assertions():
                    assert_that(1).is_equal_to(2)
            """)
        assert_that(found).is_empty()

    def test_a_module_that_never_imports_the_package_is_skipped(self):
        # somebody else's `assert_that` is not ours to judge
        assert_that(findings("def assert_that(x): ...\n\ndef test_x():\n    assert_that(1)\n", "other.py")).is_empty()

    def test_a_call_through_an_unrelated_module_is_not_ours(self):
        assert_that(scan("def test_x():\n    other.assert_that(1)\n", "import other\n")).is_empty()

    def test_an_attribute_statement_unrelated_to_the_builder_is_not_ours(self):
        assert_that(scan("def test_x():\n    self.value.attr\n")).is_empty()

    def test_a_chain_whose_head_is_a_call_on_something_else_is_not_ours(self):
        # the walk has to step through a Call node as well as Attributes before giving up
        assert_that(scan("def test_x():\n    helper(1).attr\n")).is_empty()

    def test_a_computed_callee_is_not_ours(self):
        # `funcs['assert_that'](1)` has no Name or Attribute to match, and guessing would be wrong
        assert_that(scan("def test_x():\n    funcs['assert_that'](1)\n")).is_empty()


class TestSilencingADeliberateOne:
    """Asserting nothing is sometimes the point: a benchmark measuring what a builder costs, a test of
    this library's own machinery. Without a per-line escape the only answer is turning the check off,
    and a check switched off wholesale is a check nobody runs.

    This project had exactly one such line, in its own benchmarks, found by widening the scan.
    """

    def test_a_marked_statement_is_left_out(self):
        found = scan("""
            def test_x():
                assert_that(1)  # assertpy2: allow-dangling
            """)
        assert_that(found).is_empty()

    def test_a_missing_call_can_be_marked_too(self):
        found = scan("""
            def test_x():
                assert_that(1).is_equal_to  # assertpy2: allow-dangling
            """)
        assert_that(found).is_empty()

    def test_the_marker_reaches_the_end_of_a_wrapped_call(self):
        # the natural place for it on a call broken over lines is the closing line
        found = scan("""
            def test_x():
                assert_that(
                    1
                )  # assertpy2: allow-dangling
            """)
        assert_that(found).is_empty()

    def test_it_silences_only_the_statement_it_sits_on(self):
        found = scan("""
            def test_x():
                assert_that(1)  # assertpy2: allow-dangling
                assert_that(2)
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].lineno).described_as("the unmarked line, not the marked one").is_equal_to(5)

    def test_the_constant_is_what_the_docs_tell_people_to_write(self):
        assert_that(ALLOW_MARKER).is_equal_to("assertpy2: allow-dangling")

    def test_a_bare_noqa_does_not_silence_it(self):
        # ruff's own suppression comment belongs to ruff: borrowing it would silence this check
        # by accident, and would also mean a line silenced for one tool is silenced for both
        found = scan("""
            def test_x():
                assert_that(1)  # noqa: F401
            """)
        assert_that(found).is_length(1)


class TestAwaitedChains:
    def test_an_awaited_dangling_builder_is_reported(self):
        found = scan("""
            async def test_x():
                await assert_that(1)
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].function).is_equal_to("test_x")

    def test_an_awaited_working_chain_is_not(self):
        found = scan("""
            async def test_x():
                await assert_that(1).eventually().is_equal_to(1)
            """)
        assert_that(found).is_empty()


def test_unparsable_source_raises_rather_than_reporting_nothing():
    # silently returning [] would read as a clean file
    with pytest.raises(SyntaxError):
        findings("def (:\n", "broken.py")


class TestAProjectsOwnWrapper:
    """Suites wrap `assert_that` in a helper of their own, and the check cannot see through it.

    `assertpy2_dangling_entries` names those helpers.  The name has to be bound by an import, which is
    the only thing standing between "your wrapper" and "any function anywhere that happens to be called
    `check`", so every negative case below is load-bearing.
    """

    WRAPPED = "from project.helpers import check\n"

    def test_an_unconfigured_wrapper_is_invisible(self):
        assert_that(scan("def test_x():\n    check(1)\n", self.WRAPPED)).is_empty()

    def test_a_configured_wrapper_reads_as_a_builder(self):
        found = findings(self.WRAPPED + "def test_x():\n    check(1)\n", "sample.py", frozenset({"check"}))
        assert_that(found).is_length(1)
        assert_that(found[0].message).described_as("named as the reader wrote it").is_equal_to(
            _NO_ASSERTION.format(name="check")
        )
        assert_that(found[0].function).is_equal_to("test_x")

    def test_a_configured_wrapper_that_does_assert_is_left_alone(self):
        found = findings(
            self.WRAPPED + "def test_x():\n    check(1).is_equal_to(1)\n", "sample.py", frozenset({"check"})
        )
        assert_that(found).is_empty()

    def test_a_missing_call_on_a_configured_wrapper_is_the_other_shape(self):
        found = findings(self.WRAPPED + "def test_x():\n    check(1).is_equal_to\n", "sample.py", frozenset({"check"}))
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NOT_CALLED)

    def test_an_alias_on_the_import_is_followed(self):
        source = "from project.helpers import check as verify\n\ndef test_x():\n    verify(1)\n"
        assert_that(findings(source, "sample.py", frozenset({"check"}))).is_length(1)

    def test_a_relative_import_of_the_wrapper_counts(self):
        source = "from .helpers import check\n\ndef test_x():\n    check(1)\n"
        assert_that(findings(source, "sample.py", frozenset({"check"}))).is_length(1)

    def test_a_local_function_of_the_same_name_is_not_claimed(self):
        # the guard that keeps this from becoming a linter for everybody's `check()`: no import, no claim
        source = "def check(value):\n    return value\n\n\ndef test_x():\n    check(1)\n"
        assert_that(findings(source, "sample.py", frozenset({"check"}))).is_empty()

    def test_reaching_the_wrapper_through_its_module_is_not_recognised(self):
        # a documented limit rather than an oversight: `helpers.check` would need the config to name a
        # module too, and every suite reached for `from ... import` instead
        source = "import project.helpers\n\ndef test_x():\n    project.helpers.check(1)\n"
        assert_that(findings(source, "sample.py", frozenset({"check"}))).is_empty()

    def test_the_marker_silences_a_configured_wrapper_too(self):
        source = f"{self.WRAPPED}\ndef test_x():\n    check(1)  # {ALLOW_MARKER}\n"
        assert_that(findings(source, "sample.py", frozenset({"check"}))).is_empty()

    def test_the_library_entry_points_still_work_alongside_one(self):
        source = f"{PREAMBLE}{self.WRAPPED}\ndef test_x():\n    assert_that(1)\n    check(2)\n"
        assert_that(findings(source, "sample.py", frozenset({"check"}))).is_length(2)


class TestThePluginWiring:
    """The check itself is pure, so these cover the part around it: reading each file once, and
    attaching a finding to the test that contains it.

    Driven by calling the hooks rather than through a nested pytest run, which is how the plugin's
    other hooks are tested here: the suite runs with `-p no:assertpy2`, so nothing else reaches them.
    """

    @staticmethod
    def _config(enabled: bool, entries=frozenset()):
        return SimpleNamespace(_assertpy2_dangling_enabled=enabled, _assertpy2_dangling_entries=entries)

    @staticmethod
    def _item(config, path, function_name=None, nodeid="t.py::test_x"):
        function = SimpleNamespace(__name__=function_name) if function_name else None
        return SimpleNamespace(config=config, path=path, function=function, nodeid=nodeid)

    def test_the_flag_off_records_nothing(self, tmp_path):
        source = tmp_path / "t.py"
        source.write_text(PREAMBLE + "def test_x():\n    assert_that(1)\n", encoding="utf-8")
        config = self._config(enabled=False)
        pytest_collection_modifyitems(None, config, [self._item(config, source)])
        assert_that(config._assertpy2_dangling).is_empty()

    def test_a_file_is_read_once_however_many_tests_it_contributed(self, tmp_path):
        source = tmp_path / "t.py"
        source.write_text(PREAMBLE + "def test_x():\n    assert_that(1)\n", encoding="utf-8")
        config = self._config(enabled=True)
        items = [self._item(config, source, "test_x"), self._item(config, source, "test_y")]
        pytest_collection_modifyitems(None, config, items)
        assert_that(config._assertpy2_dangling).is_length(1)
        assert_that(config._assertpy2_dangling[source]).is_length(1)

    def test_the_finding_lands_on_the_test_that_contains_it(self, tmp_path):
        source = tmp_path / "t.py"
        source.write_text(
            PREAMBLE
            + textwrap.dedent("""
                def test_clean():
                    assert_that(1).is_equal_to(1)


                def test_bare():
                    assert_that(1)
                """),
            encoding="utf-8",
        )
        config = self._config(enabled=True)
        clean = self._item(config, source, "test_clean")
        bare = self._item(config, source, "test_bare")
        pytest_collection_modifyitems(None, config, [clean, bare])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _report_dangling(clean)
            assert_that(caught).described_as("the clean test must not carry the other one's finding").is_empty()
            _report_dangling(bare)
        assert_that(caught).is_length(1)
        assert_that(caught[0].category).is_equal_to(DanglingAssertionWarning)
        # warn_explicit puts the reader in their own file, not in the plugin
        assert_that(str(caught[0].filename)).is_equal_to(str(source))

    def test_a_finding_outside_any_def_goes_to_the_first_test_to_run(self, tmp_path):
        source = tmp_path / "t.py"
        source.write_text(PREAMBLE + "assert_that(1)\n\n\ndef test_x():\n    pass\n", encoding="utf-8")
        config = self._config(enabled=True)
        item = self._item(config, source, "test_x")
        pytest_collection_modifyitems(None, config, [item])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _report_dangling(item)
        assert_that(caught).is_length(1)
        # and it is consumed, so a second test from the same file does not repeat it
        with warnings.catch_warnings(record=True) as again:
            warnings.simplefilter("always")
            _report_dangling(item)
        assert_that(again).is_empty()

    def test_the_configured_entries_reach_the_scan(self, tmp_path):
        source = tmp_path / "t.py"
        source.write_text("from project.helpers import check\n\ndef test_x():\n    check(1)\n", encoding="utf-8")
        config = self._config(enabled=True, entries=frozenset({"check"}))
        pytest_collection_modifyitems(None, config, [self._item(config, source, "test_x")])
        assert_that(config._assertpy2_dangling[source]).is_length(1)

    def test_a_config_from_before_the_setting_existed_is_tolerated(self):
        # the plugin's other tests build configs by hand, and a missing attribute must mean "none"
        config = SimpleNamespace(_assertpy2_dangling_enabled=False)
        pytest_collection_modifyitems(None, config, [])
        assert_that(config._assertpy2_dangling).is_empty()

    def test_an_item_without_a_config_is_left_alone(self):
        # the plugin's own tests drive hooks with a bare namespace, and this one must tolerate that
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _report_dangling(SimpleNamespace(nodeid="t.py::test_x"))
        assert_that(caught).is_empty()


class TestTurningItOn:
    """The flag is for trying it once; the ini setting is for a project that wants it every run.

    The flag wins, so somebody can switch it on for one command without editing a config the whole
    team shares.
    """

    @staticmethod
    def _config(*, flag=False, ini="off"):
        return SimpleNamespace(
            getoption=lambda name: flag if name == "assertpy2_dangling" else None,
            getini=lambda name: ini if name == "assertpy2_dangling" else None,
        )

    def test_the_ini_setting_alone_turns_it_on(self):
        assert_that(_dangling_enabled(self._config(ini="on"))).is_true()

    def test_off_by_default(self):
        assert_that(_dangling_enabled(self._config())).is_false()

    def test_the_flag_wins_over_a_config_that_says_off(self):
        assert_that(_dangling_enabled(self._config(flag=True, ini="off"))).is_true()

    def test_the_setting_is_read_case_and_space_insensitively(self):
        assert_that(_dangling_enabled(self._config(ini="  ON  "))).is_true()

    def test_an_unreadable_setting_warns_and_stays_off(self):
        # silence would be the wrong answer: a typo that quietly disables a check is how the check
        # stops running without anybody noticing
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            enabled = _dangling_enabled(self._config(ini="yes"))
        assert_that(enabled).is_false()
        assert_that(caught).is_length(1)
        assert_that(str(caught[0].message)).contains("assertpy2_dangling").contains("falling back to 'off'")

    def test_the_flag_still_wins_over_an_unreadable_setting(self):
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert_that(_dangling_enabled(self._config(flag=True, ini="yes"))).is_true()


class TestReadingTheEntriesSetting:
    """`assertpy2_dangling_entries` is a list of names, and a name that cannot bind is worth saying so.

    Silence on a bad value is the failure mode this check cannot afford: it would look configured and
    cover nothing.
    """

    @staticmethod
    def _config(*values):
        return SimpleNamespace(getini=lambda name: list(values) if name == "assertpy2_dangling_entries" else None)

    def test_nothing_configured_reads_as_nothing(self):
        assert_that(_dangling_entries(self._config())).is_empty()

    def test_names_are_read_and_trimmed(self):
        assert_that(_dangling_entries(self._config("check", "  verify  "))).is_equal_to({"check", "verify"})

    def test_a_dotted_path_is_dropped_with_a_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            entries = _dangling_entries(self._config("check", "helpers.verify"))
        assert_that(entries).is_equal_to({"check"})
        assert_that(caught).is_length(1)
        assert_that(str(caught[0].message)).contains("'helpers.verify'").contains("is not a plain name")

    def test_several_bad_names_are_reported_together_and_read_as_plural(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert_that(_dangling_entries(self._config("a.b", "c d"))).is_empty()
        assert_that(caught).is_length(1)
        assert_that(str(caught[0].message)).contains("'a.b', 'c d'").contains("are not plain names")


class TestANameThisModuleBindsItselfIsNotOurs:
    """Importing `assert_that` and then shadowing the name means the call in the body is somebody
    else's, and reporting it is a false alarm on their function.

    Raised by an external review. All three shapes reported before the fix.
    """

    @pytest.mark.parametrize(
        "body",
        [
            "def test_x(assert_that):\n    assert_that(1)\n",
            "def test_x():\n    assert_that = lambda value: value\n    assert_that(1)\n",
            "assert_that = print\n\n\ndef test_x():\n    assert_that(1)\n",
            "def test_x():\n    for assert_that in (print,):\n        assert_that(1)\n",
            "def test_x():\n    with open(__file__) as assert_that:\n        assert_that(1)\n",
        ],
        ids=["fixture parameter", "local lambda", "module rebinding", "loop target", "context manager"],
    )
    def test_a_shadowed_entry_point_is_left_alone(self, body):
        assert_that(scan(body)).is_empty()

    def test_shadowing_one_entry_point_does_not_silence_the_other(self):
        found = scan("def test_x(assert_warn):\n    assert_that(1)\n")
        assert_that(found).described_as("only the shadowed name is dropped").is_length(1)

    def test_an_exception_name_shadows_too(self):
        # `except ... as assert_that` binds the name for the block, and its own AST node holds a plain
        # string rather than a `Name`, so it needs its own branch
        body = """
            def test_x():
                try:
                    pass
                except ValueError as assert_that:
                    assert_that(1)
            """
        assert_that(scan(body)).is_empty()

    def test_a_bare_except_is_not_mistaken_for_a_binding(self):
        # `except ValueError:` carries `name=None`, which must not be read as a shadowed name
        found = scan("""
            def test_x():
                try:
                    assert_that(1)
                except ValueError:
                    pass
            """)
        assert_that(found).is_length(1)

    def test_a_module_alias_can_be_shadowed_too(self):
        assert_that(scan("def test_x(assertpy2):\n    assertpy2.assert_that(1)\n", "import assertpy2\n")).is_empty()


class TestTheMarkerIsAComment:
    """It is found by tokenising, not by searching the line for its own words.

    The first implementation searched the text, so a statement holding the marker inside a string was
    exempt without anybody writing a comment: an assertion *about* the marker's own wording silently
    stopped being checked.
    """

    def test_the_marker_inside_a_string_does_not_silence_anything(self):
        found = scan(f'def test_x():\n    assert_that("# {ALLOW_MARKER}")\n')
        assert_that(found).is_length(1)

    def test_nor_does_it_across_a_wrapped_call(self):
        found = scan(f'def test_x():\n    assert_that(\n        "{ALLOW_MARKER}"\n    )\n')
        assert_that(found).is_length(1)

    def test_a_real_comment_still_silences(self):
        assert_that(scan(f"def test_x():\n    assert_that(1)  # {ALLOW_MARKER}\n")).is_empty()

    def test_a_real_comment_on_the_closing_line_still_silences(self):
        assert_that(scan(f"def test_x():\n    assert_that(\n        1\n    )  # {ALLOW_MARKER}\n")).is_empty()

    def test_a_comment_on_a_neighbouring_statement_silences_only_that_one(self):
        found = scan(f"def test_x():\n    assert_that(1)  # {ALLOW_MARKER}\n    assert_that(2)\n")
        assert_that(found).is_length(1)
        assert_that(found[0].lineno).is_equal_to(4)
