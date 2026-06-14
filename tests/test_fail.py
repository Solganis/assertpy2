from assertpy2 import assert_that, fail


def test_fail():
    try:
        fail()
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Fail!")


def test_fail_msg():
    try:
        fail("some msg")
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Fail: some msg!")
