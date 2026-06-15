import logging
from io import StringIO

from assertpy2 import WarningLoggingAdapter, assert_that, assert_warn


def test_success():
    assert_warn("foo").is_length(3)
    assert_warn("foo").is_not_empty()
    assert_warn("foo").is_true()
    assert_warn("foo").is_alpha()
    assert_warn("123").is_digit()
    assert_warn("foo").is_lower()
    assert_warn("FOO").is_upper()
    assert_warn("foo").is_equal_to("foo")
    assert_warn("foo").is_not_equal_to("bar")
    assert_warn("foo").is_equal_to_ignoring_case("FOO")


def test_failures():
    # capture log
    capture = StringIO()
    logger = logging.getLogger("capture")
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn("foo", logger=adapted).is_length(4)
    assert_warn("foo", logger=adapted).is_empty()
    assert_warn("foo", logger=adapted).is_false()
    assert_warn("foo", logger=adapted).is_digit()
    assert_warn("123", logger=adapted).is_alpha()
    assert_warn("foo", logger=adapted).is_upper()
    assert_warn("FOO", logger=adapted).is_lower()
    assert_warn("foo", logger=adapted).is_equal_to("bar")
    assert_warn("foo", logger=adapted).is_not_equal_to("foo")
    assert_warn("foo", logger=adapted).is_equal_to_ignoring_case("BAR")

    # dump log to string
    out = capture.getvalue()
    capture.close()

    assert_that(out).contains("[test_warn.py:28]: Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).contains("[test_warn.py:29]: Expected <foo> to be empty string, but was not.")
    assert_that(out).contains("[test_warn.py:30]: Expected <foo> to be <False>, but was not.")
    assert_that(out).contains("[test_warn.py:31]: Expected <foo> to contain only digits, but did not.")
    assert_that(out).contains("[test_warn.py:32]: Expected <123> to contain only alphabetic chars, but did not.")
    assert_that(out).contains("[test_warn.py:33]: Expected <foo> to contain only uppercase chars, but did not.")
    assert_that(out).contains("[test_warn.py:34]: Expected <FOO> to contain only lowercase chars, but did not.")
    assert_that(out).contains("[test_warn.py:35]: Expected <foo> to be equal to <bar>, but was not.")
    assert_that(out).contains("[test_warn.py:36]: Expected <foo> to be not equal to <foo>, but was.")
    assert_that(out).contains("[test_warn.py:37]: Expected <foo> to be case-insensitive equal to <BAR>, but was not.")


def test_chained_failure():
    # capture log
    capture2 = StringIO()
    logger = logging.getLogger("capture2")
    handler = logging.StreamHandler(capture2)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn("foo", logger=adapted).is_length(4).is_in("bar").does_not_contain_duplicates()

    # dump log to string
    out = capture2.getvalue()
    capture2.close()

    assert_that(out).contains("[test_warn.py:63]: Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).contains("[test_warn.py:63]: Expected <foo> to be in <bar>, but was not.")
    assert_that(out).contains("[test_warn.py:63]: Expected <foo> to not contain duplicates, but did.")


def test_failures_with_renamed_import():
    from assertpy2 import assert_warn as warn  # inline: tests renamed import behavior

    # capture log
    capture3 = StringIO()
    logger = logging.getLogger("capture3")
    handler = logging.StreamHandler(capture3)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    warn("foo", logger=adapted).is_length(4)
    warn("foo", logger=adapted).is_empty()
    warn("foo", logger=adapted).is_false()
    warn("foo", logger=adapted).is_digit()
    warn("123", logger=adapted).is_alpha()
    warn("foo", logger=adapted).is_upper()
    warn("FOO", logger=adapted).is_lower()
    warn("foo", logger=adapted).is_equal_to("bar")
    warn("foo", logger=adapted).is_not_equal_to("foo")
    warn("foo", logger=adapted).is_equal_to_ignoring_case("BAR")

    # dump log to string
    out = capture3.getvalue()
    capture3.close()

    assert_that(out).contains("[test_warn.py:84]: Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).contains("[test_warn.py:85]: Expected <foo> to be empty string, but was not.")
    assert_that(out).contains("[test_warn.py:86]: Expected <foo> to be <False>, but was not.")
    assert_that(out).contains("[test_warn.py:87]: Expected <foo> to contain only digits, but did not.")
    assert_that(out).contains("[test_warn.py:88]: Expected <123> to contain only alphabetic chars, but did not.")
    assert_that(out).contains("[test_warn.py:89]: Expected <foo> to contain only uppercase chars, but did not.")
    assert_that(out).contains("[test_warn.py:90]: Expected <FOO> to contain only lowercase chars, but did not.")
    assert_that(out).contains("[test_warn.py:91]: Expected <foo> to be equal to <bar>, but was not.")
    assert_that(out).contains("[test_warn.py:92]: Expected <foo> to be not equal to <foo>, but was.")
    assert_that(out).contains("[test_warn.py:93]: Expected <foo> to be case-insensitive equal to <BAR>, but was not.")
