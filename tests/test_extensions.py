import numbers

from assertpy2 import add_extension, assert_that, fail, remove_extension


def is_even(self):
    if not isinstance(self.val, numbers.Integral):
        raise TypeError("val must be an integer")
    if self.val % 2 != 0:
        return self.error(f"Expected <{self.val}> to be even, but was not.")
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


add_extension(is_even)
add_extension(is_multiple_of)
add_extension(is_factor_of)


def test_is_even_extension():
    assert_that(124).is_even()
    assert_that(124).is_type_of(int).is_even().is_greater_than(123).is_less_than(125).is_equal_to(124)


def test_is_even_extension_failure():
    try:
        assert_that(123).is_even()
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected <123> to be even, but was not.")


def test_is_even_extension_failure_not_callable():
    try:
        add_extension("foo")
        fail("should have raised error")
    except TypeError as ex:
        assert_that(str(ex)).is_equal_to("func must be callable")


def test_is_even_extension_failure_not_integer():
    try:
        assert_that(124.0).is_even()
        fail("should have raised error")
    except TypeError as ex:
        assert_that(str(ex)).is_equal_to("val must be an integer")


def test_is_multiple_of_extension():
    assert_that(24).is_multiple_of(1)
    assert_that(24).is_multiple_of(2)
    assert_that(24).is_multiple_of(3)
    assert_that(24).is_multiple_of(4)
    assert_that(24).is_multiple_of(6)
    assert_that(24).is_multiple_of(8)
    assert_that(24).is_multiple_of(12)
    assert_that(24).is_multiple_of(24)
    assert_that(124).is_type_of(int).is_even().is_multiple_of(31).is_equal_to(124)


def test_is_multiple_of_extension_failure():
    try:
        assert_that(24).is_multiple_of(5)
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected <24> to be multiple of <5>, but was not.")


def test_is_multiple_of_extension_failure_bad_val():
    try:
        assert_that(24.0).is_multiple_of(5)
        fail("should have raised error")
    except TypeError as ex:
        assert_that(str(ex)).is_equal_to("val must be a positive integer")


def test_is_multiple_of_extension_failure_negative_val():
    try:
        assert_that(-24).is_multiple_of(6)
        fail("should have raised error")
    except TypeError as ex:
        assert_that(str(ex)).is_equal_to("val must be a positive integer")


def test_is_multiple_of_extension_failure_bad_arg():
    try:
        assert_that(24).is_multiple_of("foo")
        fail("should have raised error")
    except TypeError as ex:
        assert_that(str(ex)).is_equal_to("given arg must be a positive integer")


def test_is_multiple_of_extension_failure_negative_arg():
    try:
        assert_that(24).is_multiple_of(-6)
        fail("should have raised error")
    except TypeError as ex:
        assert_that(str(ex)).is_equal_to("given arg must be a positive integer")


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
    try:
        assert_that(5).is_factor_of(24)
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected <5> to be factor of <24>, but was not.")


def test_call_missing_extension():
    def is_missing():
        pass

    try:
        remove_extension(is_even)
        remove_extension(is_multiple_of)
        remove_extension(is_factor_of)
        remove_extension(is_missing)
        assert_that(24).is_multiple_of(6)
        fail("should have raised error")
    except AttributeError as ex:
        assert_that(str(ex)).is_equal_to("assertpy has no assertion <is_multiple_of()>")


def test_remove_bad_extension():
    try:
        remove_extension("foo")
        fail("should have raised error")
    except TypeError as ex:
        assert_that(str(ex)).is_equal_to("func must be callable")


def is_foo(self):
    if self.val != "foo":
        return self.error(f"Expected <{self.val}> to be foo, but was not.")
    return self


def dupe1():
    add_extension(is_foo)
    assert_that("foo").is_foo()
    try:
        assert_that("FOO").is_foo()
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected <FOO> to be foo, but was not.")


def dupe2():
    def is_foo(self):
        if self.val != "FOO":
            return self.error(f"Expected <{self.val}> to be FOO, but was not.")
        return self

    add_extension(is_foo)
    assert_that("FOO").is_foo()
    try:
        assert_that("foo").is_foo()
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected <foo> to be FOO, but was not.")


def test_dupe_extensions():
    dupe1()
    dupe2()
    dupe1()
