import re
from datetime import date, datetime, timedelta, timezone
from math import inf, nan

import pytest

from assertpy2 import AssertionFailure, Matcher, assert_that, match
from assertpy2.matchers import BaseMatcher


class TestTemporalMatchers:
    def test_is_now_matches_current(self):
        assert_that(datetime.now()).satisfies(match.is_now())

    def test_is_now_within_and_outside_delta(self):
        assert_that(datetime.now() - timedelta(seconds=1)).satisfies(match.is_now(3))
        assert_that(match.is_now(3).matches(datetime.now() - timedelta(seconds=30))).is_false()

    def test_is_now_default_window_is_two_seconds(self):
        # every other case either passes an explicit delta or uses an unshifted now(), both of which
        # hold under any positive default, so the default itself was pinned by nothing
        assert_that(match.is_now().matches(datetime.now() - timedelta(seconds=1.5))).is_true()
        assert_that(match.is_now().matches(datetime.now() - timedelta(seconds=2.5))).is_false()

    def test_is_now_accepts_timedelta_delta(self):
        assert_that(datetime.now()).satisfies(match.is_now(timedelta(seconds=5)))

    def test_is_now_timezone_aware(self):
        assert_that(datetime.now(timezone.utc)).satisfies(match.is_now())
        assert_that(datetime.now(timezone(timedelta(hours=5)))).satisfies(match.is_now())

    def test_is_now_rejects_non_datetime(self):
        assert_that(match.is_now().matches("2020-01-01")).is_false()
        assert_that(match.is_now().matches(12345)).is_false()
        assert_that(match.is_now().matches(date.today())).is_false()

    def test_is_now_in_expected_dict(self):
        assert_that({"id": "x", "ts": datetime.now()}).is_equal_to({"id": "x", "ts": match.is_now(3)})

    def test_is_now_describe(self):
        assert_that(match.is_now(3).describe()).contains("within").contains("of now")

    def test_is_before_and_after(self):
        assert_that(datetime(2000, 1, 1)).satisfies(match.is_before(datetime(2020, 1, 1)))
        assert_that(datetime(2030, 1, 1)).satisfies(match.is_after(datetime(2020, 1, 1)))
        assert_that(match.is_before(datetime(2020, 1, 1)).matches(datetime(2030, 1, 1))).is_false()
        assert_that(match.is_after(datetime(2020, 1, 1)).matches(datetime(2000, 1, 1))).is_false()

    def test_is_before_after_reject_non_comparable(self):
        # naive value vs aware reference is not comparable -> no match, no raise
        assert_that(match.is_before(datetime.now(timezone.utc)).matches(datetime(2000, 1, 1))).is_false()
        assert_that(match.is_after(datetime.now(timezone.utc)).matches(datetime(2000, 1, 1))).is_false()
        assert_that(match.is_before(datetime(2020, 1, 1)).matches("not a date")).is_false()
        assert_that(match.is_after(datetime(2020, 1, 1)).matches(42)).is_false()

    def test_is_before_after_describe(self):
        assert_that(match.is_before(datetime(2020, 1, 1)).describe()).contains("before")
        assert_that(match.is_after(datetime(2020, 1, 1)).describe()).contains("after")


class TestNumericMatchersRejectNonComparable:
    def test_is_positive_negative_no_raise_on_non_comparable(self):
        # a non-comparable operand must yield a non-match, never a raw TypeError
        assert_that(match.is_positive().matches("hello")).is_false()
        assert_that(match.is_negative().matches("hello")).is_false()
        assert_that(match.is_positive().matches(None)).is_false()

    def test_is_positive_no_typeerror_leak_via_combinator_and_pipeline(self):
        # a non-comparable element must not leak TypeError out of satisfies/any_satisfy/each
        assert_that("hello").satisfies(match.is_positive() | match.equal_to("hello"))
        assert_that(["two", 1]).any_satisfy(match.is_positive())
        with pytest.raises(AssertionError):
            assert_that(["a", "b"]).each(match.is_negative())

    def test_matches_structure_with_combinator_matcher_is_clean(self):
        # describe_mismatch re-evaluates every sub-matcher of an AllOf; a guarded sub-matcher
        # (is_positive on a str) must not leak TypeError out of matches_structure/satisfies/each
        with pytest.raises(AssertionError):
            assert_that({"n": "x"}).matches_structure({"n": match.is_instance_of(int) & match.is_positive()})


class TestMatchesRegex:
    def test_invalid_pattern_raises_at_construction(self):
        # an invalid pattern must fail fast at the call site, not later inside matches()/==/a combinator
        with pytest.raises(re.error):
            match.matches_regex("(")

    def test_valid_regex_used_in_combinator_renders_mismatch_cleanly(self):
        assert_that("foo").satisfies(match.matches_regex("^f"))
        with pytest.raises(AssertionError):
            assert_that("x").satisfies(match.is_non_empty_string() & match.matches_regex("zzz"))


class TestBaseMatcherAbstract:
    def test_matches_not_implemented(self):
        with pytest.raises(NotImplementedError):
            BaseMatcher().matches(42)

    def test_describe_not_implemented(self):
        with pytest.raises(NotImplementedError):
            BaseMatcher().describe()


class TestMatcherProtocol:
    def test_base_matcher_is_matcher(self):
        assert_that(isinstance(match.equal_to(1), Matcher)).is_true()

    def test_all_of_is_matcher(self):
        assert_that(isinstance(match.greater_than(0) & match.less_than(10), Matcher)).is_true()

    def test_any_of_is_matcher(self):
        assert_that(isinstance(match.equal_to(1) | match.equal_to(2), Matcher)).is_true()

    def test_not_is_matcher(self):
        assert_that(isinstance(~match.equal_to(1), Matcher)).is_true()


class TestEqualToMatcher:
    def test_matches(self):
        assert_that(match.equal_to(42).matches(42)).is_true()

    def test_does_not_match(self):
        assert_that(match.equal_to(42).matches(99)).is_false()

    def test_describe(self):
        assert_that(match.equal_to(42).describe()).is_equal_to("a value equal to <42>")

    def test_describe_mismatch(self):
        assert_that(match.equal_to(42).describe_mismatch(99)).is_equal_to("was <99>")

    def test_repr(self):
        assert_that(repr(match.equal_to(42))).is_equal_to("a value equal to <42>")


