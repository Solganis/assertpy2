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

# The hybrids: they hand back a different value *and* test an expectation on the way, so both proxies
# apply to them.  `error_of(KeyError)` says the group contains one and then pivots to it, and negating
# that is a question with an answer.
#
# Named rather than derived, and this is the register that matters most.  "Reaches `self.error()`" does
# not separate a verdict from a precondition: `errors()` reaches it only through the gate that refuses
# a subject which is not a group, and so read as asserting for as long as nobody asked what it could be
# wrong about.  Deriving the pivots is reliable; deciding which of them also assert is not, so a new
# pivot fails the gate until someone says which side it is on.
ALSO_ASSERTS: Final = frozenset(
    {
        "caused_by",
        "error_of",
        "extracting_group",
        "has_root_cause",
        "matches_with_groups",
        "when_called_with",
    }
)

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
    # `errors()` takes no expectation, so once a group has been caught there is nothing it can be
    # wrong about: it hands the leaves over as a list and the assertion on them is the next step.  It
    # reaches `self.error()` all the same, through the gate that refuses a subject which is not a
    # group, and that is what made the first classification count it as asserting
    "errors": TRANSFORMS,
    "single": TRANSFORMS,
    "described_as": DESCRIBES,
    "eventually": POLLS,
    "eventually_sync": POLLS,
}
