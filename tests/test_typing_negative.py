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

import pytest

pytest.importorskip("pyright")
pytest.importorskip("mypy")

from assertpy2 import assert_that
from tests import typing_harness
from tests.typing_negative_baseline import CAUGHT, VALID

_CASES = typing_harness.ROOT / "tests" / "typing_cases.py"


@pytest.fixture(scope="module")
def reported() -> dict[str, dict[int, set[str]]]:
    """Line number to diagnostic codes, per checker, from one run of each."""
    return {
        "ty": typing_harness.ty(_CASES),
        "mypy": typing_harness.mypy(_CASES),
        "pyright": typing_harness.pyright(_CASES),
    }


@pytest.fixture(scope="module")
def by_case(reported) -> dict[str, dict[str, set[str]]]:
    return typing_harness.by_case(reported, _CASES)


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
        lines = typing_harness.tagged_lines(_CASES)
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

        Families are read per checker rather than as one pool of codes, and the reason is a code that
        belongs to two of them: pyright says `reportCallIssue` both for an argument that does not fit an
        overload and for a keyword that does not exist.  Pooled together, those two families overlapped
        through that one code, and an overlap makes the check unable to tell them apart.
        """
        families = [
            # an argument that does not fit.  `misc` rides along with mypy's `arg-type` when the
            # argument is a callable: the same refusal said twice, not a second reason
            {
                "ty": {"invalid-argument-type", "no-matching-overload"},
                "mypy": {"arg-type", "misc"},
                "pyright": {"reportArgumentType", "reportCallIssue"},
            },
            # a method the value's protocol does not have
            {
                "ty": {"unresolved-attribute"},
                "mypy": {"attr-defined"},
                "pyright": {"reportAttributeAccessIssue"},
            },
            # a keyword the signature does not have, where the call does not even bind
            {
                "ty": {"unknown-argument"},
                "mypy": {"call-arg"},
                "pyright": {"reportCallIssue"},
            },
            # a required argument that is not there.  Kept apart from the keyword family above, because
            # `call-arg` and `reportCallIssue` cover both and only ty tells them apart by name
            {
                "ty": {"missing-argument"},
                "mypy": {"call-arg"},
                "pyright": {"reportCallIssue"},
            },
        ]
        mixed = {}
        for name, expected in CAUGHT.items():
            # every checker has to speak, with codes of its own: `set()` is a subset of any family, so a
            # row missing one would otherwise read as three dialects agreeing
            speaks_for_all = set(expected) == {"ty", "mypy", "pyright"} and all(expected.values())
            fits_one = any(
                all(set(expected.get(checker, ())) <= codes for checker, codes in family.items()) for family in families
            )
            # `misc` is mypy's second word for an argument that does not fit, never a reason on its own:
            # alone it would let an unrelated error read as one of these families
            spoken = set(expected.get("mypy", ()))
            rides_along = "misc" not in spoken or "arg-type" in spoken
            if expected and not (speaks_for_all and fits_one and rides_along):
                mixed[name] = {checker: sorted(codes) for checker, codes in expected.items()}
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