class TestGreaterThanMatcher:
    def test_matches(self):
        assert_that(match.greater_than(5).matches(10)).is_true()

    def test_does_not_match(self):
        assert_that(match.greater_than(5).matches(3)).is_false()

    def test_boundary(self):
        assert_that(match.greater_than(5).matches(5)).is_false()

    def test_describe(self):
        assert_that(match.greater_than(5).describe()).is_equal_to("a value greater than <5>")


class TestGreaterThanOrEqualToMatcher:
    def test_matches(self):
        assert_that(match.greater_than_or_equal_to(5).matches(5)).is_true()
        assert_that(match.greater_than_or_equal_to(5).matches(6)).is_true()

    def test_does_not_match(self):
        assert_that(match.greater_than_or_equal_to(5).matches(4)).is_false()


class TestLessThanMatcher:
    def test_matches(self):
        assert_that(match.less_than(5).matches(3)).is_true()

    def test_does_not_match(self):
        assert_that(match.less_than(5).matches(10)).is_false()

    def test_boundary(self):
        assert_that(match.less_than(5).matches(5)).is_false()

    def test_describe(self):
        assert_that(match.less_than(5).describe()).is_equal_to("a value less than <5>")


class TestLessThanOrEqualToMatcher:
    def test_matches(self):
        assert_that(match.less_than_or_equal_to(5).matches(5)).is_true()
        assert_that(match.less_than_or_equal_to(5).matches(4)).is_true()

    def test_does_not_match(self):
        assert_that(match.less_than_or_equal_to(5).matches(6)).is_false()


class TestBetweenMatcher:
    def test_matches(self):
        assert_that(match.between(1, 10).matches(5)).is_true()

    def test_boundaries_inclusive(self):
        assert_that(match.between(1, 10).matches(1)).is_true()
        assert_that(match.between(1, 10).matches(10)).is_true()

    def test_does_not_match(self):
        assert_that(match.between(1, 10).matches(0)).is_false()
        assert_that(match.between(1, 10).matches(11)).is_false()

    def test_describe(self):
        assert_that(match.between(1, 10).describe()).is_equal_to("a value between <1> and <10>")


class TestCloseToMatcher:
    def test_matches(self):
        assert_that(match.close_to(10.0, 0.5).matches(10.3)).is_true()

    def test_does_not_match(self):
        assert_that(match.close_to(10.0, 0.5).matches(11.0)).is_false()

    def test_describe(self):
        assert_that(match.close_to(10.0, 0.5).describe()).is_equal_to("a value within <0.5> of <10.0>")

    def test_infinity_is_close_to_itself_like_fluent(self):
        # parity with assert_that(inf).is_close_to(inf, 1), which passes: both APIs must agree
        assert_that(match.close_to(inf, 1).matches(inf)).is_true()
        assert_that(match.close_to(inf, 1).matches(5.0)).is_false()

    def test_nan_is_never_close(self):
        assert_that(match.close_to(5.0, 1).matches(nan)).is_false()
        assert_that(match.close_to(nan, 1).matches(5.0)).is_false()

    def test_nan_tolerance_never_matches(self):
        assert_that(match.close_to(5.0, nan).matches(5.0)).is_false()


class TestOrderingMatchersIncompatibleTypes:
    def test_greater_than_incompatible(self):
        assert_that(match.greater_than(5).matches("hello")).is_false()

    def test_greater_than_none(self):
        assert_that(match.greater_than(5).matches(None)).is_false()

    def test_greater_than_or_equal_to_incompatible(self):
        assert_that(match.greater_than_or_equal_to(5).matches("hello")).is_false()

    def test_less_than_incompatible(self):
        assert_that(match.less_than(5).matches("hello")).is_false()

    def test_less_than_none(self):
        assert_that(match.less_than(5).matches(None)).is_false()

    def test_less_than_or_equal_to_incompatible(self):
        assert_that(match.less_than_or_equal_to(5).matches([1, 2])).is_false()

    def test_between_incompatible(self):
        assert_that(match.between(1, 10).matches("hello")).is_false()

    def test_between_none(self):
        assert_that(match.between(1, 10).matches(None)).is_false()

    def test_close_to_incompatible(self):
        assert_that(match.close_to(10.0, 0.5).matches("hello")).is_false()

    def test_close_to_none(self):
        assert_that(match.close_to(10.0, 0.5).matches(None)).is_false()

    def test_composition_with_type_check(self):
        matcher = match.is_instance_of(int) & match.greater_than(5)
        assert_that(matcher.matches("hello")).is_false()
        assert_that(matcher.matches(10)).is_true()


class TestIsNoneMatcher:
    def test_matches(self):
        assert_that(match.is_none().matches(None)).is_true()

    def test_does_not_match(self):
        assert_that(match.is_none().matches(0)).is_false()
        assert_that(match.is_none().matches("")).is_false()

    def test_describe(self):
        assert_that(match.is_none().describe()).is_equal_to("None")


class TestIsNotNoneMatcher:
    def test_matches(self):
        assert_that(match.is_not_none().matches(0)).is_true()
        assert_that(match.is_not_none().matches("")).is_true()

    def test_does_not_match(self):
        assert_that(match.is_not_none().matches(None)).is_false()

    def test_describe(self):
        assert_that(match.is_not_none().describe()).is_equal_to("a non-None value")


class TestIsInstanceOfMatcher:
    def test_matches(self):
        assert_that(match.is_instance_of(str).matches("hello")).is_true()
        assert_that(match.is_instance_of(int).matches(42)).is_true()

    def test_subclass(self):
        assert_that(match.is_instance_of(object).matches("hello")).is_true()

    def test_does_not_match(self):
        assert_that(match.is_instance_of(str).matches(42)).is_false()

    def test_describe(self):
        assert_that(match.is_instance_of(str).describe()).is_equal_to("an instance of <str>")

    def test_describe_mismatch(self):
        assert_that(match.is_instance_of(str).describe_mismatch(42)).is_equal_to("was <42> of type <int>")


class TestIsTruthyMatcher:
    def test_matches(self):
        assert_that(match.is_truthy().matches(1)).is_true()
        assert_that(match.is_truthy().matches("x")).is_true()

    def test_does_not_match(self):
        assert_that(match.is_truthy().matches(0)).is_false()
        assert_that(match.is_truthy().matches("")).is_false()
        assert_that(match.is_truthy().matches(None)).is_false()


class TestIsFalsyMatcher:
    def test_matches(self):
        assert_that(match.is_falsy().matches(0)).is_true()
        assert_that(match.is_falsy().matches("")).is_true()
        assert_that(match.is_falsy().matches(None)).is_true()

    def test_does_not_match(self):
        assert_that(match.is_falsy().matches(1)).is_false()


