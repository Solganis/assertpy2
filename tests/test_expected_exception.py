import logging
from functools import partial
from io import StringIO

import pytest

from assertpy2 import WarningLoggingAdapter, assert_that, assert_warn, soft_assertions
from tests.group_compat import BaseExceptionGroup as _BaseExceptionGroup
from tests.group_compat import ExceptionGroup as _ExceptionGroup
from tests.group_compat import needs_groups


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
    assert_that(str(exc_info.value)).contains("given exception arg must be an exception type")


def test_expected_exception_no_arg_wrong_exception_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_no_arg).raises(TypeError).when_called_with()
    assert_that(str(exc_info.value)).contains(
        "Expected <func_no_arg> to raise <TypeError> when called with (), but raised <RuntimeError>."
    )


@pytest.mark.parametrize("wrong", [42, ValueError("instance")])
def test_expectation_that_is_not_a_class_is_refused(wrong):
    # `issubclass()` names no assertion, so a non-class read as "issubclass() arg 1 must be a class"
    with pytest.raises(TypeError, match="must be an exception type"):
        assert_that(func_noop).raises(wrong)
    with pytest.raises(TypeError, match="must be an exception type"):
        assert_that(func_noop).does_not_raise(wrong)


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
        assert_that(str(exc_info.value)).is_equal_to("val must be callable, but was <42> (int)")

    def test_not_exception_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(lambda: None).does_not_raise(str)
        assert_that(str(exc_info.value)).is_equal_to(
            "given exception arg must be an exception type, but was <<class 'str'>> (type)"
        )

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
        raise ValueError("clean") from None


def _raise_deep_chain():
    try:
        try:
            raise KeyError("root")
        except KeyError as exc:
            raise TimeoutError("middle") from exc
    except TimeoutError as exc:
        raise ValueError("top") from exc


def _raise_group():
    raise _ExceptionGroup("boom", [ValueError("v"), KeyError("k")])


def _raise_nested_group():
    raise _ExceptionGroup("boom", [ValueError("v"), _ExceptionGroup("inner", [TypeError("deep")])])


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
        second.__cause__ = first

        def raise_cyclic():
            raise first

        assert_that(raise_cyclic).raises(ValueError).when_called_with().has_root_cause(KeyError)

    def test_cycle_not_returning_to_head_terminates(self):
        head = ValueError("head")
        mid = KeyError("mid")
        tail = TypeError("tail")
        head.__cause__ = mid
        mid.__cause__ = tail
        tail.__cause__ = mid

        def raise_head():
            raise head

        assert_that(raise_head).raises(ValueError).when_called_with().has_root_cause(TypeError)

    def test_pivot_carries_the_root_object(self):
        chain = assert_that(_raise_deep_chain).raises(ValueError).when_called_with().has_root_cause(KeyError)
        chain.raised().is_instance_of(KeyError)


@needs_groups
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


