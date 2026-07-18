import datetime

import pytest

from assertpy2 import assert_that

reference_time = datetime.datetime.today()


def test_is_before():
    other_time = datetime.datetime.today()
    assert_that(reference_time).is_before(other_time)


def test_is_before_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.datetime.today()
        assert_that(other_time).is_before(reference_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be before "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not."
    )


def test_is_before_bad_val_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_before(123)
    assert_that(str(exc_info.value)).is_equal_to("val must be datetime, but was type <int>")


def test_is_before_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_before(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be datetime, but was type <int>")


def test_is_after():
    other_time = datetime.datetime.today()
    assert_that(other_time).is_after(reference_time)


def test_is_after_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.datetime.today()
        assert_that(reference_time).is_after(other_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be after "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not."
    )


def test_is_after_bad_val_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_after(123)
    assert_that(str(exc_info.value)).is_equal_to("val must be datetime, but was type <int>")


def test_is_after_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_after(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be datetime, but was type <int>")


def test_is_equal_to_ignoring_milliseconds():
    assert_that(reference_time).is_equal_to_ignoring_milliseconds(reference_time)


def test_is_equal_to_ignoring_milliseconds_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.datetime.today() + datetime.timedelta(days=1)
        assert_that(reference_time).is_equal_to_ignoring_milliseconds(other_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be equal to "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not."
    )


def test_is_equal_to_ignoring_milliseconds_bad_val_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_equal_to_ignoring_milliseconds(123)
    assert_that(str(exc_info.value)).is_equal_to("val must be datetime, but was type <int>")


def test_is_equal_to_ignoring_milliseconds_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_equal_to_ignoring_milliseconds(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be datetime, but was type <int>")


def test_is_equal_to_ignoring_seconds():
    assert_that(reference_time).is_equal_to_ignoring_seconds(reference_time)


def test_is_equal_to_ignoring_seconds_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.datetime.today() + datetime.timedelta(days=1)
        assert_that(reference_time).is_equal_to_ignoring_seconds(other_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}> to be equal to <\d{4}-\d{2}-\d{2} \d{2}:\d{2}>, but was not."
    )


def test_is_equal_to_ignoring_seconds_bad_val_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_equal_to_ignoring_seconds(123)
    assert_that(str(exc_info.value)).is_equal_to("val must be datetime, but was type <int>")


def test_is_equal_to_ignoring_seconds_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_equal_to_ignoring_seconds(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be datetime, but was type <int>")


def test_is_equal_to_ignoring_time():
    assert_that(reference_time).is_equal_to_ignoring_time(reference_time)


def test_is_equal_to_ignoring_time_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.datetime.today() + datetime.timedelta(days=1)
        assert_that(reference_time).is_equal_to_ignoring_time(other_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2}> to be equal to <\d{4}-\d{2}-\d{2}>, but was not."
    )


def test_is_equal_to_ignoring_time_bad_val_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_equal_to_ignoring_time(123)
    assert_that(str(exc_info.value)).is_equal_to("val must be datetime, but was type <int>")


def test_is_equal_to_ignoring_time_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_equal_to_ignoring_time(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be datetime, but was type <int>")


def test_is_greater_than():
    other_time = datetime.datetime.today()
    assert_that(other_time).is_greater_than(reference_time)


def test_is_greater_than_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.datetime.today()
        assert_that(reference_time).is_greater_than(other_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be greater than "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not."
    )


def test_is_greater_than_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_greater_than(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be <datetime>, but was <int>")


def test_is_greater_than_or_equal_to():
    assert_that(reference_time).is_greater_than_or_equal_to(reference_time)


def test_is_greater_than_or_equal_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.datetime.today()
        assert_that(reference_time).is_greater_than_or_equal_to(other_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be greater than or equal to "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not."
    )


def test_is_greater_than_or_equal_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_greater_than_or_equal_to(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be <datetime>, but was <int>")


def test_is_less_than():
    other_time = datetime.datetime.today()
    assert_that(reference_time).is_less_than(other_time)


def test_is_less_than_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.datetime.today()
        assert_that(other_time).is_less_than(reference_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be less than "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not."
    )


def test_is_less_than_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_less_than(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be <datetime>, but was <int>")


def test_is_less_than_or_equal_to():
    assert_that(reference_time).is_less_than_or_equal_to(reference_time)


def test_is_less_than_or_equal_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.datetime.today()
        assert_that(other_time).is_less_than_or_equal_to(reference_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be less than or equal to "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not."
    )


def test_is_less_than_or_equal_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_less_than_or_equal_to(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be <datetime>, but was <int>")


def test_is_between():
    other_time = datetime.datetime.today()
    third_time = datetime.datetime.today()
    assert_that(other_time).is_between(reference_time, third_time)


def test_is_between_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.datetime.today()
        third_time = datetime.datetime.today()
        assert_that(reference_time).is_between(other_time, third_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be between "
        + r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> and <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not."
    )


def test_is_between_bad_arg1_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_between(123, 456)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be <datetime>, but was <int>")


def test_is_between_bad_arg2_type_failure():
    with pytest.raises(TypeError) as exc_info:
        other_time = datetime.datetime.today()
        assert_that(reference_time).is_between(other_time, 123)
    assert_that(str(exc_info.value)).is_equal_to("given high arg must be <datetime>, but was <int>")


def test_is_not_between():
    other_time = reference_time + datetime.timedelta(minutes=5)
    third_time = reference_time + datetime.timedelta(minutes=10)
    assert_that(reference_time).is_not_between(other_time, third_time)


def test_is_not_between_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(minutes=5)
        third_time = reference_time + datetime.timedelta(minutes=10)
        assert_that(other_time).is_not_between(reference_time, third_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to not be between "
        + r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> and <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was."
    )


def test_is_not_between_bad_arg1_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_not_between(123, 456)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be <datetime>, but was <int>")


def test_is_not_between_bad_arg2_type_failure():
    with pytest.raises(TypeError) as exc_info:
        other_time = datetime.datetime.today()
        assert_that(reference_time).is_not_between(other_time, 123)
    assert_that(str(exc_info.value)).is_equal_to("given high arg must be <datetime>, but was <int>")


def test_is_close_to():
    other_time = datetime.datetime.today()
    assert_that(reference_time).is_close_to(other_time, datetime.timedelta(minutes=5))


def test_is_close_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(minutes=5)
        assert_that(reference_time).is_close_to(other_time, datetime.timedelta(minutes=1))
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be close to "
        + r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> within tolerance <\d+:\d+:\d+>, but was not."
    )


def test_is_close_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_close_to(123, 456)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be datetime, but was <int>")


def test_is_close_to_bad_tolerance_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        other_time = datetime.datetime.today()
        assert_that(reference_time).is_close_to(other_time, 123)
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must be timedelta, but was <int>")


def test_is_not_close_to():
    other_time = reference_time + datetime.timedelta(minutes=5)
    assert_that(reference_time).is_not_close_to(other_time, datetime.timedelta(minutes=4))


def test_is_not_close_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.datetime.today()
        assert_that(reference_time).is_not_close_to(other_time, datetime.timedelta(minutes=5))
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to not be close to "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> within tolerance <\d+:\d+:\d+>, but was."
    )


def test_is_not_close_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_not_close_to(123, 456)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be datetime, but was <int>")


def test_is_not_close_to_bad_tolerance_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        other_time = datetime.datetime.today()
        assert_that(reference_time).is_not_close_to(other_time, 123)
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must be timedelta, but was <int>")


reference_delta = datetime.timedelta(seconds=60)


def test_is_greater_than_timedelta():
    other_time = datetime.timedelta(seconds=120)
    assert_that(other_time).is_greater_than(reference_delta)


def test_is_greater_than_timedelta_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_delta = datetime.timedelta(seconds=90)
        assert_that(reference_delta).is_greater_than(other_delta)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{1,2}:\d{2}:\d{2}> to be greater than <\d{1,2}:\d{2}:\d{2}>, but was not."
    )


def test_is_greater_than_timedelta_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_delta).is_greater_than(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be <timedelta>, but was <int>")


def test_is_greater_than_or_equal_to_timedelta():
    assert_that(reference_delta).is_greater_than_or_equal_to(reference_delta)


def test_is_greater_than_or_equal_to_timedelta_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_delta = datetime.timedelta(seconds=90)
        assert_that(reference_delta).is_greater_than_or_equal_to(other_delta)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{1,2}:\d{2}:\d{2}> to be greater than or equal to <\d{1,2}:\d{2}:\d{2}>, but was not."
    )


def test_is_greater_than_or_equal_to_timedelta_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_delta).is_greater_than_or_equal_to(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be <timedelta>, but was <int>")


def test_is_less_than_timedelta():
    other_delta = datetime.timedelta(seconds=90)
    assert_that(reference_delta).is_less_than(other_delta)


def test_is_less_than_timedelta_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_delta = datetime.timedelta(seconds=90)
        assert_that(other_delta).is_less_than(reference_delta)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{1,2}:\d{2}:\d{2}> to be less than <\d{1,2}:\d{2}:\d{2}>, but was not."
    )


def test_is_less_than_timedelta_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_delta).is_less_than(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be <timedelta>, but was <int>")


def test_is_less_than_or_equal_to_timedelta():
    assert_that(reference_delta).is_less_than_or_equal_to(reference_delta)


def test_is_less_than_or_equal_to_timedelta_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_delta = datetime.timedelta(seconds=90)
        assert_that(other_delta).is_less_than_or_equal_to(reference_delta)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{1,2}:\d{2}:\d{2}> to be less than or equal to <\d{1,2}:\d{2}:\d{2}>, but was not."
    )


def test_is_less_than_or_equal_to_timedelta_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_delta).is_less_than_or_equal_to(123)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be <timedelta>, but was <int>")


