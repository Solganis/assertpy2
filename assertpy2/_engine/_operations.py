"""Which public operations reach a verdict, and what the ones that do not do instead.

Both proxies need the same answer.  ``not_`` inverts a verdict and ``check()`` reports one, so an
operation that reaches no verdict means nothing through either, and both used to accept them:
``assert_that(1).not_.check()`` failed with "Expected <1> to NOT satisfy: check()", and
``assert_that([1]).check().first()`` answered that an assertion passed when none had run.

A verdict is ``self.error(...)``, the one failure entry point every assertion goes through.  What is
registered here is the complement: the operations that reach it through nothing, listed by what they
do instead.  Written as the exceptions rather than as the whole surface, because 134 of the 152 public
names assert and a register of those would be a second copy of the API, kept in step by hand.

`tests/test_operation_contract.py` re-derives this set from the source and fails on any difference, so
a new operation that asserts nothing cannot quietly become negatable or checkable.
"""

from __future__ import annotations

from typing import Final

CONFIGURES: Final = "configures"
TRANSFORMS: Final = "transforms"
DESCRIBES: Final = "describes"
POLLS: Final = "polls"

# What each one does instead of asserting.  The proxies compose their own sentence around this, since
# the same operation is refused for one reason by `not_` and another by `check()`
WHAT_IT_DOES: Final = {
    CONFIGURES: "only sets an expectation and asserts nothing on its own",
    TRANSFORMS: "hands back a different value instead of asserting",
    DESCRIBES: "only sets the failure description",
    POLLS: "runs a whole chain until it holds",
}

# The builder's own machinery, which is not an assertion under any reading: `error` is the failure
# entry point the classification is defined by, `builder` constructs the next step, `value` hands the
# subject back, and the two proxies are entrances rather than operations.  Named rather than filtered
# out silently, so a new one has to be declared here before the gate will accept it
NOT_AN_OPERATION: Final = frozenset({"builder", "check", "error", "not_", "value"})

WITHOUT_A_VERDICT: Final[dict[str, str]] = {
    # an expectation is set and the call that tests it comes next
    "raises": CONFIGURES,
    "does_not_raise": CONFIGURES,
    "warns": CONFIGURES,
    "does_not_warn": CONFIGURES,
    # a pivot: what comes back is a different value, and the assertion on it is the next step
    "at_json_path": TRANSFORMS,
    "decoded_as": TRANSFORMS,
    "decoded_as_json": TRANSFORMS,
    "element": TRANSFORMS,
    "extracting": TRANSFORMS,
    "filtered_on": TRANSFORMS,
    "first": TRANSFORMS,
    "flat_mapped": TRANSFORMS,
    "last": TRANSFORMS,
    "mapped": TRANSFORMS,
    "raised": TRANSFORMS,
    "returned": TRANSFORMS,
    "single": TRANSFORMS,
    "described_as": DESCRIBES,
    "eventually": POLLS,
    "eventually_sync": POLLS,
}
