"""Every assertion either names what it measured against, or is written down as one that cannot.

`AssertionOutcome.expected` is what a report consumer reads: an Allure attachment, a dashboard, a
clustering key.  For most of the library that is the operand the assertion was handed, and for a while
only 22 of the 163 failure sites passed it, so the same question got a different answer depending on
which assertion had failed.

What cannot name one is a real category rather than an oversight, and this file is the boundary between
the two.  A negation was handed a value the subject must *not* be, and putting that under `expected`
would tell a reader the opposite of the truth.  A predicate with no operand was handed nothing at all.
Both are listed below with which of the two they are, so a new assertion has to be decided about.
"""

from __future__ import annotations

import ast
import collections
import datetime
import pathlib

import pytest

from assertpy2 import assert_that
from assertpy2.errors import AssertionFailure

_STAMP = datetime.datetime(2026, 2, 1)
_EARLIER = datetime.datetime(2026, 1, 1)

_PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "assertpy2"

# What the value must not be, which is not what it was expected to be
_NEGATIONS = {
    "contains_none_of",
    "does_not_contain",
    "does_not_contain_duplicates",
    "does_not_contain_entry",
    "does_not_contain_error",
    "does_not_contain_value",
    "does_not_exist",
    "does_not_have_json_path",
    "does_not_match",
    "is_not_between",
    "is_not_callable",
    "is_not_empty",
    "is_not_equal_to",
    "is_not_in",
    "is_not_inf",
    "is_not_close_to",
    "is_not_iterable",
    "is_not_nan",
    "is_not_none",
    "is_not_same_as",
    "none_satisfy",
    "_when_called_with_not_expected",
    "_when_called_with_not_warning",
}

# Nothing was handed in: the assertion asks about the value alone
_ASKS_ABOUT_THE_VALUE_ALONE = {
    "contains_duplicates",
    "exists",
    "is_callable",
    "is_directory",
    "is_empty",
    "is_even",
    "is_executable",
    "is_file",
    "is_inf",
    "is_iterable",
    "is_nan",
    "is_odd",
    "is_readable",
    "is_sorted",
    "is_unicode",
    "is_valid_utf8",
    "is_writable",
}

# Not assertions: a refused subject, an exhausted poll, a walk reporting its own find, the dynamic hook
_NOT_AN_ASSERTION = {
    "_check_placeholders",
    "_dict_not_equal",
    "_out_of_time",
    "_require_group",
    "_wrapper",
    "conforms_to_openapi",
    "matches_contract_snapshot",
}

_EXCUSED = _NEGATIONS | _ASKS_ABOUT_THE_VALUE_ALONE | _NOT_AN_ASSERTION


def _by_owner() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """``(what names an expected, what does not)``, each as ``{function: [file:line]}``."""
    named: dict[str, list[str]] = collections.defaultdict(list)
    silent: dict[str, list[str]] = collections.defaultdict(list)
    for path in sorted(_PACKAGE.glob("**/*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        owner = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for child in ast.walk(node):
                    owner[id(child)] = node.name
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "error"):
                continue
            where = f"{path.name}:{node.lineno}"
            side = named if any(keyword.arg == "expected" for keyword in node.keywords) else silent
            side[owner.get(id(node), "?")].append(where)
    return dict(named), dict(silent)


def test_the_walk_found_the_failure_sites() -> None:
    # a walk that found nothing would agree with any register below it
    named, silent = _by_owner()
    sites = sum(len(where) for where in named.values())
    assert_that(sites).described_as("failure sites naming an expected").is_greater_than(100)
    assert_that(set(named) & set(silent)).described_as(
        "an assertion that names one in some places and not in others, which is the drift this catches"
    ).is_empty()


def test_every_assertion_that_names_no_expected_is_written_down() -> None:
    """The one direction that matters: a new assertion cannot quietly skip the field."""
    _named, silent = _by_owner()
    assert_that(sorted(set(silent) - _EXCUSED)).described_as(
        "failure sites that name no expected value and no reason for it"
    ).is_empty()


def test_no_excused_name_stands_for_two_different_assertions() -> None:
    """The register is keyed by name, so a name that two modules define would be excused twice over."""
    owners = collections.defaultdict(set)
    for path in sorted(_PACKAGE.glob("**/*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.FunctionDef) and node.name in _EXCUSED):
                continue
            # only where a failure is raised: a protocol declares the names and raises nothing
            if any(isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "error" for call in ast.walk(node)):
                owners[node.name].add(path.name)
    shared = {name: sorted(where) for name, where in owners.items() if len(where) > 1}
    assert_that(shared).described_as("one entry excusing more than one assertion").is_equal_to({})


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (lambda: assert_that(0).is_true(), True),
        (lambda: assert_that(1).is_false(), False),
        (lambda: assert_that(1).is_none(), None),
        (lambda: assert_that("ab").is_length(3), 3),
        (lambda: assert_that(1).is_same_as(2), 2),
        (lambda: assert_that(1).is_instance_of(str), str),
        (lambda: assert_that([1]).contains(9), (9,)),
        (lambda: assert_that(5).is_between(1, 2), (1, 2)),
        (lambda: assert_that(5).is_close_to(1, 0.5), (1, 0.5)),
        (lambda: assert_that("abc").matches("z"), "z"),
        (lambda: assert_that(_STAMP).is_before(_EARLIER), _EARLIER),
        # a payload the assertion normalised before measuring against it, and a value it derived
        (lambda: assert_that({"a": 1}).contains_entry(a=2), [{"a": 2}]),
        (lambda: assert_that([1, 2]).has_same_size_as([1]), 1),
    ],
    ids=lambda value: getattr(value, "__name__", str(value)),
)
def test_the_value_it_names_is_the_one_it_was_measured_against(call, expected) -> None:
    """The keyword being there is not the claim: what it carries is.

    A walk over the source can see `expected=` and nothing about what was put in it, so these pin the
    value for one assertion of each shape: a demanded constant, an operand, a variadic, a pair.
    """
    with pytest.raises(AssertionFailure) as failure:
        call()
    assert_that(failure.value.expected).is_equal_to(expected)


def test_no_entry_is_excusing_something_that_no_longer_happens() -> None:
    """The other direction, and the one that rots: an entry with nothing to excuse says so to nobody."""
    _named, silent = _by_owner()
    assert_that(sorted(_EXCUSED - set(silent))).described_as(
        "excused here and naming an expected anyway, so the entry is stale"
    ).is_empty()
