import logging
import sys
from io import StringIO

import pytest

from assertpy2 import WarningLoggingAdapter, assert_that, assert_warn, soft_assertions


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
    assert_that(str(exc_info.value)).contains("no expectation set")


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
        "Expected <func_noop> to raise <RuntimeError> when called with "
        "('a', 'b', 3, 4, 'bar': 2, 'baz': 'dog', 'foo': 1)."
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
        f"all err: arg1={arg1}, arg2={arg2}, args={args}, "
        f"kwargs={[(key, kwargs[key]) for key in sorted(kwargs.keys())]}"
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


def safe_add(value):
    return value + 1


def test_does_not_raise_returned_pivots_to_return_value():
    assert_that(safe_add).does_not_raise(ValueError).when_called_with(41).returned().is_equal_to(42)


def test_returned_without_return_value_fails():
    with pytest.raises(TypeError) as exc_info:
        assert_that(func_no_arg).raises(RuntimeError).when_called_with().returned()
    assert_that(str(exc_info.value)).contains("no return value captured")


class TestDoesNotRaise:
    def test_no_exception(self):
        def safe_func(x):
            return x + 1

        assert_that(safe_func).does_not_raise(ValueError).when_called_with(1)

    def test_different_exception(self):
        def raises_type_error():
            raise TypeError("oops")

        assert_that(raises_type_error).does_not_raise(ValueError).when_called_with()

    def test_raises_expected_failure(self):
        def raises_value_error():
            raise ValueError("bad value")

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raises_value_error).does_not_raise(ValueError).when_called_with()
        assert_that(str(exc_info.value)).contains("to not raise <ValueError>")
        assert_that(str(exc_info.value)).contains("but did raise")

    def test_raises_subclass_failure(self):
        def raises_file_not_found():
            raise FileNotFoundError("missing")

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raises_file_not_found).does_not_raise(OSError).when_called_with()
        assert_that(str(exc_info.value)).contains("to not raise <OSError>")

    def test_not_callable_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).does_not_raise(ValueError)
        assert_that(str(exc_info.value)).is_equal_to("val must be callable")

    def test_not_exception_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(lambda: None).does_not_raise(str)
        assert_that(str(exc_info.value)).is_equal_to("given arg must be exception")

    def test_raises_expected_soft_mode(self):
        def raises_value_error():
            raise ValueError("bad value")

        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(raises_value_error).does_not_raise(ValueError).when_called_with()
        assert_that(str(exc_info.value)).contains("to not raise <ValueError>")


class _ConfigError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def _raise_config():
    raise _ConfigError("bad config", 42)


def _raise_wrapped_from():
    try:
        raise KeyError("missing")
    except KeyError as exc:
        raise ValueError("wrapped") from exc


def _raise_during_handling():
    try:
        raise ZeroDivisionError
    except ZeroDivisionError:
        raise RuntimeError("during handling")  # noqa: B904  # intentional implicit __context__ (no `from`)


def _raise_suppressed():
    try:
        raise ZeroDivisionError
    except ZeroDivisionError:
        raise ValueError("clean") from None  # suppresses the chained context


def _raise_deep_chain():
    try:
        try:
            raise KeyError("root")
        except KeyError as exc:
            raise TimeoutError("middle") from exc
    except TimeoutError as exc:
        raise ValueError("top") from exc


# Exception groups are a 3.11+ feature; alias the builtin once and gate the group tests on the version.
if sys.version_info >= (3, 11):
    _ExceptionGroup = ExceptionGroup  # noqa: F821  # 3.11+ builtin; TestContainsError is skipped below on 3.10


def _raise_group():
    raise _ExceptionGroup("boom", [ValueError("v"), KeyError("k")])


class TestRaisedPivot:
    def test_pivots_to_exception_object(self):
        err = assert_that(_raise_config).raises(_ConfigError).when_called_with().raised().value
        assert_that(err.code).is_equal_to(42)

    def test_raised_object_supports_core_assertions(self):
        assert_that(_raise_config).raises(_ConfigError).when_called_with().raised().is_instance_of(_ConfigError)

    def test_raised_without_capture_fails(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_raise_config).raised()
        assert_that(str(exc_info.value)).contains("no exception captured")