class TestHasLengthMatcher:
    def test_matches(self):
        assert_that(match.has_length(3).matches("foo")).is_true()
        assert_that(match.has_length(2).matches([1, 2])).is_true()

    def test_does_not_match(self):
        assert_that(match.has_length(3).matches("ab")).is_false()

    def test_describe(self):
        assert_that(match.has_length(3).describe()).is_equal_to("a value of length <3>")

    def test_describe_mismatch(self):
        assert_that(match.has_length(3).describe_mismatch("ab")).is_equal_to("was <ab> with length <2>")

    def test_non_sized_does_not_match(self):
        assert_that(match.has_length(3).matches(5)).is_false()
        assert_that(match.has_length(3).describe_mismatch(5)).contains("no length")


class TestIsEmptyMatcher:
    def test_matches(self):
        assert_that(match.is_empty().matches("")).is_true()
        assert_that(match.is_empty().matches([])).is_true()

    def test_does_not_match(self):
        assert_that(match.is_empty().matches("x")).is_false()

    def test_non_sized_does_not_match(self):
        assert_that(match.is_empty().matches(5)).is_false()


class TestIsNotEmptyMatcher:
    def test_matches(self):
        assert_that(match.is_not_empty().matches("x")).is_true()

    def test_does_not_match(self):
        assert_that(match.is_not_empty().matches("")).is_false()

    def test_non_sized_does_not_match(self):
        assert_that(match.is_not_empty().matches(5)).is_false()


class TestIsPositiveMatcher:
    def test_matches(self):
        assert_that(match.is_positive().matches(1)).is_true()
        assert_that(match.is_positive().matches(0.1)).is_true()

    def test_does_not_match(self):
        assert_that(match.is_positive().matches(0)).is_false()
        assert_that(match.is_positive().matches(-1)).is_false()


class TestIsNegativeMatcher:
    def test_matches(self):
        assert_that(match.is_negative().matches(-1)).is_true()

    def test_does_not_match(self):
        assert_that(match.is_negative().matches(0)).is_false()
        assert_that(match.is_negative().matches(1)).is_false()


class TestIsZeroMatcher:
    def test_matches(self):
        assert_that(match.is_zero().matches(0)).is_true()
        assert_that(match.is_zero().matches(0.0)).is_true()

    def test_does_not_match(self):
        assert_that(match.is_zero().matches(1)).is_false()


class TestContainsStringMatcher:
    def test_matches(self):
        assert_that(match.contains_string("oo").matches("foobar")).is_true()

    def test_does_not_match(self):
        assert_that(match.contains_string("xyz").matches("foobar")).is_false()

    def test_non_string(self):
        assert_that(match.contains_string("x").matches(42)).is_false()


class TestMatchesRegexMatcher:
    def test_matches(self):
        assert_that(match.matches_regex(r"\d+").matches("abc123")).is_true()

    def test_does_not_match(self):
        assert_that(match.matches_regex(r"^\d+$").matches("abc")).is_false()

    def test_non_string(self):
        assert_that(match.matches_regex(r"\d").matches(42)).is_false()


class TestStartsWithMatcher:
    def test_matches(self):
        assert_that(match.starts_with("foo").matches("foobar")).is_true()

    def test_does_not_match(self):
        assert_that(match.starts_with("bar").matches("foobar")).is_false()

    def test_non_string(self):
        assert_that(match.starts_with("x").matches(42)).is_false()


class TestEndsWithMatcher:
    def test_matches(self):
        assert_that(match.ends_with("bar").matches("foobar")).is_true()

    def test_does_not_match(self):
        assert_that(match.ends_with("foo").matches("foobar")).is_false()

    def test_non_string(self):
        assert_that(match.ends_with("x").matches(42)).is_false()


class TestAllOfMatcher:
    def test_matches(self):
        matcher = match.greater_than(0) & match.less_than(10)
        assert_that(matcher.matches(5)).is_true()

    def test_does_not_match_first(self):
        matcher = match.greater_than(0) & match.less_than(10)
        assert_that(matcher.matches(-1)).is_false()

    def test_does_not_match_second(self):
        matcher = match.greater_than(0) & match.less_than(10)
        assert_that(matcher.matches(15)).is_false()

    def test_describe(self):
        matcher = match.greater_than(0) & match.less_than(10)
        assert_that(matcher.describe()).contains("and")

    def test_describe_mismatch(self):
        matcher = match.greater_than(0) & match.less_than(10)
        result = matcher.describe_mismatch(15)
        assert_that(result).contains("15")
        assert_that(result).contains("did not satisfy")

    def test_triple_chain(self):
        matcher = match.greater_than(0) & match.less_than(10) & match.is_instance_of(int)
        assert_that(matcher.matches(5)).is_true()
        assert_that(matcher.matches(5.5)).is_false()

    def test_all_of_factory(self):
        matcher = match.all_of(match.greater_than(0), match.less_than(10))
        assert_that(matcher.matches(5)).is_true()
        assert_that(matcher.matches(15)).is_false()


class TestAnyOfMatcher:
    def test_matches_first(self):
        matcher = match.equal_to(1) | match.equal_to(2)
        assert_that(matcher.matches(1)).is_true()

    def test_matches_second(self):
        matcher = match.equal_to(1) | match.equal_to(2)
        assert_that(matcher.matches(2)).is_true()

    def test_does_not_match(self):
        matcher = match.equal_to(1) | match.equal_to(2)
        assert_that(matcher.matches(3)).is_false()

    def test_describe(self):
        matcher = match.equal_to(1) | match.equal_to(2)
        assert_that(matcher.describe()).contains("or")

    def test_describe_mismatch(self):
        matcher = match.equal_to(1) | match.equal_to(2)
        result = matcher.describe_mismatch(3)
        assert_that(result).contains("3")
        assert_that(result).contains("satisfied none of")

    def test_triple_chain(self):
        matcher = match.equal_to(1) | match.equal_to(2) | match.equal_to(3)
        assert_that(matcher.matches(3)).is_true()
        assert_that(matcher.matches(4)).is_false()

    def test_any_of_factory(self):
        matcher = match.any_of(match.equal_to(1), match.equal_to(2))
        assert_that(matcher.matches(1)).is_true()
        assert_that(matcher.matches(3)).is_false()