def test_is_between_timedelta():
    other_time = datetime.timedelta(seconds=90)
    third_time = datetime.timedelta(seconds=120)
    assert_that(other_time).is_between(reference_delta, third_time)


def test_is_between_timedelta_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.timedelta(seconds=30)
        third_time = datetime.timedelta(seconds=40)
        assert_that(reference_delta).is_between(other_time, third_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{1,2}:\d{2}:\d{2}> to be between <\d{1,2}:\d{2}:\d{2}> and <\d{1,2}:\d{2}:\d{2}>, but was not."
    )


def test_is_not_between_timedelta():
    other_time = datetime.timedelta(seconds=90)
    third_time = datetime.timedelta(seconds=120)
    assert_that(reference_delta).is_not_between(other_time, third_time)


def test_is_not_between_timedelta_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.timedelta(seconds=90)
        third_time = datetime.timedelta(seconds=120)
        assert_that(other_time).is_not_between(reference_delta, third_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{1,2}:\d{2}:\d{2}> to not be between <\d{1,2}:\d{2}:\d{2}> and <\d{1,2}:\d{2}:\d{2}>, but was."
    )


class _DatetimeSubclass(datetime.datetime):
    pass


def test_datetime_subclass_is_accepted():
    earlier = _DatetimeSubclass(2026, 1, 1, 12, 0, 0)
    later = _DatetimeSubclass(2026, 1, 2, 12, 0, 0)
    assert_that(earlier).is_before(later)
    assert_that(later).is_after(earlier)
    assert_that(earlier).is_close_to(later, datetime.timedelta(days=2))


