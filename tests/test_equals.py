import collections
import dataclasses

import pytest

from assertpy2 import assert_that
from assertpy2._compare import _find_ambiguous_operand


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


def test_is_equal_type_collision_annotates_types():
    # when the two reprs collide, the message tags each with its type so it does not read as "1 != 1"
    with pytest.raises(AssertionError) as exc_info:
        assert_that("1").is_equal_to(1)
    assert_that(str(exc_info.value)).is_equal_to("Expected <1:str> to be equal to <1:int>, but was not.")


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


class _RaisingEq:
    """Non-array value whose ``==`` raises, to pin that only array-caused errors are converted."""

    def __eq__(self, other):
        raise ValueError("raising eq")

    __hash__ = object.__hash__


@dataclasses.dataclass
class _ArrayField:
    payload: object


@dataclasses.dataclass
class _EmptyDataclass:
    pass


class _ArrayModel:
    """Duck pydantic model: ``__eq__`` compares dumps, so an array field breaks it like real pydantic."""

    def __init__(self, payload):
        self.payload = payload

    def model_dump(self):
        return {"payload": self.payload}

    def __eq__(self, other):
        return self.model_dump() == other.model_dump()

    __hash__ = object.__hash__


class TestNestedArrayLikeEqualityGuard:
    """The array/frame-like guard applies at any nesting depth, not only to the top-level operands."""

    def test_array_like_as_dict_value(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": _FakeArray()}).is_equal_to({"a": _FakeArray()})
        assert_that(str(exc_info.value)).contains("is_equal_to").contains("_FakeArray").contains("element-wise")

    def test_array_like_in_list_inside_dict(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": [_FakeArray()]}).is_equal_to({"a": [_FakeArray()]})
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_in_top_level_list(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that([_FakeArray()]).is_equal_to([_FakeArray()])
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_in_namedtuple(self):
        point = collections.namedtuple("point", ["payload"])
        with pytest.raises(TypeError) as exc_info:
            assert_that(point(_FakeArray())).is_equal_to(point(_FakeArray()))
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_as_dataclass_field(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_ArrayField(_FakeArray())).is_equal_to(_ArrayField(_FakeArray()))
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_as_model_field(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_ArrayModel(_FakeArray())).is_equal_to(_ArrayModel(_FakeArray()))
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_with_ignored_sibling_key(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": _FakeArray(), "b": 2}).is_equal_to({"a": _FakeArray(), "b": 3}, ignore="b")
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_with_tolerance(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": _FakeArray(), "x": 1.0}).is_equal_to({"a": _FakeArray(), "x": 1.0}, tolerance=0.1)
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_reached_only_in_diff_phase(self):
        # differing key counts make the boolean check pass cleanly; the diff walk hits the array
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": _FakeArray(), "b": 1}).is_equal_to({"a": _FakeArray()})
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_non_array_comparison_error_propagates_unchanged(self):
        with pytest.raises(ValueError, match="raising eq"):
            assert_that({"a": _RaisingEq()}).is_equal_to({"a": _RaisingEq()})

    def test_is_not_equal_to_array_like_as_dict_value(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": _FakeArray()}).is_not_equal_to({"a": _FakeArray()})
        assert_that(str(exc_info.value)).contains("is_not_equal_to").contains("_FakeArray")

    def test_is_not_equal_to_non_array_error_propagates_unchanged(self):
        with pytest.raises(ValueError, match="raising eq"):
            assert_that({"a": _RaisingEq()}).is_not_equal_to({"a": _RaisingEq()})

    def test_numpy_array_nested_in_dict_raises_clear_error(self):
        numpy = pytest.importorskip("numpy")
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": numpy.array([1, 2])}).is_equal_to({"a": numpy.array([1, 2])})
        assert_that(str(exc_info.value)).contains("element-wise")


class TestFindAmbiguousOperand:
    """Direct coverage of the error-path search over shapes a crashed comparison cannot produce itself."""

    def test_shared_cyclic_sibling_is_skipped(self):
        loop = {}
        loop["self"] = loop
        arr = _FakeArray()
        found = _find_ambiguous_operand({"loop": loop, "arr": arr}, {"loop": loop, "arr": _FakeArray()})
        assert_that(found).is_same_as(arr)

    def test_key_without_counterpart_is_skipped(self):
        arr = _FakeArray()
        found = _find_ambiguous_operand({"only": 1, "arr": arr}, {"arr": _FakeArray(), "other": 2})
        assert_that(found).is_same_as(arr)

    def test_dataclass_field_missing_on_expected(self):
        arr = _FakeArray()
        found = _find_ambiguous_operand(_ArrayField(arr), _EmptyDataclass())
        assert_that(found).is_same_as(arr)

    def test_dataclass_without_array_returns_none(self):
        assert_that(_find_ambiguous_operand(_ArrayField(1), _ArrayField(2))).is_none()

    def test_list_without_array_returns_none(self):
        assert_that(_find_ambiguous_operand([_RaisingEq()], [_RaisingEq()])).is_none()

    def test_plain_scalars_return_none(self):
        assert_that(_find_ambiguous_operand(1, 2)).is_none()