class TestNotMatcher:
    def test_matches(self):
        matcher = ~match.equal_to(1)
        assert_that(matcher.matches(2)).is_true()

    def test_does_not_match(self):
        matcher = ~match.equal_to(1)
        assert_that(matcher.matches(1)).is_false()

    def test_describe(self):
        matcher = ~match.equal_to(1)
        assert_that(matcher.describe()).starts_with("not ")

    def test_describe_mismatch(self):
        matcher = ~match.equal_to(1)
        result = matcher.describe_mismatch(1)
        assert_that(result).contains("unexpectedly matched")

    def test_not_factory(self):
        matcher = match.not_(match.equal_to(1))
        assert_that(matcher.matches(2)).is_true()
        assert_that(matcher.matches(1)).is_false()


class TestComposedMatchers:
    def test_and_or(self):
        matcher = (match.greater_than(0) & match.less_than(10)) | match.equal_to(-1)
        assert_that(matcher.matches(5)).is_true()
        assert_that(matcher.matches(-1)).is_true()
        assert_that(matcher.matches(15)).is_false()

    def test_not_and(self):
        matcher = ~(match.greater_than(0) & match.less_than(10))
        assert_that(matcher.matches(15)).is_true()
        assert_that(matcher.matches(-1)).is_true()
        assert_that(matcher.matches(5)).is_false()

    def test_or_and(self):
        matcher = (match.equal_to(1) | match.equal_to(2)) & match.is_instance_of(int)
        assert_that(matcher.matches(1)).is_true()
        assert_that(matcher.matches(2)).is_true()
        assert_that(matcher.matches(3)).is_false()


class TestSatisfies:
    def test_with_matcher(self):
        assert_that(7).satisfies(match.greater_than(5))

    def test_with_composed_matcher(self):
        assert_that(7).satisfies(match.greater_than(5) & match.less_than(10))

    def test_with_callable(self):
        assert_that(42).satisfies(lambda x: x % 2 == 0)

    def test_failure_with_matcher(self):
        with pytest.raises(AssertionError, match="Expected a value greater than <10>"):
            assert_that(5).satisfies(match.greater_than(10))

    def test_failure_with_callable(self):
        with pytest.raises(AssertionError, match="to satisfy"):
            assert_that(3).satisfies(lambda x: x % 2 == 0)

    def test_invalid_arg(self):
        with pytest.raises(TypeError, match="given matcher arg must be a Matcher or a callable"):
            assert_that(1).satisfies("not a matcher")

    def test_chaining(self):
        assert_that(7).satisfies(match.greater_than(5)).is_less_than(10)

    def test_failure_attaches_match_diff(self):
        try:
            assert_that(5).satisfies(match.greater_than(10))
        except AssertionFailure as exc:
            assert_that(exc.diff.kind).is_equal_to("match")
            assert_that(exc.diff.entries[0].path).is_equal_to(".")
            assert_that(exc.diff.entries[0].actual).is_equal_to(5)
        else:
            raise AssertionError("expected AssertionFailure") from None


class TestEach:
    def test_with_matcher(self):
        assert_that([1, 2, 3]).each(match.is_positive())

    def test_with_composed_matcher(self):
        assert_that([5, 6, 7]).each(match.between(1, 10))

    def test_with_callable(self):
        assert_that([2, 4, 6]).each(lambda x: x % 2 == 0)

    def test_failure_with_matcher(self):
        with pytest.raises(AssertionError, match="item at index 2"):
            assert_that([1, 2, -3]).each(match.is_positive())

    def test_failure_message_includes_description(self):
        with pytest.raises(AssertionError, match="a positive value"):
            assert_that([1, -1]).each(match.is_positive())

    def test_failure_with_callable(self):
        with pytest.raises(AssertionError, match="item at index 1"):
            assert_that([2, 3, 4]).each(lambda x: x % 2 == 0)

    def test_empty_collection(self):
        assert_that([]).each(match.is_positive())

    def test_invalid_arg(self):
        with pytest.raises(TypeError, match="given matcher arg must be a Matcher or a callable"):
            assert_that([1, 2]).each("not a matcher")

    def test_not_iterable(self):
        with pytest.raises(TypeError, match="val must be iterable"):
            assert_that(42).each(match.is_positive())

    def test_chaining(self):
        assert_that([1, 2, 3]).each(match.is_positive()).is_length(3)

    def test_with_extracting(self):
        users = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        assert_that(users).extracting("age").each(match.between(18, 120))

    def test_failure_attaches_match_diff(self):
        try:
            assert_that([1, 2, -3]).each(match.is_positive())
        except AssertionFailure as exc:
            assert_that(exc.diff.kind).is_equal_to("match")
            assert_that(exc.diff.entries[0].path).is_equal_to("[2]")
            assert_that(exc.diff.entries[0].actual).is_equal_to(-3)
        else:
            raise AssertionError("expected AssertionFailure") from None


class TestContainsWithMatcher:
    def test_single_matcher(self):
        assert_that([1, 5, 10]).contains(match.greater_than(7))

    def test_single_matcher_failure(self):
        with pytest.raises(AssertionError, match="to contain item matching"):
            assert_that([1, 2, 3]).contains(match.greater_than(10))

    def test_multiple_with_matcher(self):
        assert_that([1, 5, 10]).contains(match.greater_than(7), 1)

    def test_multiple_with_matcher_failure(self):
        with pytest.raises(AssertionError, match="did not contain"):
            assert_that([1, 2, 3]).contains(match.greater_than(10), 99)

    def test_mixed_items_and_matchers(self):
        assert_that([1, 5, 10]).contains(1, match.greater_than(7))

    def test_matcher_with_strings_in_list(self):
        assert_that(["hello", "world"]).contains(match.starts_with("hel"))

    def test_matcher_with_set(self):
        assert_that({1, 5, 10}).contains(match.greater_than(7))


class TestDescribeCoverage:
    def test_greater_than_or_equal_to_describe(self):
        assert_that(match.greater_than_or_equal_to(5).describe()).contains("greater than or equal to")

    def test_less_than_or_equal_to_describe(self):
        assert_that(match.less_than_or_equal_to(5).describe()).contains("less than or equal to")

    def test_is_truthy_describe(self):
        assert_that(match.is_truthy().describe()).is_equal_to("a truthy value")

    def test_is_falsy_describe(self):
        assert_that(match.is_falsy().describe()).is_equal_to("a falsy value")

    def test_is_empty_describe(self):
        assert_that(match.is_empty().describe()).is_equal_to("an empty value")

    def test_is_not_empty_describe(self):
        assert_that(match.is_not_empty().describe()).is_equal_to("a non-empty value")

    def test_is_negative_describe(self):
        assert_that(match.is_negative().describe()).is_equal_to("a negative value")

    def test_is_zero_describe(self):
        assert_that(match.is_zero().describe()).is_equal_to("zero")

    def test_contains_string_describe(self):
        assert_that(match.contains_string("foo").describe()).is_equal_to("a string containing <foo>")

    def test_matches_regex_describe(self):
        assert_that(match.matches_regex(r"\d+").describe()).contains("matching pattern")

    def test_starts_with_describe(self):
        assert_that(match.starts_with("foo").describe()).is_equal_to("a string starting with <foo>")

    def test_ends_with_describe(self):
        assert_that(match.ends_with("bar").describe()).is_equal_to("a string ending with <bar>")


