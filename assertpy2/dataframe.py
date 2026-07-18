"""Optional fluent assertions for data-science containers (pandas / polars / numpy).

This is an *integration* layer in the same spirit as the Allure and Behave adapters: each library is its
own optional extra (``pip install assertpy2[pandas]`` / ``[polars]`` / ``[numpy]``, or ``[data]`` for all
three), imported lazily by name, so the core stays free of runtime dependencies.  Comparison
**semantics** are delegated entirely to each library's own testing
utilities (``assert_frame_equal`` / ``assert_series_equal`` / ``assert_array_equal`` / ``assert_allclose``),
so dtype, tolerance and NaN handling match the library exactly.  This layer only adds the fluent entry
point and routes failures through the standard assertpy2 error model.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from ._engine._mixin_base import _MixinBase

if TYPE_CHECKING:
    from ._engine._compat import Self

__tracebackhide__ = True

_FRAME_ROOTS = ("pandas", "polars")


def _ensure_module(name: str) -> Any:
    """Import optional library *name* by string, or raise a clear ImportError pointing at its extra."""
    try:
        return importlib.import_module(name)
    except ImportError:
        raise ImportError(
            f"{name} is required for these assertions. Install it with: pip install assertpy2[{name}]"
        ) from None


def _load(root: str) -> tuple[Any, Any]:
    """Return ``(library, library.testing)`` for *root* (``pandas``/``polars``/``numpy``)."""
    library = _ensure_module(root)
    return library, importlib.import_module(f"{root}.testing")


class DataFrameMixin(_MixinBase):
    """Fluent assertions for pandas/polars frames and numpy arrays (optional ``[data]`` extra)."""

    def is_frame_equal(self, expected: object, **options: Any) -> Self:
        """Asserts that a pandas/polars ``DataFrame`` or ``Series`` equals *expected*.

        Delegates to the owning library's own ``assert_frame_equal`` / ``assert_series_equal``, so all
        comparison semantics (dtype strictness, row/column order, tolerance, categoricals, ...) are the
        library's.  Any keyword options are passed straight through.

        Args:
            expected: the expected frame/series (same library as val)
            **options: keyword options forwarded to the library's ``assert_frame_equal`` /
                ``assert_series_equal`` (e.g. ``check_dtype=False``, ``check_exact=False``, ``rtol=1e-3``)

        Examples:
            Usage:

                import pandas as pd

                assert_that(pd.DataFrame({"a": [1, 2]})).is_frame_equal(pd.DataFrame({"a": [1, 2]}))
                assert_that(actual).is_frame_equal(expected, check_dtype=False)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the frames/series are not equal (carrying the library's own diff message)
            TypeError: if val is not a pandas or polars ``DataFrame``/``Series``
            ImportError: if the owning library is not installed
        """
        actual = self.val
        # walk the MRO so a user subclass (whose own __module__ is its app, not pandas/polars) still
        # resolves to the owning library through its DataFrame/Series base
        root = next(
            (
                base.__module__.split(".", 1)[0]
                for base in type(actual).__mro__
                if base.__module__.split(".", 1)[0] in _FRAME_ROOTS
            ),
            type(actual).__module__.split(".", 1)[0],
        )
        if root not in _FRAME_ROOTS:
            raise TypeError(
                f"is_frame_equal() expects a pandas or polars DataFrame/Series, but was <{type(actual).__name__}>."
            )
        library, testing = _load(root)
        class_name = type(actual).__name__
        # isinstance handles real subclasses; the class-name check handles duck-typed frames (a test may
        # inject a fake library, so the value is not an instance of that fake DataFrame/Series class)
        if isinstance(actual, library.Series) or class_name == "Series":
            assert_equal, label = testing.assert_series_equal, "Series"
        elif isinstance(actual, library.DataFrame) or class_name == "DataFrame":
            assert_equal, label = testing.assert_frame_equal, "DataFrame"
        else:
            # a pandas/polars object that is neither a DataFrame nor a Series (Index, Categorical, ...)
            raise TypeError(
                f"is_frame_equal() expects a pandas or polars DataFrame/Series, but was <{type(actual).__name__}>."
            )
        try:
            assert_equal(actual, expected, **options)
        except AssertionError as exc:
            return self.error(f"Expected the {label} to equal the expected one, but they differ:\n{exc}")
        return self

    def is_array_equal(self, expected: object, **options: Any) -> Self:
        """Asserts that val equals *expected* element-wise, via numpy's ``assert_array_equal``.

        Works on any array-likes numpy can coerce (``ndarray``, nested lists, ...); shape and every
        element must match exactly (with ``NaN`` treated as equal, per numpy).

        Args:
            expected: the expected array-like
            **options: keyword options forwarded to numpy's ``assert_array_equal``
                (e.g. ``strict=True``, ``err_msg="..."``)

        Examples:
            Usage:

                import numpy as np

                assert_that(np.array([1, 2, 3])).is_array_equal(np.array([1, 2, 3]))
                assert_that(np.array([1, 2, 3])).is_array_equal(np.array([1, 2, 3]), strict=True)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the arrays are not equal (carrying numpy's own diff message)
            ImportError: if numpy is not installed
        """
        _, testing = _load("numpy")
        try:
            testing.assert_array_equal(self.val, expected, **options)
        except AssertionError as exc:
            return self.error(f"Expected the arrays to be equal, but they differ:\n{exc}")
        return self

    def is_array_close_to(
        self, expected: object, *, rtol: float = 1e-05, atol: float = 1e-08, equal_nan: bool = False, **options: Any
    ) -> Self:
        """Asserts that val is element-wise close to *expected*, via numpy's ``assert_allclose``.

        The float-tolerant counterpart to [`is_array_equal()`][assertpy2.dataframe.DataFrameMixin.is_array_equal],
        for comparing computed arrays.

        Args:
            expected: the expected array-like
            rtol: relative tolerance (numpy default ``1e-05``)
            atol: absolute tolerance (numpy default ``1e-08``)
            equal_nan: whether ``NaN`` in the same position compares equal
            **options: further keyword options forwarded to numpy's ``assert_allclose``
                (e.g. ``err_msg="..."``, ``strict=True``)

        Examples:
            Usage:

                import numpy as np

                assert_that(np.array([1.0, 2.0])).is_array_close_to(np.array([1.0, 2.0000001]))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the arrays are not close (carrying numpy's own diff message)
            ImportError: if numpy is not installed
        """
        _, testing = _load("numpy")
        try:
            testing.assert_allclose(self.val, expected, rtol=rtol, atol=atol, equal_nan=equal_nan, **options)
        except AssertionError as exc:
            return self.error(f"Expected the arrays to be close, but they differ:\n{exc}")
        return self
