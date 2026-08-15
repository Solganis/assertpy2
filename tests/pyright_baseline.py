"""Pyright diagnostics the package is known to carry, and why each group is there.

The package walks values whose static type really is `object`, guards optional imports, and composes
mixins, so pyright reports things that are not defects. Recording them per (file, rule) with a reason
lets the guard fail on a new one instead of on a total nobody can read.

A rule appearing where it was not recorded fails. So does one appearing more often, or fewer times
than recorded, which points here rather than at the code.

Line numbers are not part of the key: they move on every unrelated edit above them.
"""

from __future__ import annotations

BASELINE: dict[tuple[str, str], int] = {
    # --- values typed `object`, asked things only their runtime type can answer -------------------
    # The recursive walk decides what a value is at runtime, then reads it. Pyright judges each read
    # against the declared `object`, where ty accepts it after the narrowing predicate. Closing them
    # would mean a cast at every hop.
    ("assertpy2/_engine/_diff.py", "reportAttributeAccessIssue"): 14,
    ("assertpy2/_satisfies.py", "reportArgumentType"): 1,
    ("assertpy2/base.py", "reportArgumentType"): 2,
    ("assertpy2/extracting.py", "reportArgumentType"): 1,
    ("assertpy2/extracting.py", "reportCallIssue"): 1,
    ("assertpy2/extracting.py", "reportIndexIssue"): 1,
    ("assertpy2/helpers.py", "reportArgumentType"): 3,
    ("assertpy2/helpers.py", "reportGeneralTypeIssues"): 1,
    ("assertpy2/helpers.py", "reportIndexIssue"): 2,
    ("assertpy2/pytest_plugin.py", "reportArgumentType"): 3,
    # --- `numbers.Number` declares no arithmetic --------------------------------------------------
    # The ABC names the tower without promising operators, so comparing one or passing it to
    # `math.isnan` is flagged even though every concrete member supports both.
    ("assertpy2/_engine/_compare.py", "reportArgumentType"): 2,
    ("assertpy2/_engine/_compare.py", "reportOperatorIssue"): 1,
    ("assertpy2/helpers.py", "reportOperatorIssue"): 2,
    # --- optional dependencies, imported under try/except ------------------------------------------
    # Every use sits behind the flag the guarded import sets, which pyright does not correlate with
    # the binding, so it reports the import and each use.
    ("assertpy2/behave_matchers.py", "reportAttributeAccessIssue"): 1,
    ("assertpy2/behave_matchers.py", "reportMissingModuleSource"): 1,
    ("assertpy2/pytest_plugin.py", "reportMissingImports"): 1,
    ("assertpy2/pytest_plugin.py", "reportPossiblyUnboundVariable"): 6,
    # `executing` ships no annotations for the AST wrapper the inline-snapshot locator reads
    ("assertpy2/_inline.py", "reportAttributeAccessIssue"): 2,
    # --- the overload sets, all deliberate ---------------------------------------------------------
    # `assert_that` dispatches on value type, so per-type overloads overlap the generic fallback and
    # the implementation is typed to the core protocol. The `satisfies` narrowing pair is the same
    # trade taken once more, now in three places: the core protocol, and the string and numeric ones
    # that narrow it to `Matcher[str]` / `Matcher[_N]` so a matcher built for another type is caught.
    ("assertpy2/_engine/_typing.py", "reportOverlappingOverload"): 3,
    ("assertpy2/assertpy.py", "reportInconsistentOverload"): 1,
    ("assertpy2/assertpy.py", "reportOverlappingOverload"): 4,
    # Two variance suggestions, both refused on purpose. `_N` is read back through `value`, so
    # covariance would break its inputs. `_E` appears only in parameters, but one of them is
    # `Matcher[_E]`, and `Matcher` is contravariant: the flips cancel, and declaring it would let a
    # `Matcher[Dog]` reach an assertion over animals. Measured: pyright and mypy both accept that
    # substitution silently. `typing_cases.py` holds the case.
    ("assertpy2/_engine/_typing.py", "reportInvalidTypeVarUse"): 2,
    # --- mixin composition -------------------------------------------------------------------------
    # The mixins each declare the shared helpers over their own value type, and `AssertionBuilder` is
    # where all of them meet.
    ("assertpy2/assertpy.py", "reportIncompatibleMethodOverride"): 3,
    ("assertpy2/helpers.py", "reportIncompatibleMethodOverride"): 2,
    # --- dynamic attribute resolution ---------------------------------------------------------------
    # `__getattr__` builds the check/negation proxies, so what it returns cannot match a declared
    # return type. Each site carries its own ty suppression.  There used to be a fourth here, from
    # writing `__tracebackhide__` onto the contextlib module; that patch is gone and so is the report.
    ("assertpy2/assertpy.py", "reportAttributeAccessIssue"): 3,
    ("assertpy2/assertpy.py", "reportReturnType"): 4,
    # the failure record is `| None` in general and never None at this call, as the comment there says
    ("assertpy2/snapshot.py", "reportArgumentType"): 1,
    # both branches that reach the read assign it first, through a `try` pyright does not follow
    ("assertpy2/snapshot.py", "reportPossiblyUnboundVariable"): 2,
}
