"""Hold the package-wide pyright surface to what `pyright_baseline.py` records.

CI gates pyright on `tests/test_typing.py`. The package itself was ungated, so a diagnostic introduced
anywhere in it went unreported.

Skipped where pyright is absent: it lives in the `typecheck` group, so this runs in the type-check job
rather than in the main suite.
"""

from __future__ import annotations

import collections
import functools
import json
import pathlib
import re
import subprocess
import sys

import pytest

pytest.importorskip("pyright")

from typing import Final

from assertpy2 import assert_that
from tests.pyright_baseline import BASELINE

_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Named rather than counted: a count of two stays green when one is replaced by an unrelated
# diagnostic of the same rule, and each refusal is about its TypeVar rather than about a number.
_REFUSED_VARIANCE: tuple[tuple[str, str, str, str], ...] = (
    ("assertpy2/_engine/_typing.py", "_RepeatableAssertion", "_E", "contravariant"),
    # `_NumericAssertion` is no longer among them: `check()` reads `_N` back in a return position, so
    # the covariance suggestion pyright used to make there answers itself
    # the twins inherit the refusals along with the signatures.  `_CheckDictAssertion` gains one the
    # original does not have, because dropping the chaining return leaves `_V` read-only there and
    # pyright then suggests contravariance; the value type is still read back through the assertions
    # that take it, so the answer is the same
    ("assertpy2/_engine/_check_typing.py", "_CheckRepeatableAssertion", "_E", "contravariant"),
    ("assertpy2/_engine/_check_typing.py", "_CheckNumericAssertion", "_N", "covariant"),
    ("assertpy2/_engine/_check_typing.py", "_CheckDictAssertion", "_V", "contravariant"),
)


# The target this baseline was recorded against, passed explicitly rather than taken from whichever
# interpreter happens to be running.  It is not cosmetic: pyright reports 108 diagnostics against 3.10
# and 102 against 3.14, so a contributor on the supported floor met a red gate that said nothing about
# their change.  3.14 because that is what the type-check job runs; 3.15 gives the same answer.
_TARGET: Final = "3.14"


@functools.cache
def _diagnostics() -> tuple[dict[str, str], ...]:
    """Every pyright diagnostic over the package, as ``{file, rule, message}``, run once for the module."""
    result = subprocess.run(
        [sys.executable, "-m", "pyright", "--outputjson", "--pythonversion", _TARGET, "assertpy2/"],
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )
    # pyright exits non-zero whenever it reports anything, so the payload is what to read, not the code
    report = json.loads(result.stdout)
    return tuple(
        {
            "file": pathlib.Path(item["file"]).resolve().relative_to(_ROOT).as_posix(),
            "rule": item.get("rule", item["severity"]),
            "message": item["message"],
        }
        for item in report["generalDiagnostics"]
    )


def _observed() -> dict[tuple[str, str], int]:
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for item in _diagnostics():
        counts[(item["file"], item["rule"])] += 1
    return dict(counts)


def test_no_unrecorded_pyright_diagnostics() -> None:
    observed = _observed()
    # the run itself has to have happened: an empty report would pass every comparison below
    assert_that(observed).is_not_empty()

    appeared = {key: count for key, count in observed.items() if count > BASELINE.get(key, 0)}
    assert_that(appeared).described_as("pyright diagnostics not recorded in pyright_baseline.py").is_empty()

    resolved = {key: count for key, count in BASELINE.items() if count > observed.get(key, 0)}
    assert_that(resolved).described_as("recorded in pyright_baseline.py but no longer reported").is_empty()


def test_the_recorded_variance_refusals_are_the_ones_still_reported() -> None:
    """Name the two variance suggestions the package refuses, rather than counting them.

    The counting gate above cannot tell one diagnostic of a rule from another in the same file, so a new
    `reportInvalidTypeVarUse` could take the place of a resolved one and nothing would move.  These two
    are refused for reasons written down beside them, and each reason is about a specific TypeVar: `_N`
    would break its inputs if made covariant, and `_E` is used covariantly through `Matcher[_E]` despite
    appearing only in parameters, which `typing_cases.py` demonstrates on all three checkers.
    """
    read = [
        (item, re.search(r'variable "(\w+)".*Protocol "(\w+)".*should be (\w+)', item["message"], re.DOTALL))
        for item in _diagnostics()
        if item["rule"] == "reportInvalidTypeVarUse"
    ]
    # every one has to be classified: a message this pattern cannot read would otherwise drop out of the
    # comparison silently, and take a real change with it
    unreadable = [item["message"] for item, found in read if found is None]
    assert_that(unreadable).described_as("variance suggestions this test could not parse").is_empty()

    # the file and the suggested variance are part of the record: the same protocol and TypeVar asked to
    # become something else is a different diagnostic, and a count would not know
    reported = [(item["file"], found.group(2), found.group(1), found.group(3)) for item, found in read if found]
    assert_that(sorted(reported)).described_as("the variance suggestions pyright still reports").is_equal_to(
        sorted(_REFUSED_VARIANCE)
    )
