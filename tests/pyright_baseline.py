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
    ("assertpy2/_engine/_diff.py", "reportAttributeAccessIssue"): 14,
    ("assertpy2/_satisfies.py", "reportArgumentType"): 1,
    ("assertpy2/base.py", "reportArgumentType"): 2,
    ("assertpy2/extracting.py", "reportArgumentType"): 1,
    ("assertpy2/extracting.py", "reportCallIssue"): 1,
    ("assertpy2/extracting.py", "reportIndexIssue"): 1,
    ("assertpy2/helpers.py", "reportArgumentType"): 3,
    ("assertpy2/helpers.py", "reportGeneralTypeIssues"): 1,
    ("assertpy2/helpers.py", "reportIndexIssue"): 2,
    # three of these are values walked as `object`; the fourth is the failure-cluster share, parsed
    # the same guarded way the poll-report fraction is
    ("assertpy2/pytest_plugin.py", "reportArgumentType"): 4,
    ("assertpy2/_engine/_compare.py", "reportArgumentType"): 2,
    ("assertpy2/_engine/_compare.py", "reportOperatorIssue"): 1,
    ("assertpy2/helpers.py", "reportOperatorIssue"): 2,
    ("assertpy2/behave_matchers.py", "reportAttributeAccessIssue"): 1,
    ("assertpy2/behave_matchers.py", "reportMissingModuleSource"): 1,
    ("assertpy2/pytest_plugin.py", "reportMissingImports"): 1,
    ("assertpy2/pytest_plugin.py", "reportPossiblyUnboundVariable"): 6,
    # `executing` ships no annotations for the AST wrapper the inline-snapshot locator reads
    ("assertpy2/_inline.py", "reportAttributeAccessIssue"): 2,
    ("assertpy2/_engine/_typing.py", "reportOverlappingOverload"): 28,
    # the verdict twins mirror the protocols, and they mirror their reports with them: the same
    # overload ladder, the same two variance suggestions plus the one `_DictAssertion` carries, and
    # one override report for the same reason the original has it
    ("assertpy2/_engine/_check_typing.py", "reportOverlappingOverload"): 1,
    ("assertpy2/_engine/_check_typing.py", "reportInvalidTypeVarUse"): 3,
    ("assertpy2/_engine/_check_typing.py", "reportIncompatibleMethodOverride"): 2,
    ("assertpy2/assertpy.py", "reportInconsistentOverload"): 1,
    ("assertpy2/assertpy.py", "reportOverlappingOverload"): 5,
    # Two variance suggestions, both refused: `_N` is read back through `value`, and `_E` sits inside
    # a contravariant `Matcher`, where the flips cancel and a `Matcher[Dog]` would reach animals
    ("assertpy2/_engine/_typing.py", "reportInvalidTypeVarUse"): 1,
    ("assertpy2/assertpy.py", "reportIncompatibleMethodOverride"): 3,
    ("assertpy2/helpers.py", "reportIncompatibleMethodOverride"): 2,
    ("assertpy2/assertpy.py", "reportAttributeAccessIssue"): 3,
    ("assertpy2/assertpy.py", "reportReturnType"): 4,
    # the failure record is `| None` in general and never None at this call, as the comment there says
    ("assertpy2/snapshot.py", "reportArgumentType"): 1,
    # both branches that reach the read assign it first, through a `try` pyright does not follow
    ("assertpy2/snapshot.py", "reportPossiblyUnboundVariable"): 2,
}
