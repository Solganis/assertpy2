import contextlib
import sys
import types
from unittest.mock import patch

import pytest

from assertpy2 import assert_that


@contextlib.contextmanager
def _fake_frame_lib(root, *, fail):
    """Inject a fake pandas/polars-like module so the delegation is covered without the real library.

    The fake ``DataFrame``/``Series`` classes carry ``__module__ == root`` (what the mixin routes on), and
    the fake ``testing.assert_*`` either pass or raise, echoing options so they can be asserted on.
    """
    series = type("Series", (), {"__module__": root})
    dataframe = type("DataFrame", (), {"__module__": root})
    library = types.ModuleType(root)
    testing = types.ModuleType(f"{root}.testing")

    def assert_frame_equal(actual, expected, **options):
        if fail:
            raise AssertionError(f"{root} frames differ; options={options}")

    def assert_series_equal(actual, expected, **options):
        if fail:
            raise AssertionError(f"{root} series differ")

    library.Series = series
    library.DataFrame = dataframe
    testing.assert_frame_equal = assert_frame_equal
    testing.assert_series_equal = assert_series_equal
    with patch.dict(sys.modules, {root: library, f"{root}.testing": testing}):
        yield series, dataframe


@contextlib.contextmanager
def _fake_numpy(*, fail):
    """Inject a fake numpy.testing so array assertions are covered without real numpy."""
    library = types.ModuleType("numpy")
    testing = types.ModuleType("numpy.testing")

    def assert_array_equal(actual, expected):
        if fail:
            raise AssertionError("numpy arrays differ")

    def assert_allclose(actual, expected, *, rtol, atol, equal_nan):
        if fail:
            raise AssertionError(f"numpy not close; rtol={rtol} atol={atol} equal_nan={equal_nan}")

    testing.assert_array_equal = assert_array_equal
    testing.assert_allclose = assert_allclose
    with patch.dict(sys.modules, {"numpy": library, "numpy.testing": testing}):
        yield


class TestIsFrameEqualDuckTyped:
    def test_non_frame_value_raises_type_error(self):
        with pytest.raises(TypeError, match="pandas or polars"):
            assert_that(5).is_frame_equal(5)

    def test_pandas_dataframe_equal_passes(self):
        with _fake_frame_lib("pandas", fail=False) as (_, dataframe):
            assert_that(dataframe()).is_frame_equal(dataframe())

    def test_pandas_dataframe_not_equal_fails(self):
        with (
            _fake_frame_lib("pandas", fail=True) as (_, dataframe),
            pytest.raises(AssertionError, match="DataFrame to equal"),
        ):
            assert_that(dataframe()).is_frame_equal(dataframe())

    def test_pandas_series_branch(self):
        with (
            _fake_frame_lib("pandas", fail=True) as (series, _),
            pytest.raises(AssertionError, match="Series to equal"),
        ):
            assert_that(series()).is_frame_equal(series())

    def test_polars_dataframe_branch(self):
        with (
            _fake_frame_lib("polars", fail=True) as (_, dataframe),
            pytest.raises(AssertionError, match="DataFrame to equal"),
        ):
            assert_that(dataframe()).is_frame_equal(dataframe())

    def test_options_are_passed_through(self):
        with (
            _fake_frame_lib("pandas", fail=True) as (_, dataframe),
            pytest.raises(AssertionError, match="check_dtype"),
        ):
            assert_that(dataframe()).is_frame_equal(dataframe(), check_dtype=False)

    def test_root_extracted_from_dotted_module(self):
        # Real frames live in dotted modules ("pandas.core.frame"); the root must be the first segment.
        # `split(".", 1)[0]` -> `[1]` or limit `0` would mis-extract the root and wrongly raise TypeError.
        with _fake_frame_lib("pandas", fail=False):
            frame = type("DataFrame", (), {"__module__": "pandas.core.frame"})()
            assert_that(frame).is_frame_equal(frame)


