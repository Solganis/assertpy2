from assertpy2 import assert_that, fail, soft_assertions, soft_fail


def test_soft_fail_without_context():
    try:
        soft_fail()
        fail("should have raised error")
    except AssertionError as e:
        out = str(e)
        assert_that(out).is_equal_to("Fail!")
        assert_that(out).does_not_contain("should have raised error")


def test_soft_fail_with_msg_without_context():
    try:
        soft_fail("some msg")
        fail("should have raised error")
    except AssertionError as e:
        out = str(e)
        assert_that(out).is_equal_to("Fail: some msg!")
        assert_that(out).does_not_contain("should have raised error")


def test_soft_fail():
    try:
        with soft_assertions():
            soft_fail()
        fail("should have raised error")
    except AssertionError as e:
        out = str(e)
        assert_that(out).contains("Fail!")
        assert_that(out).does_not_contain("should have raised error")


def test_soft_fail_with_msg():
    try:
        with soft_assertions():
            soft_fail("foobar")
        fail("should have raised error")
    except AssertionError as e:
        out = str(e)
        assert_that(out).contains("Fail: foobar!")
        assert_that(out).does_not_contain("should have raised error")


def test_soft_fail_with_soft_failing_asserts():
    try:
        with soft_assertions():
            assert_that("foo").is_length(4)
            assert_that("foo").is_empty()
            soft_fail("foobar")
            assert_that("foo").is_not_equal_to("foo")
            assert_that("foo").is_equal_to_ignoring_case("BAR")
        fail("should have raised error")
    except AssertionError as e:
        out = str(e)
        assert_that(out).contains("Expected <foo> to be of length <4>, but was <3>.")
        assert_that(out).contains("Expected <foo> to be empty string, but was not.")
        assert_that(out).contains("Fail: foobar!")
        assert_that(out).contains("Expected <foo> to be not equal to <foo>, but was.")
        assert_that(out).contains("Expected <foo> to be case-insensitive equal to <BAR>, but was not.")
        assert_that(out).does_not_contain("should have raised error")


def test_double_soft_fail():
    try:
        with soft_assertions():
            soft_fail()
            soft_fail("foobar")
        fail("should have raised error")
    except AssertionError as e:
        out = str(e)
        assert_that(out).contains("Fail!")
        assert_that(out).contains("Fail: foobar!")
        assert_that(out).does_not_contain("should have raised error")
