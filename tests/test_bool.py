from assertpy2 import assert_that, fail


def test_is_true():
    assert_that(True).is_true()
    assert_that(1 == 1).is_true()
    assert_that(1).is_true()
    assert_that("a").is_true()
    assert_that([1]).is_true()
    assert_that({"a": 1}).is_true()


def test_is_true_failure():
    try:
        assert_that(False).is_true()
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected <False> to be <True>, but was not.")


def test_is_false():
    assert_that(False).is_false()
    assert_that(1 == 2).is_false()
    assert_that(0).is_false()
    assert_that([]).is_false()
    assert_that({}).is_false()
    assert_that(()).is_false()


def test_is_false_failure():
    try:
        assert_that(True).is_false()
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected <True> to be <False>, but was not.")