class TestArrayAssertionsDuckTyped:
    def test_is_array_equal_passes(self):
        with _fake_numpy(fail=False):
            assert_that([1, 2, 3]).is_array_equal([1, 2, 3])

    def test_is_array_equal_fails(self):
        with _fake_numpy(fail=True), pytest.raises(AssertionError, match="arrays to be equal"):
            assert_that([1, 2, 3]).is_array_equal([1, 2, 9])

    def test_is_array_close_to_passes(self):
        with _fake_numpy(fail=False):
            assert_that([1.0]).is_array_close_to([1.0], rtol=1e-3)

    def test_is_array_close_to_fails(self):
        with _fake_numpy(fail=True), pytest.raises(AssertionError, match="arrays to be close"):
            assert_that([1.0]).is_array_close_to([2.0])

    def test_is_array_close_to_forwards_default_tolerances(self):
        # The defaults must match numpy's own (rtol=1e-05, atol=1e-08, equal_nan=False) and be forwarded
        # unchanged; mutating any default literal would silently use a different tolerance.
        with _fake_numpy(fail=True), pytest.raises(AssertionError, match="rtol=1e-05 atol=1e-08 equal_nan=False"):
            assert_that([1.0]).is_array_close_to([2.0])


class TestMissingLibraries:
    def test_pandas_missing_raises_clear_importerror(self):
        frame = type("DataFrame", (), {"__module__": "pandas"})()
        with patch.dict(sys.modules, {"pandas": None}), pytest.raises(ImportError, match="pandas is required"):
            assert_that(frame).is_frame_equal(frame)

    def test_numpy_missing_raises_clear_importerror(self):
        with patch.dict(sys.modules, {"numpy": None}), pytest.raises(ImportError, match="numpy is required"):
            assert_that([1, 2]).is_array_equal([1, 2])


class TestRealLibraries:
    """Validate the real integration; skipped when the optional library is absent (CI without [data])."""

    def test_pandas_frame_equal_and_diff(self):
        pandas = pytest.importorskip("pandas")
        assert_that(pandas.DataFrame({"a": [1, 2]})).is_frame_equal(pandas.DataFrame({"a": [1, 2]}))
        with pytest.raises(AssertionError):
            assert_that(pandas.DataFrame({"a": [1, 2]})).is_frame_equal(pandas.DataFrame({"a": [1, 9]}))

    def test_pandas_options_passthrough(self):
        pandas = pytest.importorskip("pandas")
        actual = pandas.DataFrame({"a": [1, 2]}).astype("int64")
        expected = pandas.DataFrame({"a": [1, 2]}).astype("int32")
        assert_that(actual).is_frame_equal(expected, check_dtype=False)
        with pytest.raises(AssertionError):
            assert_that(actual).is_frame_equal(expected)

    def test_pandas_series(self):
        pandas = pytest.importorskip("pandas")
        assert_that(pandas.Series([1, 2, 3])).is_frame_equal(pandas.Series([1, 2, 3]))

    def test_polars_frame_equal_and_diff(self):
        polars = pytest.importorskip("polars")
        assert_that(polars.DataFrame({"a": [1, 2]})).is_frame_equal(polars.DataFrame({"a": [1, 2]}))
        with pytest.raises(AssertionError):
            assert_that(polars.DataFrame({"a": [1, 2]})).is_frame_equal(polars.DataFrame({"a": [1, 9]}))

    def test_numpy_array_equal(self):
        numpy = pytest.importorskip("numpy")
        assert_that(numpy.array([1, 2, 3])).is_array_equal(numpy.array([1, 2, 3]))
        with pytest.raises(AssertionError):
            assert_that(numpy.array([1, 2, 3])).is_array_equal(numpy.array([1, 2, 9]))

    def test_numpy_array_close_to(self):
        numpy = pytest.importorskip("numpy")
        assert_that(numpy.array([1.0, 2.0])).is_array_close_to(numpy.array([1.0, 2.0000001]))
        with pytest.raises(AssertionError):
            assert_that(numpy.array([1.0, 2.0])).is_array_close_to(numpy.array([1.0, 2.5]))