class TestTheTextMatchersAgreeWithTheirMethods:
    """A matcher and the method of the same name may differ in strictness, never in the answer.

    `assert_that(b"hello").contains(b"ell")` passed while `match.contains_string(b"ell")` failed: the
    matchers demanded `str`, and the methods had grown bytes support without them.  A matcher is what
    `contains()`, `satisfies()` and the `==` protocol all delegate to, so the disagreement reached
    every one of those.
    """

    @pytest.mark.parametrize(
        ("method", "matcher", "operand"),
        [
            ("contains", match.contains_string, b"ell"),
            ("starts_with", match.starts_with, b"he"),
            ("ends_with", match.ends_with, b"lo"),
        ],
    )
    def test_bytes_are_matched_the_way_the_method_matches_them(self, method, matcher, operand):
        getattr(assert_that(b"hello"), method)(operand)
        assert_that(b"hello").satisfies(matcher(operand))
        assert_that(bytearray(b"hello")).satisfies(matcher(operand))

    @pytest.mark.parametrize("matcher", [match.contains_string, match.starts_with, match.ends_with])
    def test_the_two_text_types_never_match_each_other(self, matcher):
        # the method raises TypeError on this pair; a matcher answers instead of raising, and the
        # answer is no.  Anything else would make `b"hello" == match.starts_with("he")` a silent yes
        assert_that(matcher("he").matches(b"hello")).is_false()
        assert_that(matcher(b"he").matches("hello")).is_false()

    @pytest.mark.parametrize("matcher", [match.contains_string, match.starts_with, match.ends_with])
    def test_a_value_that_is_not_text_at_all_is_no_match(self, matcher):
        assert_that(matcher("he").matches(["he", "llo"])).is_false()
        assert_that(matcher("he").matches(None)).is_false()

    def test_a_bytes_operand_is_described_as_bytes(self):
        # "a string containing <b'ell'>" described the wrong thing about the one operand that needed it
        assert_that(match.contains_string(b"ell").describe()).is_equal_to("bytes containing <b'ell'>")
        assert_that(match.starts_with(b"he").describe()).is_equal_to("bytes starting with <b'he'>")
        assert_that(match.ends_with(b"lo").describe()).is_equal_to("bytes ending with <b'lo'>")


class TestMatcherEqProtocol:
    def test_eq_positive_match(self):
        assert 5 == match.is_positive()

    def test_eq_negative_match(self):
        assert (-5 == match.is_positive()) is False

    def test_eq_equal_to(self):
        assert 42 == match.equal_to(42)

    def test_eq_between(self):
        assert 5 == match.between(1, 10)

    def test_eq_string_matcher(self):
        assert "hello" == match.is_non_empty_string()

    def test_eq_not_equal(self):
        assert -5 != match.is_positive()

    def test_eq_reverse_order(self):
        assert match.is_positive() == 5

    def test_eq_dict(self):
        assert {"id": 5, "name": "Alice"} == {"id": match.is_positive(), "name": match.is_non_empty_string()}

    def test_eq_dict_mismatch(self):
        assert {"id": -5} != {"id": match.is_positive()}

    def test_eq_nested_dict(self):
        data = {"user": {"name": "Alice", "age": 30}}
        assert data == {"user": {"name": match.is_non_empty_string(), "age": match.is_positive()}}

    def test_eq_list(self):
        assert [1, 2, 3] == [match.is_positive(), match.is_positive(), match.is_positive()]

    def test_eq_composition_and(self):
        assert 5 == (match.is_positive() & match.less_than(10))

    def test_eq_composition_or(self):
        assert -1 == (match.is_positive() | match.is_negative())

    def test_eq_negated_matcher(self):
        assert -5 == ~match.is_positive()

    def test_eq_unorderable_operand_is_false(self):
        assert (match.is_positive() == object()) is False

    def test_eq_reflected_unorderable_operand_is_false(self):
        assert (object() == match.is_positive()) is False

    def test_eq_matcher_vs_matcher_is_false(self):
        assert (match.is_positive() == match.is_positive()) is False

    def test_eq_ambiguous_truth_value_is_false(self):
        class _Elementwise:
            def __bool__(self):
                raise ValueError("ambiguous")

        class _ArrayLike:
            def __gt__(self, other):
                return _Elementwise()

        assert (match.is_positive() == _ArrayLike()) is False

    def test_membership_with_mixed_types_does_not_raise(self):
        assert match.is_positive() in [object(), "x", 5]
        assert match.is_positive() not in [object(), "x", -5]

    def test_hash_unique_instances(self):
        first_matcher = match.is_positive()
        second_matcher = match.is_positive()
        matcher_set = {first_matcher, second_matcher}
        assert_that(matcher_set).is_length(2)

    def test_hash_same_instance(self):
        matcher = match.is_positive()
        matcher_set = {matcher, matcher}
        assert_that(matcher_set).is_length(1)

    def test_repr_unchanged(self):
        assert_that(repr(match.is_positive())).is_equal_to("a positive value")

    def test_eq_with_pytest_assert_message(self):
        try:
            assert -5 == match.is_positive()
        except AssertionError:
            pass
        else:
            raise AssertionError("Expected AssertionError")


