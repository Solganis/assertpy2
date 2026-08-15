"""Static typing tests for the ``assert_that`` overloads.

These are verified by type checkers (ty, Pyright, Mypy), not at runtime: each ``assert_type`` pins the
overload resolution to the documented type-specific Protocol, so a regression that broadens or changes a
return type fails the type check. The body lives under ``TYPE_CHECKING`` because the Protocols in
:mod:`assertpy2._engine._typing` exist only for static analysis and are absent at runtime; Pytest imports this
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

    from assertpy2 import AssertionOutcome, assert_conforms, assert_that, match
    from assertpy2._engine._typing import (
        _BoolAssertion,
        _BytesAssertion,
        _CallableAssertion,
        _ComplexAssertion,
        _CoreAssertion,
        _DateAssertion,
        _DictAssertion,
        _InvokedAssertion,
        _IterableAssertion,
        _ListAssertion,
        _NumericAssertion,
        _PathAssertion,
        _StringAssertion,
    )
    from assertpy2.assertpy import AssertionBuilder
    from assertpy2.async_assertions import AsyncAssertionBuilder, SyncAssertionBuilder
    from assertpy2.matchers import IsInstanceOfMatcher, IsTypeOfMatcher

    # Each call is a static assertion: it fails type checking if assert_that stops returning the
    # documented Protocol for that value type. The mapping mirrors the table in docs/type-safety.md.
    assert_type(assert_that("text"), _StringAssertion)
    assert_type(assert_that(42), _NumericAssertion[int])
    assert_type(assert_that(3.14), _NumericAssertion[float])
    # `complex` and `bool` carry only what the runtime accepts for them: no ordering for a complex
    # number, no parity for a bool. Both used to resolve to the numeric protocol and be offered methods
    # whose only outcome was a TypeError
    assert_type(assert_that(complex(1, 2)), _ComplexAssertion)
    assert_type(assert_that(True), _BoolAssertion)
    # a step hands back `Self`, so the smaller protocol holds for the whole chain rather than for the
    # first call: `.value` stays `complex` and the assertions after it stay the two that apply
    assert_type(assert_that(complex(1, 2)).is_not_zero().value, complex)
    assert_type(assert_that(complex(1, 2)).not_.is_zero().value, complex)
    assert_type(assert_that(True).is_greater_than(0).value, bool)
    assert_type(assert_that({"key": "value"}), _DictAssertion[str, str])
    assert_type(assert_that(["a", "b"]), _IterableAssertion[str])
    assert_type(assert_that(("a", "b")), _IterableAssertion[str])
    assert_type(assert_that({"a", "b"}), _IterableAssertion[str])
    assert_type(assert_that(frozenset({"a"})), _IterableAssertion[str])
    assert_type(assert_that(datetime.date(2026, 1, 1)), _DateAssertion)
    assert_type(assert_that(datetime.datetime(2026, 1, 1, 12, 0)), _DateAssertion)
    assert_type(assert_that(pathlib.Path("/tmp")), _PathAssertion)
    assert_type(assert_that(b"raw"), _BytesAssertion[bytes])
    # the prefix/suffix pair handles bytes natively, so both spellings are reachable and typed
    assert_type(assert_that(b"raw").starts_with(b"r"), _BytesAssertion[bytes])
    assert_type(assert_that(b"raw").ends_with(b"w"), _BytesAssertion[bytes])
    assert_type(assert_that(b"raw").starts_with_bytes(b"r"), _BytesAssertion[bytes])
    # the quantifier under both its names, from the dict view as well as the sequence one
    assert_type(assert_that({"a": 1}).each(lambda key: True), _DictAssertion[str, int])
    assert_type(assert_that({"a": 1}).all_satisfy(lambda key: True), _DictAssertion[str, int])
    assert_type(assert_that(bytearray(b"raw")), _BytesAssertion[bytearray])
    assert_type(assert_that(len), _CallableAssertion)
    # the same view, pinned on a literal callable as well: a name resolves through its own type, and the
    # pair gate reads literals, so this is the line that ties `Callable` to the view it dispatches to
    assert_type(assert_that(lambda: None), _CallableAssertion)
    assert_type(assert_that(object()), AssertionBuilder[object])

    # a dynamic assertion and an `add_extension` name both resolve through the same `__getattr__`, and
    # no one signature is true of both, so the hook deliberately answers Any. pinned here because both
    # narrower forms were tried and each one rejected code that runs: see DynamicMixin.__getattr__
    assert_type(assert_that(object()).has_anything("value"), Any)

    # not_ hands back the assertion it was reached from, so inverting a step does not end the
    # narrowing: the value type survives it and a wrong-domain assertion is still rejected after it.
    assert_type(assert_that(42).not_.is_equal_to(43), _NumericAssertion[int])
    assert_type(assert_that("text").not_.starts_with("x"), _StringAssertion)
    assert_type(assert_that([1, 2]).not_.contains(3), _IterableAssertion[int])
    assert_type(assert_that(42).not_.is_equal_to(43).value, int)

    # check() ends the chain with the verdict, from every protocol and through the negation proxy.
    assert_type(assert_that(42).check().is_positive(), AssertionOutcome)
    assert_type(assert_that("text").check().starts_with("x"), AssertionOutcome)
    assert_type(assert_that({"a": 1}).check().contains_key("a"), AssertionOutcome)
    assert_type(assert_that(42).check().not_.is_positive(), AssertionOutcome)

    # The iterable-cluster methods stay on their protocol (return Self), so chaining keeps the type.
    assert_type(assert_that([1, 2]).satisfies_exactly(lambda x: x > 0, lambda x: x > 1), _IterableAssertion[int])
    assert_type(assert_that([1, 2]).zip_satisfies([2, 3], lambda left, right: left < right), _IterableAssertion[int])
    assert_type(assert_that([1, 2]).contains_only_once(1), _IterableAssertion[int])
    assert_type(assert_that([1, 2]).has_same_size_as((3, 4)), _IterableAssertion[int])
    assert_type(assert_that("ab").contains_only_once("a"), _StringAssertion)
    assert_type(assert_that("ab").has_same_size_as("cd"), _StringAssertion)
    assert_type(assert_that({"k": 1}).has_same_size_as({"j": 2}), _DictAssertion[str, int])
    assert_type(assert_that(b"ab").has_same_size_as(b"cd"), _BytesAssertion[bytes])

    # The recursive leaf assertions live on the core protocol, so they keep each value's own type.
    assert_type(assert_that({"k": 1}).all_fields_satisfy(lambda x: x > 0), _DictAssertion[str, int])
    assert_type(assert_that(42).has_no_none_fields(), _NumericAssertion[int])

    # is_equal_to keeps its protocol with the recursive-comparison kwargs.
    assert_type(assert_that({"k": 1.0}).is_equal_to({"k": 1.0}, tolerance=0.001), _DictAssertion[str, float])
    assert_type(
        assert_that({"k": 1}).is_equal_to({"k": 1}, comparators={int: lambda a, e: a == e}), _DictAssertion[str, int]
    )
    assert_type(assert_that({"k": 1}).is_equal_to({"k": None}, ignore_null=True), _DictAssertion[str, int])

    # Ordering is declared wherever the runtime supports it (assertpy#128): lexicographic on str and
    # bytes/bytearray, chronological on dates (including is_between; is_close_to stays datetime-only
    # at runtime, so the shared date protocol does not advertise it).
    assert_type(assert_that("banana").is_greater_than("apple"), _StringAssertion)
    assert_type(assert_that("apple").is_less_than("banana"), _StringAssertion)
    assert_type(assert_that("b").is_greater_than_or_equal_to("a"), _StringAssertion)
    assert_type(assert_that("a").is_less_than_or_equal_to("b"), _StringAssertion)
    assert_type(assert_that(b"b").is_greater_than(b"a"), _BytesAssertion[bytes])
    assert_type(assert_that(b"a").is_less_than(bytearray(b"b")), _BytesAssertion[bytes])
    assert_type(assert_that(bytearray(b"b")).is_greater_than_or_equal_to(b"a"), _BytesAssertion[bytearray])
    assert_type(assert_that(b"a").is_less_than_or_equal_to(b"b"), _BytesAssertion[bytes])
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
    assert_type(assert_that({"k": 1}).has_size_between(0, 2), _DictAssertion[str, int])
    assert_type(assert_that(b"ab").has_size_between(1, 2), _BytesAssertion[bytes])
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
    # and the assertion written on that builder has to stay callable. Only the builder type was pinned
    # here, so an inferred union out of its `__getattr__` made every polling chain uncallable to a
    # checker while these lines stayed green: caught against the built wheel, not by this suite
    assert_that(len).eventually_sync(timeout=2, trace=False).is_equal_to(1)
    assert_that(len).eventually_sync(timeout=2, trace=False).not_.is_equal_to(2)

    # exception cluster: when_called_with() gives the invoked (string message + chain) protocol;
    # caused_by()/has_root_cause()/contains_error() keep it; raised() pivots to the exception object.
    assert_type(assert_that(len).raises(ValueError).when_called_with(), _InvokedAssertion)
    assert_type(assert_that(len).raises(ValueError).when_called_with().caused_by(KeyError), _InvokedAssertion)
    assert_type(assert_that(len).raises(ValueError).when_called_with().has_root_cause(KeyError), _InvokedAssertion)
    assert_type(assert_that(len).raises(ValueError).when_called_with().contains_error(KeyError), _InvokedAssertion)
    assert_type(assert_that(len).raises(ValueError).when_called_with().raised(), _CoreAssertion)

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

    # ... and refinement is not confined to the generic fallback. A concretely typed value reaches the
    # per-type Protocol, and it narrows from there too: a JSON payload typed `dict[str, Any]` is where a
    # domain predicate is most often applied, and it used to be the one place refinement stopped.
    payload = cast("dict[str, Any]", {"id": 1})
    assert_type(assert_that(payload).satisfies(_is_paid), AssertionBuilder[_PaidOrder])
    assert_type(assert_that(payload).satisfies(_is_paid).value, _PaidOrder)
    assert_type(assert_that("x").satisfies(_is_paid), AssertionBuilder[_PaidOrder])
    # the non-narrowing overload still applies where the argument carries no refinement
    assert_type(assert_that(payload).satisfies(lambda item: bool(item)), _DictAssertion[str, Any])

    # assert_conforms() narrows to the validated model for ANY input - the narrowing capstone. Because the
    # return type is driven by the model arg (not the value), even the `Any` a decoded JSON payload
    # carries and an explicitly dict-typed payload both narrow, where a method on the builder could not.
    json_payload = cast("Any", {"id": 1})
    dict_payload = cast("dict[str, object]", {"id": 1})
    assert_type(assert_conforms(anything, _Order), AssertionBuilder[_Order])
    assert_type(assert_conforms(anything, _Order).value, _Order)
    assert_type(assert_conforms(json_payload, _PaidOrder).value, _PaidOrder)
    assert_type(assert_conforms(dict_payload, _PaidOrder).value, _PaidOrder)
    # a list endpoint (each=True) narrows to list[model]
    assert_type(assert_conforms(anything, _Order, each=True), AssertionBuilder[list[_Order]])
    assert_type(assert_conforms(anything, _Order, each=True).value, list[_Order])

    # collection element-access pivots narrow to the element type (universal narrowing across pivots)
    assert_type(assert_that([1, 2, 3]).first().value, int)
    assert_type(assert_that(["a", "b"]).last().value, str)
    assert_type(assert_that((1.0, 2.0)).element(0).value, float)
    order_list = cast("list[_Order]", [])
    assert_type(assert_that(order_list).single().value, _Order)
    assert_type(assert_that(order_list).first(), AssertionBuilder[_Order])
    # a map pivot re-types the element; a filter preserves it.  Either way the value that comes back is
    # a list, because that is what the pipeline builds whatever it was handed
    assert_type(assert_that([1, 2]).mapped(str).value, list[str])
    assert_type(assert_that(order_list).filtered_on(lambda o: True).value, list[_Order])
    assert_type(assert_that((1, 2)).filtered_on(lambda n: True).value, list[int])
    assert_type(assert_that({1, 2}).mapped(str).value, list[str])

    # The same pivots on the other walkable types.  A character of a string is a string and a byte is
    # an int, so both stay on their own protocol instead of widening to the generic builder.  The
    # invoked view inherits the same pivots and lands on text instead, which is what keeps a caught
    # message from being asked whether it exists on disk.
    assert_type(assert_that("abc").first(), _StringAssertion)
    assert_type(assert_that("abc").last(), _StringAssertion)
    assert_type(assert_that("abc").element(1), _StringAssertion)
    assert_type(assert_that("a").single(), _StringAssertion)
    assert_type(assert_that("abc").filtered_on(lambda char: True), _ListAssertion[str])
    assert_type(assert_that("abc").mapped(str.upper), _ListAssertion[str])
    assert_type(assert_that("abc").flat_mapped(lambda char: [char]), _ListAssertion[str])
    assert_type(assert_that(b"abc").first(), _NumericAssertion[int])
    assert_type(assert_that(bytearray(b"abc")).last(), _NumericAssertion[int])
    assert_type(assert_that(b"abc").element(0), _NumericAssertion[int])
    assert_type(assert_that(b"a").single(), _NumericAssertion[int])
    assert_type(assert_that(b"abc").filtered_on(lambda byte: True), _ListAssertion[int])
    assert_type(assert_that(b"abc").mapped(lambda byte: byte * 2), _ListAssertion[int])
    # a dict is walked over its keys, and a key of an arbitrary type has no protocol to narrow to
    assert_type(assert_that({"a": 1}).first(), AssertionBuilder[str])
    assert_type(assert_that({"a": 1}).filtered_on(lambda key: True), _ListAssertion[str])
    assert_type(assert_that({"a": 1}).mapped(str.upper), _ListAssertion[str])

    # The iterable pair is a question any value may ask, so it sits on the core protocol and keeps the
    # asking type rather than being reachable only from the collection view.
    assert_type(assert_that(42).is_not_iterable(), _NumericAssertion[int])
    assert_type(assert_that(datetime.date(2026, 1, 1)).is_not_iterable(), _DateAssertion)
    assert_type(assert_that(pathlib.Path("/tmp")).is_iterable(), _PathAssertion)
    assert_type(assert_that("abc").is_iterable(), _StringAssertion)
    assert_type(assert_that({"a": 1}).is_iterable(), _DictAssertion[str, int])
    # sorting is offered wherever the runtime walks a value, with the key typed to what it is handed
    assert_type(assert_that("aBc").is_sorted(key=str.lower), _StringAssertion)
    assert_type(assert_that(b"abc").is_sorted(key=lambda byte: -byte), _BytesAssertion[bytes])
    assert_type(assert_that({"a": 1}).is_sorted(key=str.upper), _DictAssertion[str, int])
    assert_type(assert_that([3, 1]).is_sorted(key=abs), _IterableAssertion[int])
    assert_type(assert_that(b"ab").is_subset_of(b"abc"), _BytesAssertion[bytes])

    # `.value` on the typed protocols returns each protocol's value-family type.
    assert_type(assert_that("text").value, str)
    assert_type(assert_that(42).value, int)
    assert_type(assert_that({"key": 1}).value, dict[str, int])
    assert_type(assert_that([1, 2]).value, list[int] | tuple[int, ...] | set[int] | frozenset[int])
    assert_type(assert_that(b"raw").value, bytes)
    assert_type(assert_that(pathlib.Path("/tmp")).value, pathlib.Path)
    assert_type(assert_that(datetime.date(2026, 1, 1)).value, datetime.date)
    assert_type(assert_that(len).value, Callable[..., object])

    # A type with no overload of its own falls through to the full surface rather than to a narrowed
    # view.  This is what lets the DataFrame and ndarray assertions carry no Protocol: they are
    # reachable because the fallback returns the concrete class.  tests/test_protocol_parity.py
    # exempts them from its reverse check on exactly this premise, so it is pinned here.
    class _FakeFrame:  # stands in for a DataFrame / ndarray: a type no assert_that overload keys on
        pass

    # cast from `object()` rather than `None`: the value is never read, and basedpyright rightly
    # calls a `None` -> _FakeFrame cast a likely mistake since neither type overlaps the other
    frame = cast("_FakeFrame", object())
    assert_type(assert_that(frame), AssertionBuilder[_FakeFrame])
    assert_type(assert_that(frame).is_frame_equal(frame), AssertionBuilder[_FakeFrame])
    assert_type(assert_that(frame).is_array_equal(frame), AssertionBuilder[_FakeFrame])
    assert_type(assert_that(frame).is_array_close_to(frame, rtol=0.1), AssertionBuilder[_FakeFrame])

    # `match.is_instance_of` forwards straight to `isinstance`, so it accepts a class, a union, or a
    # tuple of either.  The builder assertion of the same name stays narrow on purpose: its overloads
    # refine the tracked value to the given class, and a union has no single class to refine to.  Both
    # halves of that split are pinned here, because widening one without meaning to would silently
    # cost the narrowing that is the whole point of the typed surface.
    assert_type(match.is_instance_of(int), IsInstanceOfMatcher)
    assert_type(match.is_instance_of(int | str), IsInstanceOfMatcher)
    assert_type(match.is_instance_of((int, str)), IsInstanceOfMatcher)
    assert_type(match.is_instance_of((int | str, float)), IsInstanceOfMatcher)
    assert_type(match.is_type_of(int), IsTypeOfMatcher)
