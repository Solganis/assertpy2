import pytest

from assertpy2 import assert_that, match


class TestAnySatisfy:
    def test_any_satisfy_matcher(self):
        assert_that([1, -2, 3]).any_satisfy(match.is_negative())

    def test_any_satisfy_callable(self):
        assert_that([1, 2, 3]).any_satisfy(lambda x: x > 2)

    def test_any_satisfy_first_item(self):
        assert_that([10, 1, 2]).any_satisfy(match.greater_than(5))

    def test_any_satisfy_last_item(self):
        assert_that([1, 2, 10]).any_satisfy(match.greater_than(5))

    def test_any_satisfy_matcher_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).any_satisfy(match.is_negative())
        assert_that(str(exc_info.value)).contains("Expected any item to satisfy")

    def test_any_satisfy_callable_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).any_satisfy(lambda x: x > 10)
        assert_that(str(exc_info.value)).contains("Expected any item to satisfy")

    def test_any_satisfy_not_iterable_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).any_satisfy(match.is_positive())
        assert_that(str(exc_info.value)).is_equal_to("val is not iterable")

    def test_any_satisfy_bad_matcher_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that([1, 2]).any_satisfy("not a matcher")
        assert_that(str(exc_info.value)).is_equal_to("given arg must be a Matcher or callable")

    def test_any_satisfy_empty_iterable_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([]).any_satisfy(match.is_positive())
        assert_that(str(exc_info.value)).contains("Expected any item to satisfy")


class TestAllSatisfy:
    def test_all_satisfy_matcher(self):
        assert_that([1, 2, 3]).all_satisfy(match.is_positive())

    def test_all_satisfy_callable(self):
        assert_that([2, 4, 6]).all_satisfy(lambda x: x % 2 == 0)

    def test_all_satisfy_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, -2, 3]).all_satisfy(match.is_positive())
        assert_that(str(exc_info.value)).contains("Expected all items to satisfy")
        assert_that(str(exc_info.value)).contains("index 1")

    def test_all_satisfy_empty_iterable(self):
        assert_that([]).all_satisfy(match.is_positive())


class TestNoneSatisfy:
    def test_none_satisfy_matcher(self):
        assert_that([1, 2, 3]).none_satisfy(match.is_negative())

    def test_none_satisfy_callable(self):
        assert_that([1, 2, 3]).none_satisfy(lambda x: x < 0)

    def test_none_satisfy_matcher_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, -2, 3]).none_satisfy(match.is_negative())
        assert_that(str(exc_info.value)).contains("Expected no item to satisfy")
        assert_that(str(exc_info.value)).contains("index 1")
        assert_that(str(exc_info.value)).contains("-2")

    def test_none_satisfy_callable_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).none_satisfy(lambda x: x == 2)
        assert_that(str(exc_info.value)).contains("Expected no item to satisfy")
        assert_that(str(exc_info.value)).contains("index 1")

    def test_none_satisfy_not_iterable_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).none_satisfy(match.is_positive())
        assert_that(str(exc_info.value)).is_equal_to("val is not iterable")

    def test_none_satisfy_bad_matcher_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that([1]).none_satisfy("not a matcher")
        assert_that(str(exc_info.value)).is_equal_to("given arg must be a Matcher or callable")

    def test_none_satisfy_empty_iterable(self):
        assert_that([]).none_satisfy(match.is_positive())


class TestAnySatisfyShowsWhatItExamined:
    """The universal sibling lists every failure; "none did" left the reader to fetch the items."""

    def test_the_examined_items_reach_the_message(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2]).any_satisfy(match.greater_than(9))
        exc = exc_info.value
        assert_that(str(exc)).contains("none of the 2 did")
        assert_that([entry.path for entry in exc.diff.entries]).is_equal_to(["[0]", "[1]"])
        assert_that([entry.actual for entry in exc.diff.entries]).is_equal_to([1, 2])

    def test_a_callable_predicate_is_described_too(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2]).any_satisfy(lambda item: item > 9)
        assert_that(str(exc_info.value)).contains("a lambda predicate")

    def test_an_empty_subject_still_reports_cleanly(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([]).any_satisfy(lambda item: True)
        assert_that(str(exc_info.value)).contains("none of the 0 did")
