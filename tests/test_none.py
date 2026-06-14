from assertpy2 import assert_that, fail


def test_is_none():
    assert_that(None).is_none()


def test_is_none_failure():
    try:
        assert_that("foo").is_none()
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected <foo> to be <None>, but was not.")


def test_is_not_none():
    assert_that("foo").is_not_none()
    assert_that(123).is_not_none()
    assert_that(False).is_not_none()
    assert_that([]).is_not_none()
    assert_that({}).is_not_none()


def test_is_not_none_failure():
    try:
        assert_that(None).is_not_none()
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected not <None>, but was.")