def test_datetime_subclass_still_fails_real_mismatch():
    earlier = _DatetimeSubclass(2026, 1, 1, 12, 0, 0)
    later = _DatetimeSubclass(2026, 1, 2, 12, 0, 0)
    with pytest.raises(AssertionError):
        assert_that(later).is_before(earlier)


def test_is_close_to_tolerance_format():
    base = datetime.datetime(2026, 1, 1, 0, 0, 0)
    other = datetime.datetime(2026, 1, 3, 0, 0, 0)
    tolerance = datetime.timedelta(days=1, hours=2, minutes=3, seconds=4, microseconds=500000)
    with pytest.raises(AssertionError) as exc_info:
        assert_that(base).is_close_to(other, tolerance)
    assert_that(str(exc_info.value)).contains("within tolerance <26:03:04>")


def test_is_before_after_reject_equal():
    moment = datetime.datetime(2026, 1, 1, 12, 0, 0)
    same = datetime.datetime(2026, 1, 1, 12, 0, 0)
    with pytest.raises(AssertionError):
        assert_that(moment).is_before(same)
    with pytest.raises(AssertionError):
        assert_that(moment).is_after(same)


def test_is_equal_to_ignoring_milliseconds_each_component_mismatch():
    base = datetime.datetime(2020, 1, 2, 3, 4, 5, 123)
    for other in (
        datetime.datetime(2020, 1, 3, 3, 4, 5),  # date differs
        datetime.datetime(2020, 1, 2, 9, 4, 5),  # hour differs
        datetime.datetime(2020, 1, 2, 3, 9, 5),  # minute differs
        datetime.datetime(2020, 1, 2, 3, 4, 9),  # second differs
    ):
        with pytest.raises(AssertionError):
            assert_that(base).is_equal_to_ignoring_milliseconds(other)