class TestCausedBy:
    def test_explicit_cause(self):
        assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().caused_by(KeyError)

    def test_implicit_context_cause(self):
        assert_that(_raise_during_handling).raises(RuntimeError).when_called_with().caused_by(ZeroDivisionError)

    def test_pivots_to_cause_message(self):
        chain = assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().caused_by(KeyError)
        chain.is_equal_to("'missing'")

    def test_wrong_cause_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().caused_by(TypeError)
        assert_that(str(exc_info.value)).contains("to be caused by <TypeError>").contains("<KeyError>")

    def test_no_cause_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_config).raises(_ConfigError).when_called_with().caused_by(KeyError)
        assert_that(str(exc_info.value)).contains("the cause was no cause")

    def test_suppressed_context_has_no_cause(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_suppressed).raises(ValueError).when_called_with().caused_by(ZeroDivisionError)
        assert_that(str(exc_info.value)).contains("the cause was no cause")

    def test_wrong_cause_soft_collects(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().caused_by(TypeError)
        assert_that(str(exc_info.value)).contains("to be caused by <TypeError>")

    def test_pivot_carries_the_cause_object(self):
        # after caused_by, raised() hands back the cause object itself, so the chain can walk deeper
        chain = assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().caused_by(KeyError)
        chain.raised().is_instance_of(KeyError)

    def test_caused_by_without_capture_fails(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_raise_config).caused_by(KeyError)
        assert_that(str(exc_info.value)).contains("no exception captured")


class TestHasRootCause:
    def test_single_level_root(self):
        assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().has_root_cause(KeyError)

    def test_deep_chain_root(self):
        assert_that(_raise_deep_chain).raises(ValueError).when_called_with().has_root_cause(KeyError)

    def test_pivots_to_root_message(self):
        chain = assert_that(_raise_deep_chain).raises(ValueError).when_called_with().has_root_cause(KeyError)
        chain.is_equal_to("'root'")

    def test_wrong_root_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_deep_chain).raises(ValueError).when_called_with().has_root_cause(TypeError)
        assert_that(str(exc_info.value)).contains("root cause <TypeError>").contains("<KeyError>")

    def test_wrong_root_soft_collects(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_deep_chain).raises(ValueError).when_called_with().has_root_cause(TypeError)
        assert_that(str(exc_info.value)).contains("root cause")

    def test_cyclic_cause_chain_terminates(self):
        first = ValueError("a")
        second = KeyError("b")
        first.__cause__ = second
        second.__cause__ = first  # a cycle the walk must not loop on

        def raise_cyclic():
            raise first

        assert_that(raise_cyclic).raises(ValueError).when_called_with().has_root_cause(KeyError)

    def test_cycle_not_returning_to_head_terminates(self):
        head = ValueError("head")
        mid = KeyError("mid")
        tail = TypeError("tail")
        head.__cause__ = mid
        mid.__cause__ = tail
        tail.__cause__ = mid  # a mid<->tail cycle that never returns to the head

        def raise_head():
            raise head

        assert_that(raise_head).raises(ValueError).when_called_with().has_root_cause(TypeError)

    def test_pivot_carries_the_root_object(self):
        chain = assert_that(_raise_deep_chain).raises(ValueError).when_called_with().has_root_cause(KeyError)
        chain.raised().is_instance_of(KeyError)


@pytest.mark.skipif(sys.version_info < (3, 11), reason="ExceptionGroup requires Python 3.11+")
class TestContainsError:
    def test_group_contains_all(self):
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().contains_error(ValueError, KeyError)

    def test_group_missing_type_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().contains_error(TypeError)
        assert_that(str(exc_info.value)).contains("to contain <TypeError>")

    def test_not_a_group_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_config).raises(_ConfigError).when_called_with().contains_error(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")

    def test_missing_type_soft_collects(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().contains_error(TypeError)
        assert_that(str(exc_info.value)).contains("to contain <TypeError>")

    def test_not_a_group_soft_collects(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_config).raises(_ConfigError).when_called_with().contains_error(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")
