"""Static typing tests for the ``assert_that`` overloads.

These are verified by type checkers (ty, Pyright, Mypy), not at runtime: each ``assert_type`` pins the
overload resolution to the documented type-specific Protocol, so a regression that broadens or changes a
return type fails the type check. The body lives under ``TYPE_CHECKING`` because the Protocols in
:mod:`assertpy2._typing` exist only for static analysis and are absent at runtime; Pytest imports this
module without executing the block.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import datetime
    import pathlib

    from typing_extensions import assert_type

    from assertpy2 import assert_that
    from assertpy2._typing import (
        _BytesAssertion,
        _CallableAssertion,
        _DateAssertion,
        _DictAssertion,
        _IterableAssertion,
        _NumericAssertion,
        _PathAssertion,
        _StringAssertion,
    )
    from assertpy2.assertpy import AssertionBuilder

    # Each call is a static assertion: it fails type checking if assert_that stops returning the
    # documented Protocol for that value type. The mapping mirrors the table in docs/type-safety.md.
    assert_type(assert_that("text"), _StringAssertion)
    assert_type(assert_that(42), _NumericAssertion)
    assert_type(assert_that(3.14), _NumericAssertion)
    assert_type(assert_that(complex(1, 2)), _NumericAssertion)
    assert_type(assert_that({"key": "value"}), _DictAssertion)
    assert_type(assert_that(["a", "b"]), _IterableAssertion)
    assert_type(assert_that(("a", "b")), _IterableAssertion)
    assert_type(assert_that({"a", "b"}), _IterableAssertion)
    assert_type(assert_that(frozenset({"a"})), _IterableAssertion)
    assert_type(assert_that(datetime.date(2026, 1, 1)), _DateAssertion)
    assert_type(assert_that(datetime.datetime(2026, 1, 1, 12, 0)), _DateAssertion)
    assert_type(assert_that(pathlib.Path("/tmp")), _PathAssertion)
    assert_type(assert_that(b"raw"), _BytesAssertion)
    assert_type(assert_that(bytearray(b"raw")), _BytesAssertion)
    assert_type(assert_that(len), _CallableAssertion)
    assert_type(assert_that(object()), AssertionBuilder)
