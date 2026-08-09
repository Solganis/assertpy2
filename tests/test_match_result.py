"""A matcher answers with one object instead of three calls, and either half of the pair is enough.

`matches()` stayed the cheap primitive because it is what `==` calls, and a matcher is a dict value in
`matches_structure` and a snapshot placeholder: a comparison must not have to build a result. `evaluate()`
is for the caller that would otherwise ask the same value three questions, which is how a matcher over a
one-shot iterator used to name the wrong element.
"""

import pytest

from assertpy2 import AssertionFailure, BaseMatcher, MatchResult, assert_that, match
from assertpy2.matchers import _evaluate_matcher


class TestOneLookInsteadOfThree:
    def test_a_result_carries_the_verdict_the_requirement_and_the_reason(self):
        result = match.is_positive().evaluate(-5)
        assert_that(result.matched).is_false()
        assert_that(result.description).is_equal_to("a positive value")
        assert_that(result.mismatch).is_equal_to("was <-5>")

    def test_a_matched_result_says_nothing_about_why(self):
        result = match.is_positive().evaluate(5)
        assert_that(result.matched).is_true()
        assert_that(result.mismatch).is_empty()

    def test_a_result_is_truthy_exactly_when_it_matched(self):
        assert_that(bool(match.is_positive().evaluate(5))).is_true()
        assert_that(bool(match.is_positive().evaluate(-5))).is_false()

    def test_the_default_composes_the_three_older_methods(self):
        # every built-in matcher predates evaluate(), and none of them changed to answer it
        matcher = match.greater_than(3)
        result = matcher.evaluate(1)
        assert_that(result.description).is_equal_to(matcher.describe())
        assert_that(result.mismatch).is_equal_to(matcher.describe_mismatch(1))


class TestEitherHalfOfThePairIsEnough:
    def test_a_matcher_that_implements_only_matches_still_evaluates(self):
        class OnlyMatches(BaseMatcher):
            def matches(self, value):
                return value == "ok"

            def describe(self):
                return "the string ok"

        assert_that(OnlyMatches().evaluate("ok").matched).is_true()
        assert_that(OnlyMatches().evaluate("no").mismatch).is_equal_to("was <no>")

    def test_a_matcher_that_implements_only_evaluate_still_matches(self):
        class OnlyEvaluates(BaseMatcher):
            def evaluate(self, value):
                return MatchResult(matched=value == "ok", description="the string ok", mismatch=f"was <{value}>")

            def describe(self):
                return "the string ok"

        assert_that(OnlyEvaluates().matches("ok")).is_true()
        assert_that(OnlyEvaluates().matches("no")).is_false()

    def test_a_matcher_that_implements_only_evaluate_works_in_an_assertion(self):
        class OnlyEvaluates(BaseMatcher):
            def evaluate(self, value):
                return MatchResult(matched=value > 0, description="a positive value", mismatch=f"was <{value}>")

            def describe(self):
                return "a positive value"

        assert_that(5).satisfies(OnlyEvaluates())
        with pytest.raises(AssertionFailure) as failure:
            assert_that(-5).satisfies(OnlyEvaluates())
        assert_that(str(failure.value)).is_equal_to("Expected a positive value, but was <-5>.")

    def test_a_matcher_that_implements_neither_says_so_instead_of_recursing(self):
        class Neither(BaseMatcher):
            def describe(self):
                return "nothing at all"

        with pytest.raises(NotImplementedError) as from_matches:
            Neither().matches(1)
        with pytest.raises(NotImplementedError) as from_evaluate:
            Neither().evaluate(1)
        for raised in (from_matches, from_evaluate):
            assert_that(str(raised.value)).is_equal_to("a matcher must implement matches() or evaluate()")


class TestADuckTypedMatcherIsBridgedToo:
    """The `Matcher` protocol is three methods and stays three: widening it would un-match every
    third-party matcher written against the documented shape."""

    class _Duck:
        def matches(self, value):
            return value == 7

        def describe(self):
            return "the number seven"

        def describe_mismatch(self, value):
            return f"was <{value}>, not seven"

    def test_it_evaluates_without_inheriting_anything(self):
        result = _evaluate_matcher(self._Duck(), 1)
        assert_that(result.matched).is_false()
        assert_that(result.description).is_equal_to("the number seven")
        assert_that(result.mismatch).is_equal_to("was <1>, not seven")

    def test_a_match_leaves_the_reason_empty(self):
        assert_that(_evaluate_matcher(self._Duck(), 7).mismatch).is_empty()

    def test_it_still_works_through_an_assertion(self):
        assert_that(7).satisfies(self._Duck())
        with pytest.raises(AssertionFailure) as failure:
            assert_that(1).satisfies(self._Duck())
        assert_that(str(failure.value)).contains("not seven")


class TestTheStructureMatcherWalksOnceInsteadOfTwice:
    def test_the_result_says_the_same_thing_the_two_calls_did(self):
        matcher = match.structure({"role": match.is_in("admin", "user")})
        value = {"role": "superadmin"}
        result = matcher.evaluate(value)
        assert_that(result.matched).is_equal_to(matcher.matches(value))
        assert_that(result.mismatch).is_equal_to(matcher.describe_mismatch(value))

    def test_a_value_that_is_not_a_mapping_is_reported_the_same_way_by_both(self):
        matcher = match.structure({"role": match.is_in("admin")})
        result = matcher.evaluate(5)
        assert_that(result.matched).is_false()
        assert_that(result.mismatch).is_equal_to(matcher.describe_mismatch(5))
        assert_that(result.mismatch).is_equal_to("was not a mapping: <5>")

    def test_a_match_reports_no_reason(self):
        assert_that(match.structure({"role": match.is_in("admin")}).evaluate({"role": "admin"}).mismatch).is_empty()
