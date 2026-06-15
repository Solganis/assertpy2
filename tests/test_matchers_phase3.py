from assertpy2 import assert_that, match


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
