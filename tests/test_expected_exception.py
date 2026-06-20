import logging
from io import StringIO

import pytest

from assertpy2 import WarningLoggingAdapter, assert_that, assert_warn


def test_expected_exception():
    assert_that(func_no_arg).raises(RuntimeError).when_called_with()
    assert_that(func_one_arg).raises(RuntimeError).when_called_with("foo")
    assert_that(func_multi_args).raises(RuntimeError).when_called_with("foo", "bar", "baz")
    assert_that(func_kwargs).raises(RuntimeError).when_called_with(foo=1, bar=2, baz=3)
    assert_that(func_all).raises(RuntimeError).when_called_with("a", "b", 3, 4, foo=1, bar=2, baz="dog")


def test_expected_exception_method():
    foo = Foo()
    assert_that(foo.bar).raises(RuntimeError).when_called_with().is_equal_to("method err")


def test_expected_exception_chaining():
    assert_that(func_no_arg).raises(RuntimeError).when_called_with().is_equal_to("no arg err")
    assert_that(func_one_arg).raises(RuntimeError).when_called_with("foo").is_equal_to("one arg err")
    assert_that(func_multi_args).raises(RuntimeError).when_called_with("foo", "bar", "baz").is_equal_to(
        "multi args err"
    )
    assert_that(func_kwargs).raises(RuntimeError).when_called_with(foo=1, bar=2, baz=3).is_equal_to("kwargs err")
    assert_that(func_all).raises(RuntimeError).when_called_with("a", "b", 3, 4, foo=1, bar=2, baz="dog").starts_with(
        "all err: arg1=a, arg2=b, args=(3, 4), kwargs=["
    )


def test_expected_exception_no_arg_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_noop).raises(RuntimeError).when_called_with()
    assert_that(str(exc_info.value)).is_equal_to("Expected <func_noop> to raise <RuntimeError> when called with ().")


def test_expected_exception_no_arg_bad_func_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).raises(int).when_called_with()
    assert_that(str(exc_info.value)).contains("val must be callable")


def test_expected_exception_no_arg_bad_exception_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(func_noop).raises(int).when_called_with()
    assert_that(str(exc_info.value)).contains("given arg must be exception")


def test_expected_exception_no_arg_wrong_exception_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_no_arg).raises(TypeError).when_called_with()
    assert_that(str(exc_info.value)).contains(
        "Expected <func_no_arg> to raise <TypeError> when called with (), but raised <RuntimeError>."
    )


def test_expected_exception_no_arg_missing_raises_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(func_noop).when_called_with()
    assert_that(str(exc_info.value)).contains(
        "expected exception not set, raises() or does_not_raise() must be called first"
    )


def test_expected_exception_one_arg_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_noop).raises(RuntimeError).when_called_with("foo")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <func_noop> to raise <RuntimeError> when called with ('foo')."
    )


def test_expected_exception_multi_args_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_noop).raises(RuntimeError).when_called_with("foo", "bar", "baz")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <func_noop> to raise <RuntimeError> when called with ('foo', 'bar', 'baz')."
    )


def test_expected_exception_kwargs_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_noop).raises(RuntimeError).when_called_with(foo=1, bar=2, baz=3)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <func_noop> to raise <RuntimeError> when called with ('bar': 2, 'baz': 3, 'foo': 1)."
    )


def test_expected_exception_all_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_noop).raises(RuntimeError).when_called_with("a", "b", 3, 4, foo=1, bar=2, baz="dog")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <func_noop> to raise <RuntimeError> when called with ('a', 'b', 3, 4, 'bar': 2, 'baz': 'dog', 'foo': 1)."
    )


def test_expected_exception_arg_passing():
    assert_that(func_all).raises(RuntimeError).when_called_with("a", "b", 3, 4, foo=1, bar=2, baz="dog").is_equal_to(
        "all err: arg1=a, arg2=b, args=(3, 4), kwargs=[('bar', 2), ('baz', 'dog'), ('foo', 1)]"
    )


# helpers
def func_noop(*args, **kwargs):
    pass


def func_no_arg():
    raise RuntimeError("no arg err")


def func_one_arg(arg):
    raise RuntimeError("one arg err")


def func_multi_args(*args):
    raise RuntimeError("multi args err")


def func_kwargs(**kwargs):
    raise RuntimeError("kwargs err")


def func_all(arg1, arg2, *args, **kwargs):
    raise RuntimeError(
        f"all err: arg1={arg1}, arg2={arg2}, args={args}, kwargs={[(key, kwargs[key]) for key in sorted(kwargs.keys())]}"
    )


def test_expected_exception_warn_preserves_logger():
    capture = StringIO()
    logger = logging.getLogger("capture_exc")
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn(func_no_arg, logger=adapted).raises(RuntimeError).when_called_with().is_equal_to("wrong msg")

    out = capture.getvalue()
    capture.close()

    assert_that(out).contains("Expected <no arg err> to be equal to <wrong msg>, but was not.")


def test_expected_exception_warn_wrong_type_preserves_logger():
    capture = StringIO()
    logger = logging.getLogger("capture_exc2")
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn(func_no_arg, logger=adapted).raises(ValueError).when_called_with()

    out = capture.getvalue()
    capture.close()

    assert_that(out).contains("Expected <func_no_arg> to raise <ValueError>")


class Foo:
    def bar(self):
        raise RuntimeError("method err")