class TestIsEvenMatcher:
    def test_matches_even(self):
        assert_that(match.is_even().matches(4)).is_true()

    def test_matches_zero(self):
        assert_that(match.is_even().matches(0)).is_true()

    def test_matches_negative_even(self):
        assert_that(match.is_even().matches(-6)).is_true()

    def test_no_match_odd(self):
        assert_that(match.is_even().matches(3)).is_false()

    def test_no_match_bool(self):
        assert_that(match.is_even().matches(True)).is_false()

    def test_no_match_float(self):
        assert_that(match.is_even().matches(4.0)).is_false()

    def test_no_match_string(self):
        assert_that(match.is_even().matches("4")).is_false()

    def test_describe(self):
        assert_that(match.is_even().describe()).is_equal_to("an even integer")

    def test_describe_mismatch_odd(self):
        assert_that(match.is_even().describe_mismatch(3)).is_equal_to("was <3>, which is odd")

    def test_describe_mismatch_not_int(self):
        assert_that(match.is_even().describe_mismatch(3.0)).contains("not an integer")

    def test_describe_mismatch_bool(self):
        assert_that(match.is_even().describe_mismatch(True)).contains("not an integer")

    def test_with_each(self):
        assert_that([2, 4, 6]).each(match.is_even())

    def test_composition_and(self):
        positive_even = match.is_even() & match.is_positive()
        assert_that(positive_even.matches(4)).is_true()
        assert_that(positive_even.matches(-4)).is_false()
        assert_that(positive_even.matches(3)).is_false()

    def test_composition_not(self):
        not_even = ~match.is_even()
        assert_that(not_even.matches(3)).is_true()
        assert_that(not_even.matches(4)).is_false()


class TestIsOddMatcher:
    def test_matches_odd(self):
        assert_that(match.is_odd().matches(3)).is_true()

    def test_matches_negative_odd(self):
        assert_that(match.is_odd().matches(-5)).is_true()

    def test_no_match_even(self):
        assert_that(match.is_odd().matches(4)).is_false()

    def test_no_match_zero(self):
        assert_that(match.is_odd().matches(0)).is_false()

    def test_no_match_bool(self):
        assert_that(match.is_odd().matches(True)).is_false()

    def test_no_match_float(self):
        assert_that(match.is_odd().matches(3.0)).is_false()

    def test_describe(self):
        assert_that(match.is_odd().describe()).is_equal_to("an odd integer")

    def test_describe_mismatch_even(self):
        assert_that(match.is_odd().describe_mismatch(4)).is_equal_to("was <4>, which is even")

    def test_describe_mismatch_not_int(self):
        assert_that(match.is_odd().describe_mismatch("x")).contains("not an integer")

    def test_composition_or(self):
        odd_or_zero = match.is_odd() | match.is_zero()
        assert_that(odd_or_zero.matches(3)).is_true()
        assert_that(odd_or_zero.matches(0)).is_true()
        assert_that(odd_or_zero.matches(4)).is_false()


class TestIsDivisibleByMatcher:
    def test_matches(self):
        assert_that(match.is_divisible_by(3).matches(9)).is_true()

    def test_matches_zero_val(self):
        assert_that(match.is_divisible_by(5).matches(0)).is_true()

    def test_matches_negative(self):
        assert_that(match.is_divisible_by(3).matches(-12)).is_true()

    def test_no_match(self):
        assert_that(match.is_divisible_by(3).matches(10)).is_false()

    def test_no_match_bool(self):
        assert_that(match.is_divisible_by(1).matches(True)).is_false()

    def test_no_match_float(self):
        assert_that(match.is_divisible_by(2).matches(4.0)).is_false()

    def test_describe(self):
        assert_that(match.is_divisible_by(7).describe()).is_equal_to("an integer divisible by <7>")

    def test_describe_mismatch_remainder(self):
        assert_that(match.is_divisible_by(3).describe_mismatch(10)).is_equal_to("was <10>, which has remainder <1>")

    def test_describe_mismatch_not_int(self):
        assert_that(match.is_divisible_by(3).describe_mismatch(10.0)).contains("not an integer")

    def test_composition(self):
        div_by_6 = match.is_divisible_by(2) & match.is_divisible_by(3)
        assert_that(div_by_6.matches(12)).is_true()
        assert_that(div_by_6.matches(9)).is_false()
        assert_that(div_by_6.matches(4)).is_false()

    def test_zero_divisor_rejected(self):
        assert_that(match.is_divisible_by).raises(ValueError).when_called_with(0).contains("must not be zero")


class TestIsCallableMatcher:
    def test_matches_function(self):
        assert_that(match.is_callable().matches(print)).is_true()

    def test_matches_lambda(self):
        assert_that(match.is_callable().matches(lambda: None)).is_true()

    def test_matches_class(self):
        assert_that(match.is_callable().matches(int)).is_true()

    def test_no_match_int(self):
        assert_that(match.is_callable().matches(42)).is_false()

    def test_no_match_string(self):
        assert_that(match.is_callable().matches("foo")).is_false()

    def test_no_match_none(self):
        assert_that(match.is_callable().matches(None)).is_false()

    def test_describe(self):
        assert_that(match.is_callable().describe()).is_equal_to("a callable")

    def test_describe_mismatch(self):
        result = match.is_callable().describe_mismatch(42)
        assert_that(result).contains("42").contains("int").contains("not callable")

    def test_with_satisfies(self):
        assert_that(print).satisfies(match.is_callable())

    def test_composition_not(self):
        not_callable = ~match.is_callable()
        assert_that(not_callable.matches(42)).is_true()
        assert_that(not_callable.matches(print)).is_false()


class TestIsInMatcher:
    def test_matches(self):
        assert_that(match.is_in(1, 2, 3).matches(2)).is_true()

    def test_matches_string(self):
        assert_that(match.is_in("foo", "bar").matches("foo")).is_true()

    def test_no_match(self):
        assert_that(match.is_in(1, 2, 3).matches(4)).is_false()

    def test_no_match_none(self):
        assert_that(match.is_in(1, 2, 3).matches(None)).is_false()

    def test_matches_none_in_values(self):
        assert_that(match.is_in(None, 1, 2).matches(None)).is_true()

    def test_describe(self):
        assert_that(match.is_in(1, 2, 3).describe()).contains("1").contains("2").contains("3")

    def test_describe_mismatch(self):
        result = match.is_in(1, 2).describe_mismatch(5)
        assert_that(result).contains("5").contains("not in")

    def test_with_each(self):
        assert_that([1, 2, 1]).each(match.is_in(1, 2, 3))

    def test_with_each_failure(self):
        try:
            assert_that([1, 2, 4]).each(match.is_in(1, 2, 3))
        except AssertionError as ex:
            assert_that(str(ex)).contains("index 2")

    def test_composition_and(self):
        in_ab_and_positive = match.is_in(1, 2, -3) & match.is_positive()
        assert_that(in_ab_and_positive.matches(1)).is_true()
        assert_that(in_ab_and_positive.matches(-3)).is_false()


