import datetime

from assertpy2 import assert_that, fail, match, soft_assertions


class TestIsCallable:
    def test_callable_lambda(self):
        assert_that(lambda: None).is_callable()

    def test_callable_function(self):
        assert_that(print).is_callable()

    def test_callable_class(self):
        assert_that(int).is_callable()

    def test_callable_method(self):
        assert_that("foo".upper).is_callable()

    def test_callable_failure(self):
        try:
            assert_that(42).is_callable()
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to("Expected <42> to be callable, but was not.")

    def test_callable_string_failure(self):
        try:
            assert_that("foo").is_callable()
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to("Expected <foo> to be callable, but was not.")


class TestIsNotCallable:
    def test_not_callable_int(self):
        assert_that(42).is_not_callable()

    def test_not_callable_string(self):
        assert_that("foo").is_not_callable()

    def test_not_callable_none(self):
        assert_that(None).is_not_callable()

    def test_not_callable_failure(self):
        try:
            assert_that(print).is_not_callable()
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("to not be callable, but was.")

    def test_not_callable_lambda_failure(self):
        try:
            assert_that(lambda: None).is_not_callable()
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("to not be callable, but was.")


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
        try:
            assert_that([1, 2, 3]).any_satisfy(match.is_negative())
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("Expected any item to satisfy")

    def test_any_satisfy_callable_failure(self):
        try:
            assert_that([1, 2, 3]).any_satisfy(lambda x: x > 10)
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("Expected any item to satisfy")

    def test_any_satisfy_not_iterable_failure(self):
        try:
            assert_that(42).any_satisfy(match.is_positive())
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to("val is not iterable")

    def test_any_satisfy_bad_matcher_failure(self):
        try:
            assert_that([1, 2]).any_satisfy("not a matcher")
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to("given arg must be a Matcher or callable")

    def test_any_satisfy_empty_iterable_failure(self):
        try:
            assert_that([]).any_satisfy(match.is_positive())
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("Expected any item to satisfy")


class TestAllSatisfy:
    def test_all_satisfy_matcher(self):
        assert_that([1, 2, 3]).all_satisfy(match.is_positive())

    def test_all_satisfy_callable(self):
        assert_that([2, 4, 6]).all_satisfy(lambda x: x % 2 == 0)

    def test_all_satisfy_failure(self):
        try:
            assert_that([1, -2, 3]).all_satisfy(match.is_positive())
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("Expected all items to satisfy")
            assert_that(str(ex)).contains("index 1")

    def test_all_satisfy_empty_iterable(self):
        assert_that([]).all_satisfy(match.is_positive())


class TestNoneSatisfy:
    def test_none_satisfy_matcher(self):
        assert_that([1, 2, 3]).none_satisfy(match.is_negative())

    def test_none_satisfy_callable(self):
        assert_that([1, 2, 3]).none_satisfy(lambda x: x < 0)

    def test_none_satisfy_matcher_failure(self):
        try:
            assert_that([1, -2, 3]).none_satisfy(match.is_negative())
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("Expected no item to satisfy")
            assert_that(str(ex)).contains("index 1")
            assert_that(str(ex)).contains("-2")

    def test_none_satisfy_callable_failure(self):
        try:
            assert_that([1, 2, 3]).none_satisfy(lambda x: x == 2)
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("Expected no item to satisfy")
            assert_that(str(ex)).contains("index 1")

    def test_none_satisfy_not_iterable_failure(self):
        try:
            assert_that(42).none_satisfy(match.is_positive())
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to("val is not iterable")

    def test_none_satisfy_bad_matcher_failure(self):
        try:
            assert_that([1]).none_satisfy("not a matcher")
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to("given arg must be a Matcher or callable")

    def test_none_satisfy_empty_iterable(self):
        assert_that([]).none_satisfy(match.is_positive())


class TestContainsExactly:
    def test_list(self):
        assert_that([1, 2, 3]).contains_exactly(1, 2, 3)

    def test_tuple(self):
        assert_that((1, 2, 3)).contains_exactly(1, 2, 3)

    def test_string_chars(self):
        assert_that("abc").contains_exactly("a", "b", "c")

    def test_wrong_order_failure(self):
        try:
            assert_that([1, 2, 3]).contains_exactly(1, 3, 2)
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("to contain exactly")

    def test_missing_items_failure(self):
        try:
            assert_that([1, 2, 3]).contains_exactly(1, 2)
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("to contain exactly")

    def test_extra_items_failure(self):
        try:
            assert_that([1, 2]).contains_exactly(1, 2, 3)
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("to contain exactly")

    def test_empty_args_failure(self):
        try:
            assert_that([1]).contains_exactly()
            fail("should have raised error")
        except ValueError as ex:
            assert_that(str(ex)).is_equal_to("one or more args must be given")

    def test_not_iterable_failure(self):
        try:
            assert_that(42).contains_exactly(1)
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to("val is not iterable")


