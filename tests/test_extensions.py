import numbers

import pytest

from assertpy2 import add_extension, assert_that, remove_extension


def is_even_integer(self):
    if not isinstance(self.val, numbers.Integral):
        raise TypeError("val must be an integer")
    if self.val % 2 != 0:
        return self.error(f"Expected <{self.val}> to be an even integer, but was not.")
    return self


def is_multiple_of(self, other):
    if not isinstance(self.val, numbers.Integral) or self.val <= 0:
        raise TypeError("val must be a positive integer")

    if not isinstance(other, numbers.Integral) or other <= 0:
        raise TypeError("given arg must be a positive integer")

    _, rem = divmod(self.val, other)
    if rem > 0:
        return self.error(f"Expected <{self.val}> to be multiple of <{other}>, but was not.")

    return self


def is_factor_of(self, other):
    if not isinstance(self.val, numbers.Integral) or self.val <= 0:
        raise TypeError("val must be a positive integer")

    if not isinstance(other, numbers.Integral) or other <= 0:
        raise TypeError("given arg must be a positive integer")

    _, rem = divmod(other, self.val)
    if rem > 0:
        return self.error(f"Expected <{self.val}> to be factor of <{other}>, but was not.")

    return self


add_extension(is_even_integer)
add_extension(is_multiple_of)
add_extension(is_factor_of)


def test_is_even_extension():
    assert_that(124).is_even_integer()
    assert_that(124).is_type_of(int).is_even_integer().is_greater_than(123).is_less_than(125).is_equal_to(124)


def test_is_even_extension_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_even_integer()
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be an even integer, but was not.")


def test_is_even_extension_failure_not_callable():
    with pytest.raises(TypeError) as exc_info:
        add_extension("foo")
    assert_that(str(exc_info.value)).is_equal_to("func must be callable")


def test_is_even_extension_failure_not_integer():
    with pytest.raises(TypeError) as exc_info:
        assert_that(124.0).is_even_integer()
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer")


def test_is_multiple_of_extension():
    assert_that(24).is_multiple_of(1)
    assert_that(24).is_multiple_of(2)
    assert_that(24).is_multiple_of(3)
    assert_that(24).is_multiple_of(4)
    assert_that(24).is_multiple_of(6)
    assert_that(24).is_multiple_of(8)
    assert_that(24).is_multiple_of(12)
    assert_that(24).is_multiple_of(24)
    assert_that(124).is_type_of(int).is_even_integer().is_multiple_of(31).is_equal_to(124)


def test_is_multiple_of_extension_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(24).is_multiple_of(5)
    assert_that(str(exc_info.value)).is_equal_to("Expected <24> to be multiple of <5>, but was not.")


def test_is_multiple_of_extension_failure_bad_val():
    with pytest.raises(TypeError) as exc_info:
        assert_that(24.0).is_multiple_of(5)
    assert_that(str(exc_info.value)).is_equal_to("val must be a positive integer")


def test_is_multiple_of_extension_failure_negative_val():
    with pytest.raises(TypeError) as exc_info:
        assert_that(-24).is_multiple_of(6)
    assert_that(str(exc_info.value)).is_equal_to("val must be a positive integer")


def test_is_multiple_of_extension_failure_bad_arg():
    with pytest.raises(TypeError) as exc_info:
        assert_that(24).is_multiple_of("foo")
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a positive integer")


def test_is_multiple_of_extension_failure_negative_arg():
    with pytest.raises(TypeError) as exc_info:
        assert_that(24).is_multiple_of(-6)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a positive integer")


def test_is_factor_of_extension():
    assert_that(1).is_factor_of(24)
    assert_that(2).is_factor_of(24)
    assert_that(3).is_factor_of(24)
    assert_that(4).is_factor_of(24)
    assert_that(6).is_factor_of(24)
    assert_that(8).is_factor_of(24)
    assert_that(12).is_factor_of(24)
    assert_that(24).is_factor_of(24)
    assert_that(31).is_type_of(int).is_factor_of(124).is_equal_to(31)


def test_is_factor_of_extension_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(5).is_factor_of(24)
    assert_that(str(exc_info.value)).is_equal_to("Expected <5> to be factor of <24>, but was not.")


def test_call_missing_extension():
    def is_missing():
        pass

    with pytest.raises(AttributeError) as exc_info:
        remove_extension(is_even_integer)
        remove_extension(is_multiple_of)
        remove_extension(is_factor_of)
        remove_extension(is_missing)
        assert_that(24).is_multiple_of(6)
    assert_that(str(exc_info.value)).is_equal_to("assertpy has no assertion <is_multiple_of()>")


def test_remove_bad_extension():
    with pytest.raises(TypeError) as exc_info:
        remove_extension("foo")
    assert_that(str(exc_info.value)).is_equal_to("func must be callable")


