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
    from collections.abc import Callable
    from typing import Any, cast

    from typing_extensions import TypeIs, assert_type

    from assertpy2 import assert_conforms, assert_that
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
    from assertpy2.async_assertions import AsyncAssertionBuilder, SyncAssertionBuilder

    # Each call is a static assertion: it fails type checking if assert_that stops returning the
    # documented Protocol for that value type. The mapping mirrors the table in docs/type-safety.md.
    assert_type(assert_that("text"), _StringAssertion)
    assert_type(assert_that(42), _NumericAssertion[int])
    assert_type(assert_that(3.14), _NumericAssertion[float])
    assert_type(assert_that(complex(1, 2)), _NumericAssertion[complex])
    assert_type(assert_that({"key": "value"}), _DictAssertion)
    assert_type(assert_that(["a", "b"]), _IterableAssertion[str])
    assert_type(assert_that(("a", "b")), _IterableAssertion[str])
    assert_type(assert_that({"a", "b"}), _IterableAssertion[str])
    assert_type(assert_that(frozenset({"a"})), _IterableAssertion[str])
    assert_type(assert_that(datetime.date(2026, 1, 1)), _DateAssertion)
    assert_type(assert_that(datetime.datetime(2026, 1, 1, 12, 0)), _DateAssertion)
    assert_type(assert_that(pathlib.Path("/tmp")), _PathAssertion)
    assert_type(assert_that(b"raw"), _BytesAssertion)
    assert_type(assert_that(bytearray(b"raw")), _BytesAssertion)
    assert_type(assert_that(len), _CallableAssertion)
    assert_type(assert_that(object()), AssertionBuilder[object])

    # The iterable-cluster methods stay on their protocol (return Self), so chaining keeps the type.
    assert_type(assert_that([1, 2]).satisfies_exactly(lambda x: x > 0, lambda x: x > 1), _IterableAssertion[int])
    assert_type(assert_that([1, 2]).zip_satisfies([2, 3], lambda left, right: left < right), _IterableAssertion[int])
    assert_type(assert_that([1, 2]).contains_only_once(1), _IterableAssertion[int])
    assert_type(assert_that([1, 2]).has_same_size_as((3, 4)), _IterableAssertion[int])
    assert_type(assert_that("ab").contains_only_once("a"), _StringAssertion)
    assert_type(assert_that("ab").has_same_size_as("cd"), _StringAssertion)
    assert_type(assert_that({"k": 1}).has_same_size_as({"j": 2}), _DictAssertion)
    assert_type(assert_that(b"ab").has_same_size_as(b"cd"), _BytesAssertion)

    # The recursive leaf assertions live on the core protocol, so they keep each value's own type.
    assert_type(assert_that({"k": 1}).all_fields_satisfy(lambda x: x > 0), _DictAssertion)
    assert_type(assert_that(42).has_no_none_fields(), _NumericAssertion[int])

    # is_equal_to keeps its protocol with the recursive-comparison kwargs.
    assert_type(assert_that({"k": 1.0}).is_equal_to({"k": 1.0}, tolerance=0.001), _DictAssertion)
    assert_type(assert_that({"k": 1}).is_equal_to({"k": 1}, comparators={int: lambda a, e: a == e}), _DictAssertion)

    # Ordering is declared wherever the runtime supports it (assertpy#128): lexicographic on str and
    # bytes/bytearray, chronological on dates (including is_between; is_close_to stays datetime-only
    # at runtime, so the shared date protocol does not advertise it).
    assert_type(assert_that("banana").is_greater_than("apple"), _StringAssertion)
    assert_type(assert_that("apple").is_less_than("banana"), _StringAssertion)
    assert_type(assert_that("b").is_greater_than_or_equal_to("a"), _StringAssertion)
    assert_type(assert_that("a").is_less_than_or_equal_to("b"), _StringAssertion)
    assert_type(assert_that(b"b").is_greater_than(b"a"), _BytesAssertion)
    assert_type(assert_that(b"a").is_less_than(bytearray(b"b")), _BytesAssertion)
    assert_type(assert_that(bytearray(b"b")).is_greater_than_or_equal_to(b"a"), _BytesAssertion)
    assert_type(assert_that(b"a").is_less_than_or_equal_to(b"b"), _BytesAssertion)
    assert_type(assert_that(datetime.date(2026, 1, 2)).is_greater_than(datetime.date(2026, 1, 1)), _DateAssertion)
    assert_type(assert_that(datetime.date(2026, 1, 1)).is_less_than(datetime.date(2026, 1, 2)), _DateAssertion)
    assert_type(
        assert_that(datetime.datetime(2026, 1, 2)).is_greater_than_or_equal_to(datetime.datetime(2026, 1, 1)),
        _DateAssertion,
    )
    assert_type(
        assert_that(datetime.datetime(2026, 1, 1)).is_less_than_or_equal_to(datetime.datetime(2026, 1, 2)),
        _DateAssertion,
    )
    assert_type(
        assert_that(datetime.date(2026, 1, 2)).is_between(datetime.date(2026, 1, 1), datetime.date(2026, 1, 3)),
        _DateAssertion,
    )

    # The any-order, relational-size, string-sugar, and type methods keep their protocols (return Self).
    assert_type(assert_that([3, 1, 2]).contains_exactly_in_any_order(1, 2, 3), _IterableAssertion[int])
    assert_type(assert_that("cba").contains_exactly_in_any_order("a", "b", "c"), _StringAssertion)
    assert_type(
        assert_that([1, 2]).satisfies_exactly_in_any_order(lambda x: x > 1, lambda x: x < 2), _IterableAssertion[int]
    )
    assert_type(assert_that([1, 2]).has_size_greater_than(1), _IterableAssertion[int])
    assert_type(assert_that("ab").has_size_less_than(3), _StringAssertion)
    assert_type(assert_that({"k": 1}).has_size_between(0, 2), _DictAssertion)
    assert_type(assert_that(b"ab").has_size_between(1, 2), _BytesAssertion)
    assert_type(assert_that("ab").is_length_between(1, 3), _StringAssertion)
    assert_type(assert_that(42).is_length_between(0, 9), _NumericAssertion[int])
    assert_type(assert_that("a b").is_equal_to_ignoring_whitespace("ab"), _StringAssertion)
    assert_type(assert_that("FooBar").starts_with_ignoring_case("foo"), _StringAssertion)
    assert_type(assert_that("FooBar").ends_with_ignoring_case("BAR"), _StringAssertion)
    assert_type(assert_that(1).is_instance_of_any(int, float), _NumericAssertion[int])
    assert_type(assert_that("s").is_subclass_of(object), _StringAssertion)

    # eventually() and eventually_sync() switch the chain to the polling builders.
    assert_type(assert_that(len).eventually(trace=False), AsyncAssertionBuilder)
    assert_type(assert_that(len).eventually_sync(timeout=2, trace=False), SyncAssertionBuilder)

    # Typed extract-and-continue: the generic fallback tracks the input type, `.value` hands it back,
    # and the narrowing terminals refine it (is_not_none strips None, is_instance_of narrows to the class).
    maybe_name = cast("str | None", "fred")
    anything = cast("object", "fred")
    assert_type(assert_that(maybe_name), AssertionBuilder[str | None])
    assert_type(assert_that(maybe_name).is_not_none(), AssertionBuilder[str])
    assert_type(assert_that(maybe_name).is_not_none().value, str)
    assert_type(assert_that(anything).is_instance_of(bool), AssertionBuilder[bool])
    assert_type(assert_that(anything).is_instance_of(bool).value, bool)
    assert_type(assert_that(maybe_name).is_not_none().is_instance_of(str).value, str)
    assert_type(assert_that(anything).is_not_none(), AssertionBuilder[object])

    # User-extensible refinement narrowing: a TypeIs predicate narrows satisfies() to the guarded type,
    # so a domain predicate (richer than isinstance) narrows the chain and `.value` hands it back typed.
    class _Order: ...

    class _PaidOrder(_Order): ...

    def _is_paid(order: _Order) -> TypeIs[_PaidOrder]:
        return isinstance(order, _PaidOrder)

    some_order = cast("_Order", _PaidOrder())
    assert_type(assert_that(some_order).satisfies(_is_paid), AssertionBuilder[_PaidOrder])
    assert_type(assert_that(some_order).satisfies(_is_paid).value, _PaidOrder)
    assert_type(assert_that(anything).is_not_none().satisfies(_is_paid).value, _PaidOrder)
    # a plain (non-TypeIs) predicate does not narrow: the chain keeps its type
    assert_type(assert_that(some_order).satisfies(lambda item: bool(item)), AssertionBuilder[_Order])

    # assert_conforms() narrows to the validated model for ANY input - the narrowing capstone. Because the
    # return type is driven by the model arg (not the value), even the `Any` a decoded JSON payload
    # carries and an explicitly dict-typed payload both narrow, where a method on the builder could not.
    json_payload = cast("Any", {"id": 1})
    dict_payload = cast("dict[str, object]", {"id": 1})
    assert_type(assert_conforms(anything, _Order), AssertionBuilder[_Order])
    assert_type(assert_conforms(anything, _Order).value, _Order)
    assert_type(assert_conforms(json_payload, _PaidOrder).value, _PaidOrder)
    assert_type(assert_conforms(dict_payload, _PaidOrder).value, _PaidOrder)

    # collection element-access pivots narrow to the element type (universal narrowing across pivots)
    assert_type(assert_that([1, 2, 3]).first().value, int)
    assert_type(assert_that(["a", "b"]).last().value, str)
    assert_type(assert_that((1.0, 2.0)).element(0).value, float)
    order_list = cast("list[_Order]", [])
    assert_type(assert_that(order_list).single().value, _Order)
    assert_type(assert_that(order_list).first(), AssertionBuilder[_Order])
    # a map pivot re-types the element; a filter preserves it
    assert_type(assert_that([1, 2]).mapped(str).value, list[str] | tuple[str, ...] | set[str] | frozenset[str])
    assert_type(
        assert_that(order_list).filtered_on(lambda o: True).value,
        list[_Order] | tuple[_Order, ...] | set[_Order] | frozenset[_Order],
    )

    # `.value` on the typed protocols returns each protocol's value-family type.
    assert_type(assert_that("text").value, str)
    assert_type(assert_that(42).value, int)
    assert_type(assert_that({"key": 1}).value, dict[Any, Any])
    assert_type(assert_that([1, 2]).value, list[int] | tuple[int, ...] | set[int] | frozenset[int])
    assert_type(assert_that(b"raw").value, bytes | bytearray)
    assert_type(assert_that(pathlib.Path("/tmp")).value, pathlib.Path)
    assert_type(assert_that(datetime.date(2026, 1, 1)).value, datetime.date)
    assert_type(assert_that(len).value, Callable[..., object])