class TestContainsInOrder:
    def test_all_present(self):
        assert_that([1, 5, 2, 8, 3]).contains_in_order(1, 2, 3)

    def test_contiguous(self):
        assert_that([1, 2, 3]).contains_in_order(1, 2, 3)

    def test_strings(self):
        assert_that(["a", "x", "b", "y", "c"]).contains_in_order("a", "b", "c")

    def test_single_item(self):
        assert_that([1, 2, 3]).contains_in_order(2)

    def test_wrong_order_failure(self):
        try:
            assert_that([1, 2, 3]).contains_in_order(3, 1)
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("in order, but did not")

    def test_missing_item_failure(self):
        try:
            assert_that([1, 2, 3]).contains_in_order(1, 4)
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("in order, but did not")

    def test_empty_args_failure(self):
        try:
            assert_that([1]).contains_in_order()
            fail("should have raised error")
        except ValueError as ex:
            assert_that(str(ex)).is_equal_to("one or more args must be given")

    def test_not_iterable_failure(self):
        try:
            assert_that(42).contains_in_order(1)
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to("val is not iterable")


class TestDoesNotRaise:
    def test_no_exception(self):
        def safe_func(x):
            return x + 1

        assert_that(safe_func).does_not_raise(ValueError).when_called_with(1)

    def test_different_exception(self):
        def raises_type_error():
            raise TypeError("oops")

        assert_that(raises_type_error).does_not_raise(ValueError).when_called_with()

    def test_raises_expected_failure(self):
        def raises_value_error():
            raise ValueError("bad value")

        try:
            assert_that(raises_value_error).does_not_raise(ValueError).when_called_with()
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("to not raise <ValueError>")
            assert_that(str(ex)).contains("but did raise")

    def test_raises_subclass_failure(self):
        def raises_file_not_found():
            raise FileNotFoundError("missing")

        try:
            assert_that(raises_file_not_found).does_not_raise(OSError).when_called_with()
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("to not raise <OSError>")

    def test_not_callable_failure(self):
        try:
            assert_that(42).does_not_raise(ValueError)
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to("val must be callable")

    def test_not_exception_failure(self):
        try:
            assert_that(lambda: None).does_not_raise(str)
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to("given arg must be exception")

    def test_raises_expected_soft_mode(self):
        def raises_value_error():
            raise ValueError("bad value")

        try:
            with soft_assertions():
                assert_that(raises_value_error).does_not_raise(ValueError).when_called_with()
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("to not raise <ValueError>")


class TestIsBeforeOrEqualTo:
    def test_before(self):
        d1 = datetime.datetime(2020, 1, 1)
        d2 = datetime.datetime(2020, 1, 2)
        assert_that(d1).is_before_or_equal_to(d2)

    def test_equal(self):
        d1 = datetime.datetime(2020, 1, 1, 12, 0, 0)
        assert_that(d1).is_before_or_equal_to(d1)

    def test_failure(self):
        d1 = datetime.datetime(2020, 1, 2)
        d2 = datetime.datetime(2020, 1, 1)
        try:
            assert_that(d1).is_before_or_equal_to(d2)
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("to be before or equal to")

    def test_bad_val_type(self):
        try:
            assert_that("foo").is_before_or_equal_to(datetime.datetime.now())
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).contains("val must be datetime")

    def test_bad_arg_type(self):
        try:
            assert_that(datetime.datetime.now()).is_before_or_equal_to("foo")
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).contains("given arg must be datetime")

    def test_date_not_datetime_val(self):
        try:
            assert_that(datetime.date(2020, 1, 1)).is_before_or_equal_to(datetime.datetime.now())
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).contains("val must be datetime")

    def test_date_not_datetime_arg(self):
        try:
            assert_that(datetime.datetime.now()).is_before_or_equal_to(datetime.date(2020, 1, 1))
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).contains("given arg must be datetime")


class TestIsAfterOrEqualTo:
    def test_after(self):
        d1 = datetime.datetime(2020, 1, 2)
        d2 = datetime.datetime(2020, 1, 1)
        assert_that(d1).is_after_or_equal_to(d2)

    def test_equal(self):
        d1 = datetime.datetime(2020, 1, 1, 12, 0, 0)
        assert_that(d1).is_after_or_equal_to(d1)

    def test_failure(self):
        d1 = datetime.datetime(2020, 1, 1)
        d2 = datetime.datetime(2020, 1, 2)
        try:
            assert_that(d1).is_after_or_equal_to(d2)
            fail("should have raised error")
        except AssertionError as ex:
            assert_that(str(ex)).contains("to be after or equal to")

    def test_bad_val_type(self):
        try:
            assert_that("foo").is_after_or_equal_to(datetime.datetime.now())
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).contains("val must be datetime")

    def test_bad_arg_type(self):
        try:
            assert_that(datetime.datetime.now()).is_after_or_equal_to("foo")
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).contains("given arg must be datetime")

    def test_date_not_datetime_val(self):
        try:
            assert_that(datetime.date(2020, 1, 1)).is_after_or_equal_to(datetime.datetime.now())
            fail("should have raised error")
        except TypeError as ex:
            assert_that(str(ex)).contains("val must be datetime")


class TestChaining:
    def test_callable_chain(self):
        assert_that(print).is_callable().is_not_none()

    def test_satisfy_chain(self):
        assert_that([1, 2, 3]).any_satisfy(lambda x: x > 2).none_satisfy(lambda x: x < 0)

    def test_contains_exactly_chain(self):
        assert_that([1, 2, 3]).contains_exactly(1, 2, 3).is_length(3)

    def test_contains_in_order_chain(self):
        assert_that([1, 2, 3]).contains_in_order(1, 3).is_not_empty()

    def test_datetime_chain(self):
        d1 = datetime.datetime(2020, 1, 1)
        d2 = datetime.datetime(2020, 12, 31)
        assert_that(d1).is_before_or_equal_to(d2).is_after_or_equal_to(d1)