def test_is_equal_to_ignoring_seconds_each_component_mismatch():
    base = datetime.datetime(2020, 1, 2, 3, 4, 5)
    for other in (
        datetime.datetime(2020, 1, 3, 3, 4, 5),  # date differs
        datetime.datetime(2020, 1, 2, 9, 4, 5),  # hour differs
        datetime.datetime(2020, 1, 2, 3, 9, 5),  # minute differs
    ):
        with pytest.raises(AssertionError):
            assert_that(base).is_equal_to_ignoring_seconds(other)


class TestIsBeforeOrEqualTo:
    def test_before(self):
        reference_time = datetime.datetime(2020, 1, 1)
        other_time = datetime.datetime(2020, 1, 2)
        assert_that(reference_time).is_before_or_equal_to(other_time)

    def test_equal(self):
        reference_time = datetime.datetime(2020, 1, 1, 12, 0, 0)
        assert_that(reference_time).is_before_or_equal_to(reference_time)

    def test_failure(self):
        reference_time = datetime.datetime(2020, 1, 2)
        other_time = datetime.datetime(2020, 1, 1)
        with pytest.raises(AssertionError) as exc_info:
            assert_that(reference_time).is_before_or_equal_to(other_time)
        assert_that(str(exc_info.value)).contains("to be before or equal to")

    def test_bad_val_type(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that("foo").is_before_or_equal_to(datetime.datetime.now())
        assert_that(str(exc_info.value)).contains("val must be datetime")

    def test_bad_arg_type(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(datetime.datetime.now()).is_before_or_equal_to("foo")
        assert_that(str(exc_info.value)).contains("given arg must be datetime")

    def test_date_not_datetime_val(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(datetime.date(2020, 1, 1)).is_before_or_equal_to(datetime.datetime.now())
        assert_that(str(exc_info.value)).contains("val must be datetime")

    def test_date_not_datetime_arg(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(datetime.datetime.now()).is_before_or_equal_to(datetime.date(2020, 1, 1))
        assert_that(str(exc_info.value)).contains("given arg must be datetime")


class TestIsAfterOrEqualTo:
    def test_after(self):
        reference_time = datetime.datetime(2020, 1, 2)
        other_time = datetime.datetime(2020, 1, 1)
        assert_that(reference_time).is_after_or_equal_to(other_time)

    def test_equal(self):
        reference_time = datetime.datetime(2020, 1, 1, 12, 0, 0)
        assert_that(reference_time).is_after_or_equal_to(reference_time)

    def test_failure(self):
        reference_time = datetime.datetime(2020, 1, 1)
        other_time = datetime.datetime(2020, 1, 2)
        with pytest.raises(AssertionError) as exc_info:
            assert_that(reference_time).is_after_or_equal_to(other_time)
        assert_that(str(exc_info.value)).contains("to be after or equal to")

    def test_bad_val_type(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that("foo").is_after_or_equal_to(datetime.datetime.now())
        assert_that(str(exc_info.value)).contains("val must be datetime")

    def test_bad_arg_type(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(datetime.datetime.now()).is_after_or_equal_to("foo")
        assert_that(str(exc_info.value)).contains("given arg must be datetime")

    def test_date_not_datetime_val(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(datetime.date(2020, 1, 1)).is_after_or_equal_to(datetime.datetime.now())
        assert_that(str(exc_info.value)).contains("val must be datetime")


def test_naive_vs_aware_comparison_raises_clear_type_error():
    # mixing a tz-naive and a tz-aware datetime is a programming error; all four relational methods must
    # raise a clear, actionable TypeError instead of Python's raw "can't compare offset-naive..." one
    naive = datetime.datetime(2020, 1, 1, 12)
    aware = datetime.datetime(2020, 1, 1, 12, tzinfo=datetime.timezone.utc)
    for call in (
        lambda: assert_that(naive).is_before(aware),
        lambda: assert_that(naive).is_after(aware),
        lambda: assert_that(naive).is_before_or_equal_to(aware),
        lambda: assert_that(naive).is_after_or_equal_to(aware),
    ):
        with pytest.raises(TypeError, match="timezone-naive datetime with a timezone-aware"):
            call()
