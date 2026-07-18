import logging
import warnings
from functools import partial
from io import StringIO

import pytest

from assertpy2 import WarningLoggingAdapter, assert_that, assert_warn, soft_assertions

_calls = []


# helpers
def warn_deprecation(*args, **kwargs):
    warnings.warn("deprecated since 2.6", DeprecationWarning, stacklevel=2)


def warn_user(*args, **kwargs):
    warnings.warn("user warning", UserWarning, stacklevel=2)


def no_warn(*args, **kwargs):
    pass


def warn_then_raise():
    warnings.warn("before boom", UserWarning, stacklevel=2)
    raise RuntimeError("boom")


def warn_with_args(arg1, arg2, *, keyword):
    _calls.append((arg1, arg2, keyword))
    warnings.warn("args ok", UserWarning, stacklevel=2)


# warns - success
def test_warns_success():
    assert_that(warn_deprecation).warns(DeprecationWarning).when_called_with()


def test_warns_default_matches_any_warning():
    assert_that(warn_user).warns().when_called_with()


def test_warns_matches_subclass():
    assert_that(warn_deprecation).warns(Warning).when_called_with()


def test_warns_chains_on_message():
    assert_that(warn_deprecation).warns(DeprecationWarning).when_called_with().is_equal_to("deprecated since 2.6")
    assert_that(warn_deprecation).warns(DeprecationWarning).when_called_with().matches(r"since 2\.6")


def test_warns_passes_args_and_kwargs():
    _calls.clear()
    assert_that(warn_with_args).warns(UserWarning).when_called_with("a", "b", keyword="c")
    assert_that(_calls).is_equal_to([("a", "b", "c")])


# warns - failure
def test_warns_failure_no_warning():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(no_warn).warns(DeprecationWarning).when_called_with()
    assert_that(str(exc_info.value)).is_equal_to("Expected <no_warn> to warn <DeprecationWarning> when called with ().")


def test_warns_failure_wrong_category():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(warn_user).warns(DeprecationWarning).when_called_with()
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <warn_user> to warn <DeprecationWarning> when called with (), but warned <UserWarning>."
    )


# warns - bad input
def test_warns_val_not_callable():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).warns(UserWarning)
    assert_that(str(exc_info.value)).contains("val must be callable")


def test_warns_arg_not_a_warning():
    with pytest.raises(TypeError) as exc_info:
        assert_that(no_warn).warns(ValueError)
    assert_that(str(exc_info.value)).contains("given arg must be a warning")


# does_not_warn
def test_does_not_warn_success():
    assert_that(no_warn).does_not_warn(DeprecationWarning).when_called_with()


def test_does_not_warn_other_category_is_ignored():
    assert_that(warn_user).does_not_warn(DeprecationWarning).when_called_with()


def test_does_not_warn_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(warn_user).does_not_warn(UserWarning).when_called_with()
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <warn_user> to not warn <UserWarning> when called with (), but did warn <UserWarning>."
    )


# semantics: registry dedup, filterwarnings=error, exception propagation
def test_warns_bypasses_show_once_dedup():
    # without simplefilter("always") the second identical warning would be swallowed by __warningregistry__
    assert_that(warn_user).warns(UserWarning).when_called_with()
    assert_that(warn_user).warns(UserWarning).when_called_with()


def test_warns_captures_under_filterwarnings_error():
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # turn warnings into errors globally
        assert_that(warn_user).warns(UserWarning).when_called_with()  # still captured, not raised


def test_warns_propagates_exception_from_callable():
    with pytest.raises(RuntimeError) as exc_info:
        assert_that(warn_then_raise).warns(UserWarning).when_called_with()
    assert_that(str(exc_info.value)).is_equal_to("boom")


# integration with soft and warn modes
def test_warns_in_soft_assertions_collects():
    with pytest.raises(AssertionError) as exc_info:  # noqa: SIM117  # nested with is clearer than a combined one here
        with soft_assertions():
            assert_that(no_warn).warns(DeprecationWarning).when_called_with()
            assert_that(1).is_equal_to(2)
    message = str(exc_info.value)
    assert_that(message).contains("Expected <no_warn> to warn <DeprecationWarning>")
    assert_that(message).contains("Expected <1> to be equal to <2>")


def test_warns_in_warn_mode_logs():
    capture = StringIO()
    logger = logging.getLogger("capture_warns")
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn(no_warn, logger=adapted).warns(DeprecationWarning).when_called_with()

    out = capture.getvalue()
    capture.close()
    assert_that(out).contains("Expected <no_warn> to warn <DeprecationWarning> when called with ().")


def test_warns_wrong_category_in_warn_mode_logs():
    capture = StringIO()
    logger = logging.getLogger("capture_warns_wrong")
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn(warn_user, logger=adapted).warns(DeprecationWarning).when_called_with()

    out = capture.getvalue()
    capture.close()
    assert_that(out).contains(
        "Expected <warn_user> to warn <DeprecationWarning> when called with (), but warned <UserWarning>."
    )


def test_does_not_warn_failure_in_warn_mode_logs():
    capture = StringIO()
    logger = logging.getLogger("capture_does_not_warn")
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn(warn_user, logger=adapted).does_not_warn(UserWarning).when_called_with()

    out = capture.getvalue()
    capture.close()
    assert_that(out).contains(
        "Expected <warn_user> to not warn <UserWarning> when called with (), but did warn <UserWarning>."
    )


# returned() pivot to the callable's return value


def warn_and_return_list(*args, **kwargs):
    warnings.warn("dep since 2.7", DeprecationWarning, stacklevel=2)
    return [1, 2, 3]


def quiet_return_ok(*args, **kwargs):
    return "ok"


def test_warns_returned_pivots_to_return_value():
    assert_that(warn_and_return_list).warns(DeprecationWarning).when_called_with().returned().is_equal_to([1, 2, 3])


def test_warns_returned_after_message_assertion():
    assert_that(warn_and_return_list).warns(DeprecationWarning).when_called_with().matches(
        "since 2.7"
    ).returned().is_equal_to([1, 2, 3])


def test_does_not_warn_returned_pivots_to_return_value():
    assert_that(quiet_return_ok).does_not_warn(DeprecationWarning).when_called_with().returned().is_equal_to("ok")


def test_warns_partial_without_name_fails_cleanly():
    # a callable lacking __name__ (functools.partial) must fail cleanly, not raise AttributeError
    def emit(level):
        if level > 5:
            warnings.warn("hi", UserWarning, stacklevel=2)

    with pytest.raises(AssertionError):
        assert_that(partial(emit, 3)).warns(UserWarning).when_called_with()
    with pytest.raises(AssertionError):
        assert_that(partial(emit, 9)).does_not_warn(UserWarning).when_called_with()


def test_custom_logger_survives_collection_transform():
    # a transform (filtered_on/mapped/first/...) must forward the caller's logger, so a warning from a
    # failing assertion after it still reaches the custom logger, not the library default
    capture = StringIO()
    logger = logging.getLogger("test_transform_logger")
    logger.addHandler(logging.StreamHandler(capture))
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn([1, -2, 3], logger=adapted).filtered_on(lambda item: item > 0).contains(999)
    assert_that(capture.getvalue()).contains("to contain")
