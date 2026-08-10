"""Pin what `import assertpy2` gives a caller.

The golden failure harness proves the text of a failure has not moved. It says nothing about the Python
contract, and nothing else did either: before this file, removing a name from `__all__` or a field from
a published record passed every gate in the repository.

The neighbours answer different questions. `test_protocol_parity` proves each declared protocol method
exists at runtime, `test_api_vocabulary` holds the naming rules, `test_typing` pins overload resolution.
None of them notices an export that disappeared.

Both lists below are written by hand. Deriving them from the package would agree with whatever the
package happens to say, which gates nothing: the point is that a human edits them on purpose.
"""

from __future__ import annotations

import dataclasses

import assertpy2
from assertpy2 import assert_that

EXPECTED_EXPORTS = [
    "AssertionFailure",
    "AssertionOutcome",
    "AsyncAssertionBuilder",
    "BaseMatcher",
    "CheckBuilder",
    "DiffEntry",
    "DiffResult",
    "MatchResult",
    "Matcher",
    "NegatedBuilder",
    "PollSample",
    "PollTrace",
    "SnapshotCreatedWarning",
    "SnapshotKeyReusedWarning",
    "SnapshotUpdatedWarning",
    "SoftAssertionCollector",
    "Step",
    "SyncAssertionBuilder",
    "VacuousAssertionWarning",
    "WarningLoggingAdapter",
    "__version__",
    "add_extension",
    "assert_all",
    "assert_conforms",
    "assert_that",
    "assert_warn",
    "clear_custom_matchers",
    "contents_of",
    "fail",
    "match",
    "register_matcher",
    "register_snapshot_serializer",
    "remove_extension",
    "soft_assertions",
    "soft_fail",
    "unregister_matcher",
]

# The records a consumer reads off a failure. `__all__` covers the names a module exports and stops
# there, so a field dropped from one of these would go out in a release unremarked.
EXPECTED_FIELDS = {
    "AssertionOutcome": [
        "passed",
        "message",
        "actual",
        "actual_provided",
        "expected",
        "diff",
        "trace",
        "group",
        "location",
        "hint",
    ],
    "MatchResult": ["matched", "description", "mismatch", "diff"],
    "DiffEntry": ["path", "actual", "expected", "absent", "steps"],
    "DiffResult": ["kind", "entries"],
    "Step": ["kind", "value", "side"],
    "PollSample": ["elapsed", "outcome", "value", "detail", "repeats"],
    "PollTrace": ["samples", "total_polls", "dropped", "elapsed", "summary"],
}


def _fields(record: type) -> list[str]:
    """Field names in declaration order, for a dataclass or a NamedTuple alike."""
    if dataclasses.is_dataclass(record):
        return [field.name for field in dataclasses.fields(record)]
    return list(record._fields)  # NamedTuple's own documented accessor


class TestExports:
    def test_the_exported_names_are_the_recorded_ones(self):
        assert_that(sorted(assertpy2.__all__)).is_equal_to(sorted(EXPECTED_EXPORTS))

    def test_every_exported_name_resolves(self):
        # `__all__` is a list of strings, and a name left in it after its import was dropped fails
        # only at `from assertpy2 import *`, which nothing in the suite does
        missing = [name for name in assertpy2.__all__ if not hasattr(assertpy2, name)]
        assert_that(missing).described_as("names in __all__ with nothing behind them").is_empty()


class TestRecordFields:
    def test_each_published_record_keeps_its_fields(self):
        observed = {name: _fields(getattr(assertpy2, name)) for name in EXPECTED_FIELDS}
        assert_that(observed).is_equal_to(EXPECTED_FIELDS)

    def test_every_pinned_record_is_exported(self):
        # a record pinned here but dropped from `__all__` would keep passing the check above through
        # whatever import path this module happens to use
        assert_that(sorted(EXPECTED_FIELDS)).is_subset_of(set(assertpy2.__all__))


class TestTheCountsTheDocsQuote:
    """`docs/getting-started/comparison.md` states these as figures, and a figure in prose rots
    silently: it was written at 39 matchers and was still saying so at 41."""

    def test_the_matcher_count(self):
        matchers = [name for name in dir(assertpy2.match) if not name.startswith("_")]
        assert_that(matchers).described_as("matchers, quoted in comparison.md").is_length(41)

    def test_the_assertion_count_clears_the_floor_the_docs_claim(self):
        # a floor, not an exact number: `add_extension` writes onto the builder, so a suite that
        # registers one and leaves it makes the exact count depend on test order. The page says
        # "over 100" and that is the claim worth holding
        builder = assertpy2.assert_that(1)
        assertions = [
            name for name in dir(builder) if not name.startswith("_") and callable(getattr(builder, name, None))
        ]
        assert_that(len(assertions)).described_as("assertions, quoted in comparison.md as over 100").is_greater_than(
            100
        )
