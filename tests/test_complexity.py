"""A complexity ratchet, so the measure cannot grow where nobody looks.

Thirty functions in the package sit above mccabe's default of 10, the worst four being `extracting` at
32, `_build_equality_diff` at 30, `_sub_diff_entries` at 27 and `_dict_err` at 20.

Getting them under 10 is deliberately NOT the goal. It fixes no defect, and rewriting
`_build_equality_diff` for the sake of a number would risk code the suite and mutation testing hold.

Recorded per function rather than as a count or a ceiling, because neither of those sees the growth that
matters: a function going from 11 to 32 leaves both unchanged.  `[tool.ruff.lint.mccabe]` still carries
`max-complexity = 32`, which stops a new worst before this file is read at all.

Re-record when a number drops, which is the ratchet turning. A commit that raises one should say which
function grew and why that was the cheaper answer.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

from assertpy2 import assert_that

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_REPORTED = re.compile(r"`([^`]+)` is too complex \((\d+)")

RECORDED: dict[str, int] = {
    "assertpy2/extracting.py::extracting": 32,
    "assertpy2/_engine/_diff.py::_build_equality_diff": 30,
    "assertpy2/_engine/_diff.py::_sub_diff_entries": 27,
    "assertpy2/helpers.py::_dict_err": 20,
    "assertpy2/_snapshot_codec.py::_object_hook": 19,
    "assertpy2/_hints.py::diagnose": 17,
    "assertpy2/_engine/_compare.py::_find_ambiguous_operand": 15,
    "assertpy2/_engine/_diff.py::_walk_leaves": 15,
    "assertpy2/_engine/_equality.py::mapping_differs": 15,
    "assertpy2/collection.py::is_subset_of": 15,
    "assertpy2/_matcher_impls.py::_walk": 14,
    "assertpy2/_snapshot_codec.py::default": 14,
    "assertpy2/errors.py::_render_diff": 14,
    "assertpy2/snapshot.py::snapshot": 14,
    "assertpy2/errors.py::_json_safe": 13,
    "assertpy2/string.py::contains_ignoring_case": 13,
    "assertpy2/_engine/_compare.py::_build_compare_config": 12,
    "assertpy2/async_assertions.py::record": 12,
    "assertpy2/dynamic.py::__getattr__": 12,
    "assertpy2/_dangling.py::_survey": 11,
    "assertpy2/_dangling.py::findings": 11,
    "assertpy2/_engine/_contract.py::contract_drift": 11,
    "assertpy2/_satisfies.py::satisfies_exactly_in_any_order": 11,
    "assertpy2/assertpy.py::assert_conforms": 11,
    "assertpy2/async_assertions.py::__getattr__": 11,
    "assertpy2/contains.py::contains": 11,
    "assertpy2/helpers.py::_to_comparable_dict": 11,
    "assertpy2/json_mixin.py::_openapi_resolve": 11,
    "assertpy2/string.py::ends_with": 11,
    "assertpy2/string.py::starts_with": 11,
}
"""Every function over mccabe's default, keyed by file and name, measured 2026-08-29."""


def _measured() -> dict[str, int]:
    """What ruff reports at the default threshold, read from its own JSON."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "assertpy2/",
            "--select",
            "C901",
            "--config",
            "lint.mccabe.max-complexity = 10",
            "--output-format",
            "json",
            "--no-cache",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=_ROOT,
        check=False,
    )
    # refuse rather than read an empty list as zero: a ruff that failed to start would read as a clean sweep
    if result.returncode not in (0, 1) or not result.stdout.strip():
        raise RuntimeError(f"ruff did not report: exit {result.returncode} {result.stderr}")
    found = {}
    for row in json.loads(result.stdout):
        match = _REPORTED.search(row["message"])
        if match is None:
            raise RuntimeError(f"unreadable C901 message, so a real change could hide in it: {row['message']}")
        # relative to the repository, because both the checkout and the package are named `assertpy2`
        # and splitting on the name landed on the first of the two
        where = pathlib.Path(row["filename"]).resolve().relative_to(_ROOT).as_posix()
        key = f"{where}::{match.group(1)}"
        # ruff names the function and not the class, so two same-named methods in one file share a key.
        # Silently overwriting would let one of them grow behind the other
        if key in found:
            raise RuntimeError(f"two entries share {key}, so the record cannot tell them apart")
        found[key] = int(match.group(2))
    return found


def test_no_function_grew_more_complex() -> None:
    measured = _measured()
    grown = {
        name: f"{RECORDED.get(name, 0)} -> {score}" for name, score in measured.items() if score > RECORDED.get(name, 0)
    }
    assert_that(grown).described_as(
        "more complex than recorded. Say which function grew and why that was the cheaper answer"
    ).is_empty()


def test_the_record_is_not_stale() -> None:
    """A record nobody is near stops being a ratchet, so it has to be what ruff reports today."""
    assert_that(_measured()).described_as("recorded complexity, which has to be the measured one").is_equal_to(RECORDED)
