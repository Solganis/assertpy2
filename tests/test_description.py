from assertpy2 import assert_that, fail


def test_constructor():
    try:
        assert_that(1, "extra msg").is_equal_to(2)
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("[extra msg] Expected <1> to be equal to <2>, but was not.")


def test_described_as():
    try:
        assert_that(1).described_as("extra msg").is_equal_to(2)
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("[extra msg] Expected <1> to be equal to <2>, but was not.")


def test_described_as_double():
    try:
        assert_that(1).described_as("extra msg").described_as("other msg").is_equal_to(2)
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("[other msg] Expected <1> to be equal to <2>, but was not.")


def test_described_as_chained():
    try:
        assert_that(1).described_as("extra msg").is_equal_to(1).described_as("other msg").is_equal_to(1).described_as(
            "last msg"
        ).is_equal_to(2)
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("[last msg] Expected <1> to be equal to <2>, but was not.")