class TestHasPropertyMatcher:
    def test_matches_attr(self):
        assert_that(match.has_property("upper").matches("foo")).is_true()

    def test_matches_attr_on_object(self):
        class Obj:
            x = 10

        assert_that(match.has_property("x").matches(Obj())).is_true()

    def test_no_match(self):
        assert_that(match.has_property("nonexistent").matches("foo")).is_false()

    def test_matches_with_value_matcher(self):
        class Obj:
            count = 5

        assert_that(match.has_property("count", match.is_positive()).matches(Obj())).is_true()

    def test_no_match_value_mismatch(self):
        class Obj:
            count = -1

        assert_that(match.has_property("count", match.is_positive()).matches(Obj())).is_false()

    def test_no_match_missing_attr_with_matcher(self):
        class Obj:
            pass

        assert_that(match.has_property("count", match.is_positive()).matches(Obj())).is_false()

    def test_describe_no_matcher(self):
        assert_that(match.has_property("name").describe()).is_equal_to("an object with property <name>")

    def test_describe_with_matcher(self):
        result = match.has_property("count", match.is_positive()).describe()
        assert_that(result).contains("count").contains("a positive value")

    def test_describe_mismatch_missing(self):
        result = match.has_property("foo").describe_mismatch(42)
        assert_that(result).contains("no property <foo>")

    def test_describe_mismatch_value_mismatch(self):
        class Obj:
            count = -1

        result = match.has_property("count", match.is_positive()).describe_mismatch(Obj())
        assert_that(result).contains("count").contains("-1")

    def test_describe_mismatch_has_attr_no_matcher(self):
        result = match.has_property("upper").describe_mismatch("foo")
        assert_that(result).contains("foo")

    def test_with_satisfies(self):
        assert_that("hello").satisfies(match.has_property("upper"))

    def test_composition(self):
        has_x_and_y = match.has_property("x") & match.has_property("y")

        class Good:
            x = 1
            y = 2

        class Bad:
            x = 1

        assert_that(has_x_and_y.matches(Good())).is_true()
        assert_that(has_x_and_y.matches(Bad())).is_false()

    def test_repr(self):
        assert_that(repr(match.has_property("name"))).is_equal_to("an object with property <name>")


class TestCombinatorOperands:
    """A non-matcher operand fails where the expression is written, not where it is later applied."""

    def test_and_rejects_a_non_matcher(self):
        with pytest.raises(TypeError, match=r"cannot combine a Matcher with <int> using '&'"):
            match.is_positive() & 5

    def test_or_rejects_a_non_matcher(self):
        with pytest.raises(TypeError, match=r"cannot combine a Matcher with <str> using '\|'"):
            match.is_positive() | "x"

    def test_matcher_operands_still_combine(self):
        assert_that(5).satisfies(match.is_positive() & match.less_than(10))
        assert_that(5).satisfies(match.is_positive() | match.greater_than(99))


class TestIsTypeOfMatcher:
    """`is_instance_of` accepts a subclass, so a spec could not say "an int, not a bool" until now."""

    def test_rejects_a_subclass(self):
        assert_that(match.is_type_of(int).matches(True)).is_false()
        assert_that(match.is_instance_of(int).matches(True)).is_true()

    def test_matches_the_exact_type(self):
        assert_that(match.is_type_of(int).matches(1)).is_true()
        assert_that(match.is_type_of(bool).matches(True)).is_true()

    def test_describe(self):
        assert_that(match.is_type_of(int).describe()).is_equal_to("exactly type <int>")

    def test_describe_mismatch_names_the_actual_type(self):
        assert_that(match.is_type_of(int).describe_mismatch(True)).contains("bool")

    def test_gives_matches_structure_a_strict_type_check(self):
        assert_that({"n": 1}).matches_structure({"n": match.is_type_of(int)})
        with pytest.raises(AssertionError):
            assert_that({"n": True}).matches_structure({"n": match.is_type_of(int)})

    def test_composes_with_the_operators(self):
        assert_that({"n": 5}).matches_structure({"n": match.is_type_of(int) & match.greater_than(0)})


class TestEqualToStrictTypes:
    """`match.equal_to(x, strict_types=True)` is the same relation the is_equal_to flag applies."""

    def test_rejects_a_type_change(self):
        assert_that(match.equal_to(1).matches(True)).is_true()
        assert_that(match.equal_to(1, strict_types=True).matches(True)).is_false()

    def test_still_matches_the_same_type(self):
        assert_that(match.equal_to(1, strict_types=True).matches(1)).is_true()
        assert_that(match.equal_to(True, strict_types=True).matches(True)).is_true()

    def test_describe_names_the_type(self):
        assert_that(match.equal_to(1, strict_types=True).describe()).contains("of type <int>")
        assert_that(match.equal_to(1).describe()).does_not_contain("of type")

    def test_describe_mismatch_names_the_actual_type(self):
        assert_that(match.equal_to(1, strict_types=True).describe_mismatch(True)).contains("bool")
        assert_that(match.equal_to(1, strict_types=True).describe_mismatch(2)).does_not_contain("of type")

    def test_one_matcher_covers_value_and_type_in_a_spec(self):
        assert_that({"active": True}).matches_structure({"active": match.equal_to(True, strict_types=True)})
        with pytest.raises(AssertionError):
            assert_that({"active": 1}).matches_structure({"active": match.equal_to(True, strict_types=True)})

    def test_the_strict_walk_reaches_inside_a_composite(self):
        # the cases above all compare scalars, which never reach the recursive walk: without it the
        # matcher quietly falls back to plain `==` and the flag stops meaning anything for containers
        assert_that(match.equal_to([1], strict_types=True).matches([True])).is_false()
        assert_that(match.equal_to([1], strict_types=True).matches([1])).is_true()
        assert_that(match.equal_to({"a": 1}, strict_types=True).matches({"a": True})).is_false()
        assert_that(match.equal_to({"a": 1}, strict_types=True).matches({"a": 1})).is_true()

    def test_agrees_with_the_is_equal_to_flag(self):
        # the two spellings of one relation must not drift
        for value, expected in ((True, 1), (1, 1.0), (1, 1)):
            spec_ok = match.equal_to(expected, strict_types=True).matches(value)
            try:
                assert_that(value).is_equal_to(expected, strict_types=True)
                flag_ok = True
            except AssertionError:
                flag_ok = False
            assert_that(spec_ok).is_equal_to(flag_ok)


