import sys
import traceback

from assertpy2 import AssertionFailure, assert_that, fail


def test_traceback():
    try:
        assert_that("foo").is_equal_to("bar")
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected <foo> to be equal to <bar>, but was not.")
        assert_that(ex).is_instance_of(AssertionError)
        assert_that(ex).is_instance_of(AssertionFailure)

        # extract all stack frames from the traceback
        _, _, tb = sys.exc_info()
        assert_that(tb).is_not_none()

        # walk_tb added in 3.5
        if sys.version_info[0] == 3 and sys.version_info[1] >= 5:
            frames = [(f.f_code.co_filename, f.f_code.co_name, lineno) for f, lineno in traceback.walk_tb(tb)]

            assert_that(frames).is_length(3)

            assert_that(frames[0][0]).ends_with("test_traceback.py")
            assert_that(frames[0][1]).is_equal_to("test_traceback")
            assert_that(frames[0][2]).is_equal_to(9)

            assert_that(frames[1][0]).ends_with("base.py")
            assert_that(frames[1][1]).is_equal_to("is_equal_to")
            assert_that(frames[1][2]).is_greater_than(40)

            assert_that(frames[2][0]).ends_with("assertpy.py")
            assert_that(frames[2][1]).is_equal_to("error")
            assert_that(frames[2][2]).is_greater_than(100)