@needs_groups
class TestGroupPivots:
    def test_errors_yields_the_leaves(self):
        # the types in order: a length alone would hold if the view kept the group and dropped a leaf
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        assert_that([type(leaf) for leaf in caught.errors().value]).is_equal_to([ValueError, KeyError])

    def test_errors_flattens_nesting(self):
        caught = assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with()
        assert_that([type(leaf) for leaf in caught.errors().value]).is_equal_to([ValueError, TypeError])
        caught.errors().extracting("args").is_equal_to([("v",), ("deep",)])

    def test_errors_reaches_collection_assertions(self):
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        caught.errors().extracting("args").contains(("v",), ("k",))

    def test_errors_on_a_plain_exception_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_config).raises(_ConfigError).when_called_with().errors()
        assert_that(str(exc_info.value)).contains("to be an exception group")

    def test_error_of_pivots_to_that_message(self):
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().error_of(KeyError).contains("k")

    def test_error_of_reaches_into_nesting(self):
        caught = assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with()
        caught.error_of(TypeError).contains("deep")

    def test_error_of_carries_the_object(self):
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        caught.error_of(KeyError).raised().is_instance_of(KeyError)

    def test_error_of_missing_type_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().error_of(TypeError)
        assert_that(str(exc_info.value)).contains("to contain <TypeError>")

    def test_error_of_on_a_plain_exception_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_config).raises(_ConfigError).when_called_with().error_of(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")

    def test_does_not_contain_error_passes(self):
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().does_not_contain_error(TypeError)

    def test_does_not_contain_error_present_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().does_not_contain_error(ValueError)
        assert_that(str(exc_info.value)).contains("to not contain <ValueError>")

    def test_does_not_contain_error_on_a_plain_exception_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_config).raises(_ConfigError).when_called_with().does_not_contain_error(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")

    def test_soft_collects_every_group_failure(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().error_of(TypeError)
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().does_not_contain_error(ValueError)
            assert_that(_raise_config).raises(_ConfigError).when_called_with().errors()
        collected = str(exc_info.value)
        assert_that(collected).contains("to contain <TypeError>", "to not contain <ValueError>")
        assert_that(collected).contains("to be an exception group")

    def test_the_leaves_view_does_not_carry_the_exception(self):
        # `_ListAssertion` declares no `raised()`, so the runtime must not offer one: the hole closes both ways
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        with pytest.raises(TypeError, match="no exception captured"):
            caught.errors().raised()

    def test_a_pivot_without_a_caught_exception_names_itself(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(lambda: 1).does_not_raise(ValueError).when_called_with().errors()
        assert_that(str(exc_info.value)).contains("errors() is only valid after")

    def test_an_empty_call_is_refused_by_both_forms(self):
        # these two used to pass on a call with nothing to look for, which is the failure mode itself
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        with pytest.raises(ValueError, match="one or more args"):
            caught.contains_error()
        with pytest.raises(ValueError, match="one or more args"):
            caught.does_not_contain_error()

    def test_a_deeply_nested_group_is_still_answered(self):
        group = _ExceptionGroup("leaf", [ValueError("v")])
        for _ in range(3000):
            group = _ExceptionGroup("outer", [group])

        def raise_deep():
            raise group

        caught = assert_that(raise_deep).raises(_ExceptionGroup).when_called_with()
        caught.contains_error(ValueError)
        caught.error_of(ValueError).contains("v")
        caught.errors().is_length(1)

    def test_a_group_that_lies_about_its_own_members_is_answered_the_same_way(self):
        class _LyingGroup(_ExceptionGroup):
            def subgroup(self, condition):
                return None

        def raise_lying():
            raise _LyingGroup("boom", [ValueError("v")])

        caught = assert_that(raise_lying).raises(_LyingGroup).when_called_with()
        caught.contains_error(ValueError)
        caught.error_of(ValueError).contains("v")
        with pytest.raises(AssertionError):
            caught.does_not_contain_error(ValueError)

    @pytest.mark.parametrize("wrong", [str, 42, ValueError("instance"), (TypeError, KeyError)])
    def test_anything_but_an_exception_type_is_refused(self, wrong):
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        for call in (caught.contains_error, caught.does_not_contain_error, caught.error_of):
            with pytest.raises(TypeError, match="must be an exception type"):
                call(wrong)

    def test_a_group_type_reaches_the_group_itself_from_every_form(self):
        caught = assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with()
        caught.contains_error(_ExceptionGroup)
        caught.error_of(_ExceptionGroup).contains("boom")
        with pytest.raises(AssertionError):
            caught.does_not_contain_error(_ExceptionGroup)

    def test_the_first_leaf_of_a_type_is_the_one_pivoted_to(self):
        first, second = ValueError("first"), ValueError("second")

        def raise_two():
            raise _ExceptionGroup("boom", [_ExceptionGroup("inner", [first]), second])

        caught = assert_that(raise_two).raises(_ExceptionGroup).when_called_with()
        assert caught.error_of(ValueError).raised().value is first

    def test_a_bare_base_exception_is_a_leaf_like_any_other(self):
        def raise_base():
            raise _BaseExceptionGroup("cancelled", [KeyboardInterrupt(), ValueError("v")])

        caught = assert_that(raise_base).raises(_BaseExceptionGroup).when_called_with()
        caught.errors().is_length(2)
        caught.contains_error(KeyboardInterrupt)
        caught.error_of(KeyboardInterrupt).raised().is_instance_of(KeyboardInterrupt)

    def test_soft_keeps_chaining_after_a_pivot_on_a_plain_exception(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_config).raises(_ConfigError).when_called_with().error_of(ValueError).contains("nope")
            assert_that(_raise_config).raises(_ConfigError).when_called_with().does_not_contain_error(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")


def test_raises_partial_without_name_fails_cleanly():
    def boom(x):
        if x > 5:
            raise ValueError("big")

    with pytest.raises(AssertionError):
        assert_that(partial(boom, 3)).raises(ValueError).when_called_with()
    with pytest.raises(AssertionError):
        assert_that(partial(boom, 9)).raises(KeyError).when_called_with()


class TestAnInterruptIsNotAMismatch:
    """Ctrl+C and ``sys.exit()`` belong to the runner, and both capture paths used to keep them."""

    @staticmethod
    def _interrupt():
        raise KeyboardInterrupt

    @staticmethod
    def _exit():
        raise SystemExit(3)

    def test_raises_lets_an_interrupt_through_instead_of_reporting_it(self):
        with pytest.raises(KeyboardInterrupt):
            assert_that(self._interrupt).raises(ValueError).when_called_with()

    def test_does_not_raise_lets_an_interrupt_through_instead_of_swallowing_it(self):
        with pytest.raises(KeyboardInterrupt):
            assert_that(self._interrupt).does_not_raise(ValueError).when_called_with()

    def test_an_exit_travels_the_same_way(self):
        with pytest.raises(SystemExit):
            assert_that(self._exit).does_not_raise(ValueError).when_called_with()

    def test_asking_for_one_by_name_still_catches_it(self):
        assert_that(self._interrupt).raises(KeyboardInterrupt).when_called_with()
        assert_that(self._exit).raises(SystemExit).when_called_with()

    def test_a_named_interrupt_that_does_arrive_is_still_refused_by_the_negative_form(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(self._exit).does_not_raise(SystemExit).when_called_with()
        assert_that(str(exc_info.value)).contains("did raise <SystemExit>")

    def test_an_ordinary_mismatch_is_still_reported(self):
        def boom():
            raise TypeError("wrong one")

        with pytest.raises(AssertionError) as exc_info:
            assert_that(boom).raises(ValueError).when_called_with()
        assert_that(str(exc_info.value)).contains("but raised <TypeError>")


@needs_groups
class TestMatchesErrorTree:
    """The shape of the group, which `contains_error` deliberately says nothing about.

    That one searches the whole tree for a type, so a group that grew a third failure, or one whose
    members moved into a subgroup, still passes it. These read the tree.
    """

    def test_the_flat_shape_matches(self):
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(ValueError, KeyError)

    def test_order_is_not_part_of_the_shape(self):
        """An `asyncio.TaskGroup` reports its failures in the order the tasks finished, not a chosen one."""
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(KeyError, ValueError)

    def test_the_nested_shape_matches(self):
        assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
            ValueError, [TypeError]
        )

    def test_a_flat_spec_refuses_a_nested_group(self):
        """The gap this exists for: `contains_error(ValueError, TypeError)` passes on this very group."""
        assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with().contains_error(
            ValueError, TypeError
        )
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
                ValueError, TypeError
            )
        assert_that(str(exc_info.value)).contains("[ValueError, TypeError]", "[ValueError, [TypeError]]")

    def test_a_nested_spec_refuses_a_flat_group(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
                ValueError, [KeyError]
            )
        assert_that(str(exc_info.value)).contains("[ValueError, [KeyError]]")

    def test_an_extra_exception_refuses(self):
        def raise_three():
            raise _ExceptionGroup("boom", [ValueError("v"), KeyError("k"), TypeError("t")])

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raise_three).raises(_ExceptionGroup).when_called_with().matches_error_tree(ValueError, KeyError)
        assert_that(str(exc_info.value)).contains("[ValueError, KeyError, TypeError]")

    def test_a_type_matches_a_subgroup_node(self):
        """`isinstance` is what the rest of the family uses, and a group is an exception."""
        assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
            ValueError, Exception
        )

    @pytest.mark.parametrize(
        "spec",
        [(Exception, ValueError), (ValueError, Exception)],
        ids=["the wide entry written first", "written second"],
    )
    def test_the_verdict_does_not_depend_on_how_the_spec_is_ordered(self, spec):
        """A complete matching, not a greedy walk.

        Measured against `pytest.RaisesGroup`, which pairs greedily: it accepts the second spelling and
        refuses the first, on the same group.
        """
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(*spec)

    def test_two_of_one_type_need_two_of_them(self):
        with pytest.raises(AssertionError):
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
                ValueError, ValueError
            )

    def test_a_deep_tree_matches_entry_for_entry(self):
        def raise_deep():
            raise _ExceptionGroup("l0", [_ExceptionGroup("l1", [_ExceptionGroup("l2", [ValueError("v")])])])

        assert_that(raise_deep).raises(_ExceptionGroup).when_called_with().matches_error_tree([[ValueError]])

    def test_a_type_entry_leaves_the_subgroup_it_matches_unconstrained(self):
        def raise_nested():
            raise _ExceptionGroup("failed", [_ExceptionGroup("inner", [ValueError("a"), KeyError("b")])])

        assert_that(raise_nested).raises(_ExceptionGroup).when_called_with().matches_error_tree(Exception)

    def test_two_classes_of_one_name_are_told_apart_in_the_message(self):
        expected = type("Error", (Exception,), {"__module__": "service.first"})
        raised = type("Error", (Exception,), {"__module__": "service.second"})

        def raise_theirs():
            raise _ExceptionGroup("failed", [raised("b")])

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raise_theirs).raises(_ExceptionGroup).when_called_with().matches_error_tree(expected)
        assert_that(str(exc_info.value)).contains("<[service.first.Error]>", "<[service.second.Error]>")

    def test_two_classes_alike_to_the_qualified_name_get_an_ordinal(self):
        def make_error():
            class Error(Exception):
                pass

            return Error

        expected, raised = make_error(), make_error()

        def raise_theirs():
            raise _ExceptionGroup("failed", [raised("b")])

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raise_theirs).raises(_ExceptionGroup).when_called_with().matches_error_tree(expected)
        assert_that(str(exc_info.value)).contains("Error#1]>", "Error#2]>")

    def test_an_unhashable_class_is_still_named(self):
        """A metaclass can refuse to be hashed, and the message still has to arrive.

        The other three group assertions report against such a class and carry on, so this one raising
        `TypeError` instead would be the family disagreeing with itself.
        """
        raised = type("Unhashable", (type,), {"__hash__": None})("Error", (Exception,), {})

        def raise_theirs():
            raise _ExceptionGroup("failed", [raised("w")])

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raise_theirs).raises(_ExceptionGroup).when_called_with().matches_error_tree(ValueError)
        assert_that(str(exc_info.value)).contains("<[ValueError]>", "<[Error]>")

    def test_two_classes_equal_to_each_other_are_still_told_apart(self):
        collapsing = type("Collapsing", (type,), {"__eq__": lambda cls, other: True, "__hash__": lambda cls: 0})
        expected = collapsing("Error", (Exception,), {"__module__": "svc"})
        raised = collapsing("Error", (Exception,), {"__module__": "svc"})

        def raise_theirs():
            raise _ExceptionGroup("failed", [raised("w")])

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raise_theirs).raises(_ExceptionGroup).when_called_with().matches_error_tree(expected)
        assert_that(str(exc_info.value)).contains("<[svc.Error#1]>", "<[svc.Error#2]>")

    def test_a_name_nothing_collides_with_stays_short(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
                TypeError, TypeError
            )
        assert_that(str(exc_info.value)).contains("<[TypeError, TypeError]>", "<[ValueError, KeyError]>")

    def test_a_wide_group_of_one_type_matches_entry_for_entry(self):
        def raise_wide():
            raise _ExceptionGroup("wide", [ValueError(str(index)) for index in range(1100)])

        assert_that(raise_wide).raises(_ExceptionGroup).when_called_with().matches_error_tree(*[Exception] * 1100)

    def test_a_mismatch_against_a_deep_tree_still_reports(self):
        def raise_very_deep():
            error: BaseException = ValueError("leaf")
            for _ in range(3000):
                error = _ExceptionGroup("nested", [error])
            raise error

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raise_very_deep).raises(_ExceptionGroup).when_called_with().matches_error_tree(ValueError)
        assert_that(str(exc_info.value)).contains("[[[")

    def test_no_arguments_is_refused(self):
        with pytest.raises(ValueError, match="one or more args"):
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree()

    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            (("ValueError",), "an exception type"),
            ((ValueError, (KeyError,)), "a list for a subgroup"),
            ((ValueError, []), "a non-empty subgroup"),
            ((ValueError, [42]), "an exception type"),
        ],
        ids=["a string", "a tuple", "an empty subgroup", "a bad type inside one"],
    )
    def test_a_malformed_spec_is_refused_before_the_group_is_read(self, spec, expected):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(*spec)
        assert_that(str(exc_info.value)).contains(expected)

    def test_not_a_group_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_config).raises(_ConfigError).when_called_with().matches_error_tree(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")

    def test_not_a_group_soft_collects(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_config).raises(_ConfigError).when_called_with().matches_error_tree(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")

    def test_a_mismatch_soft_collects(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(TypeError)
        assert_that(str(exc_info.value)).contains("to match <[TypeError]>")

    def test_the_chain_continues_after_it_holds(self):
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
            ValueError, KeyError
        ).errors().is_length(2)
