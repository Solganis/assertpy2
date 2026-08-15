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
        raise ValueError("clean") from None  # suppresses the chained context


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
        # the types, in order: a length alone would hold just as well if the view kept the group and
        # dropped a leaf, which is the mistake this is here to catch
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        assert_that([type(leaf) for leaf in caught.errors().value]).is_equal_to([ValueError, KeyError])

    def test_errors_flattens_nesting(self):
        caught = assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with()
        # the inner group is walked through rather than handed over, so what comes back is two leaves
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
        # `_ListAssertion` declares no `raised()`, so the runtime must not offer one either: a path the
        # typed surface refuses is the hole this library keeps closing, and it closes both ways
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        with pytest.raises(TypeError, match="no exception captured"):
            caught.errors().raised()

    def test_a_pivot_without_a_caught_exception_names_itself(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(lambda: 1).does_not_raise(ValueError).when_called_with().errors()
        assert_that(str(exc_info.value)).contains("errors() is only valid after")

    def test_an_empty_call_is_refused_by_both_forms(self):
        # the rest of the contains family refuses a call with nothing to look for, and these two used
        # to pass on it: an assertion that asks nothing cannot fail, which is the failure mode itself
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        with pytest.raises(ValueError, match="one or more args"):
            caught.contains_error()
        with pytest.raises(ValueError, match="one or more args"):
            caught.does_not_contain_error()

    def test_a_deeply_nested_group_is_still_answered(self):
        # `subgroup()` is written in C and walks a group thousands deep; the walk that replaced it has to
        # hold the same ground, and a recursive one gave up around five hundred
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
        # `subgroup()` is a method a subclass can override, and two of the three used to trust it while
        # `error_of` walked the tree. One shared walk is what keeps the verdicts from splitting.
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
        # `isinstance(node, str)` answers False rather than complaining, so without this the mistake
        # would read as a verdict about the group. A tuple is refused too: the declared type is one class
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        for call in (caught.contains_error, caught.does_not_contain_error, caught.error_of):
            with pytest.raises(TypeError, match="must be an exception type"):
                call(wrong)

    def test_a_group_type_reaches_the_group_itself_from_every_form(self):
        # `subgroup()` matches group nodes as well as leaves, so `error_of` walks the same nodes: the
        # three used to disagree here, with `contains_error` passing and `error_of` reporting a miss
        caught = assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with()
        caught.contains_error(_ExceptionGroup)
        caught.error_of(_ExceptionGroup).contains("boom")  # str() of a group adds its sub-exception count
        with pytest.raises(AssertionError):
            caught.does_not_contain_error(_ExceptionGroup)

    def test_the_first_leaf_of_a_type_is_the_one_pivoted_to(self):
        first, second = ValueError("first"), ValueError("second")

        def raise_two():
            raise _ExceptionGroup("boom", [_ExceptionGroup("inner", [first]), second])

        caught = assert_that(raise_two).raises(_ExceptionGroup).when_called_with()
        # depth-first, so the nested one comes before the sibling that follows its group
        assert caught.error_of(ValueError).raised().value is first

    def test_a_bare_base_exception_is_a_leaf_like_any_other(self):
        # `errors()` is typed `list[BaseException]` rather than `list[Exception]`, which is what a
        # cancelled task group hands over: KeyboardInterrupt and SystemExit are not Exceptions
        def raise_base():
            raise _BaseExceptionGroup("cancelled", [KeyboardInterrupt(), ValueError("v")])

        caught = assert_that(raise_base).raises(_BaseExceptionGroup).when_called_with()
        caught.errors().is_length(2)
        caught.contains_error(KeyboardInterrupt)
        caught.error_of(KeyboardInterrupt).raised().is_instance_of(KeyboardInterrupt)

    def test_soft_keeps_chaining_after_a_pivot_on_a_plain_exception(self):
        # under soft assertions `error()` collects instead of raising, so each pivot has to hand back
        # something chainable: the inert builder, which records the first failure and swallows the rest
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_config).raises(_ConfigError).when_called_with().error_of(ValueError).contains("nope")
            assert_that(_raise_config).raises(_ConfigError).when_called_with().does_not_contain_error(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")


def test_raises_partial_without_name_fails_cleanly():
    # a callable lacking __name__ (functools.partial) must fail cleanly, not raise AttributeError
    def boom(x):
        if x > 5:
            raise ValueError("big")

    with pytest.raises(AssertionError):
        assert_that(partial(boom, 3)).raises(ValueError).when_called_with()
    with pytest.raises(AssertionError):
        assert_that(partial(boom, 9)).raises(KeyError).when_called_with()
