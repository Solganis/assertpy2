import datetime
import pathlib

from assertpy2 import assert_that
from assertpy2.assertpy import AssertionBuilder


class TestOverloadsRuntimeBehavior:
    def test_str_returns_builder(self):
        result = assert_that("hello")
        assert isinstance(result, AssertionBuilder)

    def test_int_returns_builder(self):
        result = assert_that(42)
        assert isinstance(result, AssertionBuilder)

    def test_float_returns_builder(self):
        result = assert_that(3.14)
        assert isinstance(result, AssertionBuilder)

    def test_dict_returns_builder(self):
        result = assert_that({"a": 1})
        assert isinstance(result, AssertionBuilder)

    def test_list_returns_builder(self):
        result = assert_that([1, 2, 3])
        assert isinstance(result, AssertionBuilder)

    def test_tuple_returns_builder(self):
        result = assert_that((1, 2))
        assert isinstance(result, AssertionBuilder)

    def test_set_returns_builder(self):
        result = assert_that({1, 2})
        assert isinstance(result, AssertionBuilder)

    def test_date_returns_builder(self):
        result = assert_that(datetime.date.today())
        assert isinstance(result, AssertionBuilder)

    def test_datetime_returns_builder(self):
        result = assert_that(datetime.datetime.now())
        assert isinstance(result, AssertionBuilder)

    def test_path_returns_builder(self):
        result = assert_that(pathlib.Path("."))
        assert isinstance(result, AssertionBuilder)

    def test_callable_returns_builder(self):
        result = assert_that(lambda: 42)
        assert isinstance(result, AssertionBuilder)

    def test_none_returns_builder(self):
        result = assert_that(None)
        assert isinstance(result, AssertionBuilder)

    def test_bool_returns_builder(self):
        result = assert_that(True)
        assert isinstance(result, AssertionBuilder)

    def test_with_description(self):
        result = assert_that(42, "my description")
        assert isinstance(result, AssertionBuilder)
        assert result.description == "my description"


class TestTypingModuleImport:
    def test_typing_module_importable(self):
        import assertpy2._typing

        assert assertpy2._typing is not None