class TestMatcherDescriptionsNameTheRightValue:
    """Every `describe_mismatch` interpolates the value it was handed.  Handing it something else
    still yields a grammatical sentence, and no test read one, so the whole family could describe the
    wrong thing and stay green."""

    def test_all_of_lists_only_the_matchers_that_failed(self):
        # the filter is negated: listing the ones that passed reads as a plausible sentence too
        composed = match.is_positive() & match.is_even()
        assert_that(composed.describe_mismatch(3)).is_equal_to("<3> did not satisfy: an even integer")

    def test_all_of_lists_several_failures(self):
        composed = match.is_even() & match.greater_than(10)
        assert_that(composed.describe_mismatch(3)).contains("an even integer").contains("greater than <10>")

    def test_any_of_lists_every_alternative(self):
        composed = match.is_even() | match.greater_than(10)
        assert_that(composed.describe_mismatch(-1)).is_equal_to(
            "<-1> satisfied none of: an even integer, a value greater than <10>"
        )

    def test_has_property_delegates_the_property_value_not_the_object(self):
        holder = type("Holder", (), {"x": -1})()
        assert_that(match.has_property("x", match.is_positive()).describe_mismatch(holder)).is_equal_to(
            "property <x> was <-1>, was <-1>"
        )

    @pytest.mark.parametrize("matcher", [match.is_even(), match.is_odd(), match.is_divisible_by(2)])
    def test_the_integer_matchers_name_the_type_they_were_given(self, matcher):
        assert_that(matcher.describe_mismatch("a")).is_equal_to("was <'a'> of type <str>, not an integer")


class TestTemporalMatcherBoundaries:
    """`is_after` and `is_before` are strict, `is_now` is inclusive.  Only a value sitting exactly on
    the boundary tells a strict comparison from a loose one."""

    _MOMENT = datetime(2020, 1, 1, tzinfo=timezone.utc)

    def test_is_after_rejects_the_boundary_itself(self):
        assert_that(match.is_after(self._MOMENT).matches(self._MOMENT)).is_false()
        assert_that(match.is_after(self._MOMENT).matches(self._MOMENT + timedelta(microseconds=1))).is_true()

    def test_is_before_rejects_the_boundary_itself(self):
        assert_that(match.is_before(self._MOMENT).matches(self._MOMENT)).is_false()
        assert_that(match.is_before(self._MOMENT).matches(self._MOMENT - timedelta(microseconds=1))).is_true()

    def test_is_now_accepts_a_value_exactly_delta_away(self):
        delta = timedelta(seconds=30)
        assert_that(match.is_now(delta).matches(datetime.now(timezone.utc) - delta + timedelta(seconds=1))).is_true()


class TestMatcherComposition:
    def test_combining_two_all_of_matchers_flattens_them(self):
        composed = (match.is_positive() & match.is_even()) & (match.greater_than(1) & match.less_than(9))
        assert_that(composed.matchers).is_length(4)
        assert_that(composed.matches(4)).is_true()
        assert_that(composed.matches(10)).is_false()

    def test_combining_two_any_of_matchers_flattens_them(self):
        composed = (match.is_even() | match.greater_than(100)) | (match.less_than(-100) | match.is_odd())
        assert_that(composed.matchers).is_length(4)
        assert_that(composed.matches(3)).is_true()

    def test_equal_to_is_not_strict_about_types_by_default(self):
        # the flag defaults to off, so a bool still matches the int it equals
        assert_that(match.equal_to(1).matches(True)).is_true()
        assert_that(match.equal_to(1, strict_types=True).matches(True)).is_false()

    def test_a_regex_matcher_keeps_the_pattern_it_was_given(self):
        matcher = match.matches_regex(r"^a\d+$")
        assert_that(matcher.pattern).is_equal_to(r"^a\d+$")
        assert_that(matcher.describe()).contains(r"^a\d+$")


class TestTypeMatchersRefuseBadInputAtConstruction:
    """`MatchesRegexMatcher` compiles eagerly so an invalid pattern raises at the call site rather
    than inside `matches()`, because a matcher must not raise on use.  These two broke that contract:
    `list[int]` was accepted and blew up inside `matches()`, and a tuple of classes matched fine and
    then blew up inside `describe()` - only while a failure was being rendered.
    """

    @pytest.mark.parametrize("bad", [list[int], None, "int", 42])
    def test_is_instance_of_refuses_what_isinstance_refuses(self, bad):
        with pytest.raises(TypeError, match="given class arg must be a class"):
            match.is_instance_of(bad)

    @pytest.mark.parametrize("bad", [list[int], None, "int", int | str, (int, str)])
    def test_is_type_of_refuses_anything_but_a_type(self, bad):
        # `type(value) is <a union>` can never hold, so accepting one yields a matcher that silently
        # never matches
        with pytest.raises(TypeError, match="given type arg must be a type"):
            match.is_type_of(bad)

    @pytest.mark.parametrize("good", [int, int | str, (int, str), (int | str, float)])
    def test_is_instance_of_accepts_everything_isinstance_accepts(self, good):
        matcher = match.is_instance_of(good)
        assert_that(matcher.matches(1)).is_true()
        assert_that(matcher.describe()).starts_with("an instance of")

    def test_the_error_matches_the_builder_assertion_word_for_word(self):
        # one vocabulary for the same mistake, whichever surface the caller reached it through
        with pytest.raises(TypeError) as from_matcher:
            match.is_instance_of(None)
        with pytest.raises(TypeError) as from_builder:
            assert_that(1).is_instance_of(None)
        assert_that(str(from_matcher.value)).is_equal_to(str(from_builder.value))


class TestTypeMatcherDescriptionsSurviveEveryShape:
    """`__name__` is absent on a union below 3.14 and on a tuple everywhere, and the description is
    built on the failure path, so reading it directly turned a failure into an `AttributeError`."""

    def test_a_class_is_named(self):
        assert_that(match.is_instance_of(int).describe()).is_equal_to("an instance of <int>")

    def test_a_union_is_spelled_out(self):
        # `str()` gives `int | str` on every supported version; `__name__` gives `Union` on 3.14+ and
        # raises below it
        assert_that(match.is_instance_of(int | str).describe()).is_equal_to("an instance of <int | str>")

    def test_a_tuple_names_its_members(self):
        assert_that(match.is_instance_of((int, str)).describe()).is_equal_to("an instance of <int, str>")

    def test_a_tuple_containing_a_union_names_both(self):
        described = match.is_instance_of((int | str, float)).describe()
        assert_that(described).is_equal_to("an instance of <int | str, float>")

    def test_is_type_of_names_its_class(self):
        assert_that(match.is_type_of(int).describe()).is_equal_to("exactly type <int>")

    def test_a_union_reaches_the_rendered_failure(self):
        # the whole point: the description is built while a mismatch is being rendered
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"v": 1.5}).matches_structure({"v": match.is_instance_of(int | str)})
        assert_that(str(exc_info.value)).contains("int | str")
