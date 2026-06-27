import pytest

from assertpy2 import assert_that


def test_is_equal():
    assert_that("foo").is_equal_to("foo")
    assert_that(123).is_equal_to(123)
    assert_that(0.11).is_equal_to(0.11)
    assert_that(["a", "b"]).is_equal_to(["a", "b"])
    assert_that((1, 2, 3)).is_equal_to((1, 2, 3))
    assert_that(1 == 1).is_equal_to(True)
    assert_that(1 == 2).is_equal_to(False)
    assert_that({"a", "b"}).is_equal_to({"b", "a"})
    assert_that({"a": 1, "b": 2}).is_equal_to({"b": 2, "a": 1})


def test_is_equal_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_equal_to("bar")
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to be equal to <bar>, but was not.")


def test_is_equal_int_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_equal_to(234)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be equal to <234>, but was not.")


def test_is_equal_list_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b"]).is_equal_to(["a", "b", "c"])
    assert_that(str(exc_info.value)).is_equal_to("Expected <['a', 'b']> to be equal to <['a', 'b', 'c']>, but was not.")


def test_is_not_equal():
    assert_that("foo").is_not_equal_to("bar")
    assert_that(123).is_not_equal_to(234)
    assert_that(0.11).is_not_equal_to(0.12)
    assert_that(["a", "b"]).is_not_equal_to(["a", "x"])
    assert_that(["a", "b"]).is_not_equal_to(["a"])
    assert_that(["a", "b"]).is_not_equal_to(["a", "b", "c"])
    assert_that((1, 2, 3)).is_not_equal_to((1, 2))
    assert_that(1 == 1).is_not_equal_to(False)
    assert_that(1 == 2).is_not_equal_to(True)
    assert_that({"a", "b"}).is_not_equal_to({"a"})
    assert_that({"a": 1, "b": 2}).is_not_equal_to({"a": 1, "b": 3})
    assert_that({"a": 1, "b": 2}).is_not_equal_to({"a": 1, "c": 2})


def test_is_not_equal_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_not_equal_to("foo")
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to be not equal to <foo>, but was.")


def test_is_not_equal_int_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_not_equal_to(123)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be not equal to <123>, but was.")


def test_is_not_equal_list_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b"]).is_not_equal_to(["a", "b"])
    assert_that(str(exc_info.value)).is_equal_to("Expected <['a', 'b']> to be not equal to <['a', 'b']>, but was.")


class _FakeArray:
    """Array-like: has ``__array__`` and an element-wise ``==`` whose truth value is ambiguous."""

    def __array__(self):
        return None

    def __eq__(self, other):
        return self  # an element-wise result stand-in, not a bool

    def __bool__(self):
        raise ValueError("the truth value of a _FakeArray is ambiguous")

    __hash__ = object.__hash__


class _FakeScalarArray:
    """Array-like but scalar: has ``__array__`` yet a truth-testable ``==`` (like a 0-d array/scalar)."""

    def __array__(self):
        return None

    def __eq__(self, other):
        return isinstance(other, _FakeScalarArray)

    __hash__ = object.__hash__


class TestArrayLikeEqualityGuard:
    """is_equal_to/is_not_equal_to reject element-wise array/frame-likes with a clear, actionable error."""

    def test_is_equal_to_rejects_array_like(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_FakeArray()).is_equal_to(_FakeArray())
        assert_that(str(exc_info.value)).contains("is_equal_to").contains("_FakeArray").contains("element-wise")

    def test_is_not_equal_to_rejects_array_like(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_FakeArray()).is_not_equal_to(_FakeArray())
        assert_that(str(exc_info.value)).contains("is_not_equal_to").contains("_FakeArray")

    def test_array_like_as_expected_operand_is_rejected(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(5).is_equal_to(_FakeArray())
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_scalar_array_like_is_not_rejected(self):
        # has __array__ but a truth-testable ==, so it must compare normally (no regression)
        assert_that(_FakeScalarArray()).is_equal_to(_FakeScalarArray())
        with pytest.raises(AssertionError):
            assert_that(_FakeScalarArray()).is_not_equal_to(_FakeScalarArray())

    def test_numpy_array_raises_clear_error(self):
        numpy = pytest.importorskip("numpy")
        with pytest.raises(TypeError) as exc_info:
            assert_that(numpy.array([1, 2, 3])).is_equal_to(numpy.array([1, 2, 3]))
        assert_that(str(exc_info.value)).contains("element-wise")

    def test_pandas_dataframe_raises_clear_error(self):
        pandas = pytest.importorskip("pandas")
        frame = pandas.DataFrame({"a": [1, 2]})
        with pytest.raises(TypeError) as exc_info:
            assert_that(frame).is_equal_to(frame)
        assert_that(str(exc_info.value)).contains("element-wise")

    def test_polars_dataframe_raises_clear_error(self):
        polars = pytest.importorskip("polars")
        frame = polars.DataFrame({"a": [1, 2]})
        with pytest.raises(TypeError) as exc_info:
            assert_that(frame).is_equal_to(frame)
        assert_that(str(exc_info.value)).contains("element-wise")