def is_foo(self):
    if self.val != "foo":
        return self.error(f"Expected <{self.val}> to be foo, but was not.")
    return self


def dupe1():
    # replacing an extension is the point of this pair, so it says so rather than relying on the
    # registry letting it through quietly
    add_extension(is_foo, override=True)
    assert_that("foo").is_foo()
    with pytest.raises(AssertionError) as exc_info:
        assert_that("FOO").is_foo()
    assert_that(str(exc_info.value)).is_equal_to("Expected <FOO> to be foo, but was not.")


def dupe2():
    def is_foo(self):
        if self.val != "FOO":
            return self.error(f"Expected <{self.val}> to be FOO, but was not.")
        return self

    add_extension(is_foo, override=True)
    assert_that("FOO").is_foo()
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_foo()
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to be FOO, but was not.")


def test_dupe_extensions():
    dupe1()
    dupe2()
    dupe1()


def test_a_second_implementation_under_one_name_is_refused():
    # the hazard is two different functions claiming one name, which used to end with whichever was
    # imported last and no way to tell
    def already_there(self):
        return self

    def already_there_again(self):
        return self.error("the other one")

    already_there_again.__name__ = "already_there"

    add_extension(already_there)
    try:
        with pytest.raises(ValueError, match="already been added"):
            add_extension(already_there_again)
        add_extension(already_there_again, override=True)
    finally:
        remove_extension(already_there)


def test_a_function_rebuilt_by_a_fixture_is_not_a_clash():
    # the documented way to share extensions is a module-scoped conftest fixture, and a fixture that
    # defines its assertion inline hands over a NEW function object every time it runs. identity
    # would call the second module a clash; the code object is what stays the same across rebuilds
    def build():
        def steady(self):
            return self

        return steady

    first, second = build(), build()
    assert first is not second
    add_extension(first)
    try:
        add_extension(second)
    finally:
        remove_extension(first)


def test_a_callable_object_falls_back_to_identity():
    # an instance with __call__ has no code object to compare, so the strictest answer available is
    # whether it is literally the same object
    class Callable:
        __name__ = "instance_extension"

        def __call__(self, builder):
            return builder

    first, second = Callable(), Callable()
    add_extension(first)
    try:
        add_extension(first)
        with pytest.raises(ValueError, match="already been added"):
            add_extension(second)
    finally:
        remove_extension(first)


def test_a_callable_without_a_usable_name_is_refused():
    # a callable object's __name__ is whatever it says it is, and the registry keys on it. a lambda
    # gives "<lambda>", which is not something anyone can then call on the builder
    with pytest.raises(ValueError, match="valid Python identifier"):
        add_extension(lambda self: self)


def test_replacing_a_built_in_assertion_has_to_be_deliberate():
    # this used to go through in silence, and every later call to the core assertion got the
    # extension's message instead. the project's own suite was doing it by accident
    def is_type_of(self, other):
        return self.error("shadowed")

    with pytest.raises(ValueError, match="already defined on the assertion builder"):
        add_extension(is_type_of)


class TestExtensionBindingMechanics:
    """Plain functions bind to the extension host class once; exotic callables fall back to
    per-instance grafting; removal never damages the original API."""

    def test_extension_shadowing_a_builtin_method_is_restored_on_removal(self):
        def is_true(self):
            return self.error("shadowed is_true")

        add_extension(is_true, override=True)  # deliberate: the point of this test is the restore
        try:
            with pytest.raises(AssertionError, match="shadowed is_true"):
                assert_that(True).is_true()
        finally:
            remove_extension(is_true)
        assert_that(True).is_true()

    def test_callable_object_extension_uses_per_instance_fallback(self):
        class IsBar:
            __name__ = "is_bar"

            def __call__(self, builder):
                if builder.val != "bar":
                    return builder.error(f"Expected <{builder.val}> to be bar, but was not.")
                return builder

        extension = IsBar()
        add_extension(extension)
        try:
            assert_that("bar").is_bar()
            with pytest.raises(AssertionError, match="to be bar"):
                assert_that("baz").is_bar()
        finally:
            remove_extension(extension)
        with pytest.raises(AttributeError):
            assert_that("bar").is_bar()

    def test_extension_becomes_visible_to_builders_created_before_registration(self):
        builder = assert_that("foo")

        def is_visible_late(self):
            return self

        add_extension(is_visible_late)
        try:
            builder.is_visible_late()
        finally:
            remove_extension(is_visible_late)

    def test_removed_extension_disappears_from_live_builders(self):
        def is_transient(self):
            return self

        add_extension(is_transient)
        builder = assert_that("foo")
        builder.is_transient()
        remove_extension(is_transient)
        with pytest.raises(AttributeError):
            builder.is_transient()

    def test_builder_stays_an_assertion_builder_instance(self):
        from assertpy2.assertpy import AssertionBuilder

        assert_that(assert_that(1)).is_instance_of(AssertionBuilder)
