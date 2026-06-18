import pytest

from assertpy2 import assert_that


class Person:
    def __init__(self, first_name, last_name, shoe_size):
        self.first_name = first_name
        self.last_name = last_name
        self.shoe_size = shoe_size

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}"

    def say_hello(self):
        return f"Hello, {self.first_name}!"

    def say_goodbye(self, target):
        return f"Bye, {target}!"


fred = Person("Fred", "Smith", 12)


def test_dynamic_assertion():
    assert_that(fred).is_type_of(Person)
    assert_that(fred).is_instance_of(object)

    assert_that(fred.first_name).is_equal_to("Fred")
    assert_that(fred.last_name).is_equal_to("Smith")
    assert_that(fred.shoe_size).is_equal_to(12)

    assert_that(fred).has_first_name("Fred")
    assert_that(fred).has_last_name("Smith")
    assert_that(fred).has_shoe_size(12)


def test_dynamic_assertion_on_property():
    assert_that(fred.name).is_equal_to("Fred Smith")
    assert_that(fred).has_name("Fred Smith")


def test_dynamic_assertion_on_method():
    assert_that(fred.say_hello()).is_equal_to("Hello, Fred!")
    assert_that(fred).has_say_hello("Hello, Fred!")


def test_dynamic_assertion_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred).has_first_name("Joe")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <Fred> to be equal to <Joe> on attribute <first_name>, but was not."
    )


def test_dynamic_assertion_bad_name_failure():
    with pytest.raises(AttributeError) as exc_info:
        assert_that(fred).foo()
    assert_that(str(exc_info.value)).is_equal_to("assertpy has no assertion <foo()>")


def test_dynamic_assertion_unknown_attribute_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred).has_foo()
    assert_that(str(exc_info.value)).is_equal_to("Expected attribute <foo>, but val has no attribute <foo>.")


def test_dynamic_assertion_no_args_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(fred).has_first_name()
    assert_that(str(exc_info.value)).is_equal_to("assertion <has_first_name()> takes exactly 1 argument (0 given)")


def test_dynamic_assertion_too_many_args_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(fred).has_first_name("Fred", "Joe")
    assert_that(str(exc_info.value)).is_equal_to("assertion <has_first_name()> takes exactly 1 argument (2 given)")


def test_dynamic_assertion_on_method_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(fred).has_say_goodbye("Foo")
    assert_that(str(exc_info.value)).contains("val does not have zero-arg method <say_goodbye()>")


def test_chaining():
    assert_that(fred).has_first_name("Fred").has_last_name("Smith").has_shoe_size(12)
