"""Hold the *rejections* to what `typing_negative_baseline.py` records.

`tests/test_typing.py` checks that correct usage type-checks and that a chain narrows the way it should.
Nothing checked the other direction: which incompatible operands a checker actually refuses.  Both
halves are needed before any signature is tightened, because the cost of tightening one is paid by the
usage that has to keep working.

**A rejection is recorded with its diagnostic code, not as a yes.** An earlier version asked only
whether a line was reported, and a counter-example whose fixture was missing a name reported an
undefined-reference instead of a type error: green, for the wrong reason, on a case that proved
nothing.  The codes also make the three checkers comparable, which is how a relation only one of them
refuses becomes visible rather than comfortable.

Skipped where the checkers are absent: they live in the `typecheck` group, so this runs in the
type-check job rather than in the main suite.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import pytest

pytest.importorskip("pyright")
pytest.importorskip("mypy")

from assertpy2 import assert_that
from tests.typing_negative_baseline import CAUGHT, VALID

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CASES = _ROOT / "tests" / "typing_cases.py"


def _tagged_lines() -> dict[int, str]:
    """Line number to case name, read from the tags in the source rather than kept in step by hand."""
    found = {}
    for number, line in enumerate(_CASES.read_text(encoding="utf-8").splitlines(), 1):
        tag = re.search(r"# case: ([\w-]+)", line)
        if tag:
            found[number] = tag.group(1)
    return found


def _run(*command: str) -> str:
    result = subprocess.run([sys.executable, "-m", *command], capture_output=True, text=True, cwd=_ROOT, check=False)
    # every one of them exits non-zero as soon as it reports anything, so the output is what to read
    return result.stdout + result.stderr


def _pyright() -> dict[int, set[str]]:
    report = json.loads(_run("pyright", "--outputjson", str(_CASES)))
    found: dict[int, set[str]] = {}
    for item in report["generalDiagnostics"]:
        found.setdefault(item["range"]["start"]["line"] + 1, set()).add(item.get("rule", item["severity"]))
    return found


def _mypy() -> dict[int, set[str]]:
    output = _run("mypy", "--strict", "--follow-imports=silent", str(_CASES))
    found: dict[int, set[str]] = {}
    for number, code in re.findall(r"typing_cases\.py:(\d+): error:.*\[([\w-]+)\]", output):
        found.setdefault(int(number), set()).add(code)
    return found


def _ty() -> dict[int, set[str]]:
    output = _run("ty", "check", "--output-format", "concise", str(_CASES))
    found: dict[int, set[str]] = {}
    for number, code in re.findall(r"typing_cases\.py:(\d+):\d+: error\[([\w-]+)\]", output):
        found.setdefault(int(number), set()).add(code)
    return found


@pytest.fixture(scope="module")
def reported() -> dict[str, dict[int, set[str]]]:
    """Line number to diagnostic codes, per checker, from one run of each."""
    return {"ty": _ty(), "mypy": _mypy(), "pyright": _pyright()}


@pytest.fixture(scope="module")
def by_case(reported) -> dict[str, dict[str, set[str]]]:
    """Case name to the codes each checker reported for it."""
    lines = _tagged_lines()
    return {
        name: {checker: found.get(number, set()) for checker, found in reported.items()}
        for number, name in lines.items()
    }


class TestTheMeasurementItselfRan:
    """A comparison against an empty run passes everything, so the run has to be shown to have happened."""

    def test_every_recorded_case_is_present_in_the_file(self, by_case):
        assert_that(set(by_case)).is_equal_to(set(CAUGHT) | VALID)

    def test_all_three_checkers_reported_something(self, reported):
        silent = [checker for checker, found in reported.items() if not found]
        assert_that(silent).described_as("a checker reported nothing at all: it did not run").is_empty()

    def test_no_diagnostic_lands_outside_a_tagged_line(self, reported):
        """The guard the `date` incident bought.

        A counter-example whose fixture was missing an import reported an undefined name, the test saw
        a diagnostic on the right line, and the case it was meant to prove was never checked. Anything
        reported away from a tagged line means the file itself is broken.
        """
        lines = _tagged_lines()
        stray = {
            checker: sorted(number for number in found if number not in lines)
            for checker, found in reported.items()
            if set(found) - set(lines)
        }
        assert_that(stray).described_as("diagnostics away from a tagged case: the file is broken").is_empty()


class TestWhatTheCheckersRefuse:
    def test_each_case_is_refused_with_exactly_the_recorded_codes(self, by_case):
        differing = {}
        for name, expected in CAUGHT.items():
            observed = {checker: sorted(codes) for checker, codes in by_case[name].items() if codes}
            recorded = {checker: sorted(codes) for checker, codes in expected.items()}
            if observed != recorded:
                differing[name] = {"recorded": recorded, "observed": observed}
        assert_that(differing).described_as(
            "a rejection changed. Tightened on purpose? Update typing_negative_baseline.py"
        ).is_empty()

    def test_a_refused_case_is_refused_by_all_three(self, by_case):
        # they have disagreed before, and a relation only one checker catches is a fact worth stating
        # rather than a comfort: a suite gated on one checker would let it through
        split = {
            name: sorted(checker for checker, codes in by_case[name].items() if codes)
            for name, expected in CAUGHT.items()
            if expected and len(expected) != 3
        }
        assert_that(split).described_as("checkers disagree; record the split in the baseline").is_empty()

    def test_the_codes_say_the_same_thing_in_three_dialects(self, by_case):
        """A relation refused for one reason by one checker and another by the next is not one relation.

        Each row of the baseline names a family, and the three spellings inside it have to belong to
        that family: an argument that does not fit, or a method that is not there.
        """
        families = [
            {"invalid-argument-type", "arg-type", "reportArgumentType", "no-matching-overload", "reportCallIssue"},
            {"unresolved-attribute", "attr-defined", "reportAttributeAccessIssue"},
        ]
        mixed = {}
        for name, expected in CAUGHT.items():
            codes = {code for spelling in expected.values() for code in spelling}
            if codes and not any(codes <= family for family in families):
                mixed[name] = sorted(codes)
        assert_that(mixed).described_as("one relation, refused for unrelated reasons").is_empty()


class TestOrdinaryUsageStaysAccepted:
    """The half that decides whether a tightened signature can ship at all."""

    def test_no_valid_relation_is_rejected(self, by_case):
        refused = {
            name: {checker: sorted(codes) for checker, codes in by_case[name].items() if codes}
            for name in VALID
            if any(by_case[name].values())
        }
        assert_that(refused).described_as("valid usage stopped type-checking").is_empty()
