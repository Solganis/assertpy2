"""Static typing tests for the ``assert_that`` overloads.

These are verified by type checkers (ty, Pyright, Mypy, Pyrefly), not at runtime: each ``assert_type`` pins the
overload resolution to the documented type-specific Protocol, so a regression that broadens or changes a
return type fails the type check. The body lives under ``TYPE_CHECKING`` because the Protocols in
:mod:`assertpy2._engine._typing` exist only for static analysis and are absent at runtime; Pytest imports this
module without executing the block.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import datetime
    import logging
    import pathlib
    from collections.abc import Callable, Mapping, Sequence
    from typing import Any, cast

    from typing_extensions import TypeIs, assert_type

    from assertpy2 import AssertionOutcome, assert_conforms, assert_that, assert_warn, match
    from assertpy2._engine._capable_typing import _CapableAssertion
    from assertpy2._engine._check_typing import (
        _CheckDictAssertion,
        _CheckNumericAssertion,
        _CheckStringAssertion,
    )
    from assertpy2._engine._poll_typing import _AsyncPoll, _SyncPoll
    from assertpy2._engine._typing import (
        _ArrayAssertion,
        _ArrayShape,
        _BoolAssertion,
        _BytesAssertion,
        _CallableAssertion,
        _ComplexAssertion,
        _CoreAssertion,
        _DateAssertion,
        _DateTimeAssertion,
        _DictAssertion,
        _FrameAssertion,
        _FrameShape,
        _InvokedAssertion,
        _IterableAssertion,
        _ListAssertion,
        _NumericAssertion,
        _ObjectAssertion,
        _PathAssertion,
        _StringAssertion,
        _TextAssertion,
    )
    from assertpy2.assertpy import AssertionBuilder
    from assertpy2.matchers import IsInstanceOfMatcher, IsTypeOfMatcher, Matcher

    assert_type(assert_that("text"), _StringAssertion)
    assert_type(assert_that(42), _NumericAssertion[int])
    assert_type(assert_that(3.14), _NumericAssertion[float])
    # both used to resolve to the numeric protocol and be offered methods whose only outcome was a TypeError
    assert_type(assert_that(complex(1, 2)), _ComplexAssertion)
    assert_type(assert_that(True), _BoolAssertion)
    # a step hands back `Self`, so the smaller protocol holds for the whole chain rather than the first call
    assert_type(assert_that(complex(1, 2)).is_not_zero().value, complex)
    assert_type(assert_that(complex(1, 2)).not_.is_zero().value, complex)
    assert_type(assert_that(True).is_greater_than(0).value, bool)
    assert_type(assert_that({"key": "value"}), _DictAssertion[str, str])
    assert_type(assert_that(["a", "b"]), _IterableAssertion[str])
    assert_type(assert_that(("a", "b")), _IterableAssertion[str])
    assert_type(assert_that({"a", "b"}), _IterableAssertion[str])
    assert_type(assert_that(frozenset({"a"})), _IterableAssertion[str])
    # a `datetime` is a `date` and then some: the chronological nine refuse a plain date at run time, on
    # the value as well as the operand, so one view for both types offered them to one that raises
    assert_type(assert_that(datetime.date(2026, 1, 1)), _DateAssertion)
    assert_type(assert_that(datetime.datetime(2026, 1, 1, 12, 0)), _DateTimeAssertion)
    assert_type(assert_that(datetime.datetime(2026, 1, 1, 12, 0)).value, datetime.datetime)
    assert_type(assert_that(pathlib.Path("/tmp")), _PathAssertion)
    assert_type(assert_that(b"raw"), _BytesAssertion[bytes])
    assert_type(assert_that(b"raw").starts_with(b"r"), _BytesAssertion[bytes])
    assert_type(assert_that(b"raw").ends_with(b"w"), _BytesAssertion[bytes])
    assert_type(assert_that(b"raw").starts_with_bytes(b"r"), _BytesAssertion[bytes])
    assert_type(assert_that({"a": 1}).each(lambda key: True), _DictAssertion[str, int])
    # a text is walked character by character, so the quantifiers answer for it and the element is a
    # `str`: the runtime has always taken them, and no view offered one
    assert_type(assert_that("ab").each(lambda character: character.isalpha()), _StringAssertion)
    assert_type(assert_that("ab").any_satisfy(lambda character: character == "a"), _StringAssertion)
    assert_type(assert_that("ab").satisfies_exactly(lambda first: first == "a"), _StringAssertion)
    # the pairwise one names both sides: a character and an element of the sequence walked alongside it
    assert_type(
        assert_that("ab").zip_satisfies([1, 2], lambda character, number: character.isalpha() and number > 0),
        _StringAssertion,
    )
    # and the loose spelling stays ordinary: naming the two sides is not a demand that a caller name them
    _pairs: list[Any] = [1, 2]
    _loose: Callable[[Any, Any], object] = lambda left, right: left == right  # noqa: E731  # the shape under test
    assert_type(assert_that("ab").zip_satisfies(_pairs, _loose), _StringAssertion)
    assert_type(assert_that({"a": 1}).all_satisfy(lambda key: True), _DictAssertion[str, int])
    assert_type(assert_that(bytearray(b"raw")), _BytesAssertion[bytearray])
    assert_type(assert_that(len), _CallableAssertion[int])
    # the pair gate reads literals, so this is what ties `Callable` to the view it dispatches to
    assert_type(assert_that(lambda: None), _CallableAssertion[None])

    class _Countable:
        def __iter__(self) -> object: ...

    class _CallableResponse:
        """An ASGI or WSGI response: a callable, and the one thing an HTTP capability describes."""

        def __call__(self, *args: object, **kwargs: object) -> object: ...
        @property
        def status_code(self) -> int: ...
        @property
        def headers(self) -> Mapping[str, str]: ...

    # the callable view sits under the shapes for this: above them it claimed a Starlette or a Flask
    # response, and `has_status_code()` on one was a type error in all three checkers while the runtime
    # answered it.  `tests/typing_http.py` asks the same question of the real classes
    assert_type(assert_that(_CallableResponse()), _CapableAssertion[_CallableResponse])

    assert_type(assert_that(object()), _ObjectAssertion[object])

    # a dynamic assertion and an `add_extension` name resolve through the same hook, and no one signature is true
    # of both.  A plain object gets the object view, which has no `__getattr__`, so `has_anything` on one is a
    # type error.  A capable value has the hook, and the facade hands its own surface back rather than `Any`
    assert_type(assert_that(_Countable()).has_anything("value"), _CapableAssertion[_Countable])

    assert_type(assert_that(42).not_.is_equal_to(43), _NumericAssertion[int])
    assert_type(assert_that("text").not_.starts_with("x"), _StringAssertion)
    assert_type(assert_that([1, 2]).not_.contains(3), _IterableAssertion[int])
    assert_type(assert_that(42).not_.is_equal_to(43).value, int)

    assert_type(assert_that(42).check().is_positive(), AssertionOutcome)
    # the proxy is the verdict twin of the view it was reached from, so a wrong-domain assertion is a type error here
    # too
    assert_type(assert_that(42).check(), _CheckNumericAssertion[int])
    assert_type(assert_that("text").check(), _CheckStringAssertion)
    assert_type(assert_that({"a": 1}).check(), _CheckDictAssertion[str, int])
    assert_type(assert_that("text").check().starts_with("x"), AssertionOutcome)
    assert_type(assert_that({"a": 1}).check().contains_key("a"), AssertionOutcome)
    assert_type(assert_that(42).check().not_.is_positive(), AssertionOutcome)

    assert_type(assert_that([1, 2]).satisfies_exactly(lambda x: x > 0, lambda x: x > 1), _IterableAssertion[int])
    assert_type(assert_that([1, 2]).zip_satisfies([2, 3], lambda left, right: left < right), _IterableAssertion[int])
    assert_type(assert_that([1, 2]).contains_only_once(1), _IterableAssertion[int])
    assert_type(assert_that([1, 2]).has_same_size_as((3, 4)), _IterableAssertion[int])
    assert_type(assert_that("ab").contains_only_once("a"), _StringAssertion)
    assert_type(assert_that("ab").has_same_size_as("cd"), _StringAssertion)
    assert_type(assert_that({"k": 1}).has_same_size_as({"j": 2}), _DictAssertion[str, int])
    assert_type(assert_that(b"ab").has_same_size_as(b"cd"), _BytesAssertion[bytes])

    assert_type(assert_that({"k": 1}).all_fields_satisfy(lambda x: x > 0), _DictAssertion[str, int])
    assert_type(assert_that(42).has_no_none_fields(), _NumericAssertion[int])

    assert_type(assert_that({"k": 1.0}).is_equal_to({"k": 1.0}, tolerance=0.001), _DictAssertion[str, float])
    assert_type(
        assert_that({"k": 1}).is_equal_to({"k": 1}, comparators={int: lambda a, e: a == e}), _DictAssertion[str, int]
    )
    assert_type(assert_that({"k": 1}).is_equal_to({"k": None}, ignore_null=True), _DictAssertion[str, int])

    # declared wherever the runtime supports it: `is_close_to` stays datetime-only, so the shared date protocol does
    # not advertise it
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
        _DateTimeAssertion,
    )
    assert_type(
        assert_that(datetime.datetime(2026, 1, 1)).is_less_than_or_equal_to(datetime.datetime(2026, 1, 2)),
        _DateTimeAssertion,
    )
    assert_type(
        assert_that(datetime.date(2026, 1, 2)).is_between(datetime.date(2026, 1, 1), datetime.date(2026, 1, 3)),
        _DateAssertion,
    )

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
    assert_type(assert_that(1).is_instance_of_any(str, int | float), _NumericAssertion[int])
    assert_type(assert_that(1).is_instance_of_any(str, (int, float)), _NumericAssertion[int])
    assert_type(assert_that("s").is_subclass_of(object), _StringAssertion)
    # a caught message is text without being a `str` view, and its element pivots are the only way to
    # reach `_TextAssertion` at all
    assert_type(assert_that(len).raises(ValueError).when_called_with().first(), _TextAssertion)

    assert_type(assert_that(len).eventually(trace=False), _AsyncPoll[int])
    assert_type(assert_that(len).eventually_sync(timeout=2, trace=False), _SyncPoll[int])
    assert_that(len).eventually_sync(timeout=2, trace=False).is_equal_to(1)
    assert_that(len).eventually_sync(timeout=2, trace=False).is_positive()
    assert_type(assert_that(len).eventually_sync().is_positive().val, int)
    assert_type(assert_that(len).eventually().is_positive(), _AsyncPoll[int])
    assert_that(len).eventually_sync(timeout=2, trace=False).not_.is_equal_to(2)

    assert_type(assert_that(len).raises(ValueError).when_called_with(), _InvokedAssertion)
    assert_type(assert_that(len).raises(ValueError).when_called_with().caused_by(KeyError), _InvokedAssertion)
    assert_type(assert_that(len).raises(ValueError).when_called_with().has_root_cause(KeyError), _InvokedAssertion)
    assert_type(assert_that(len).raises(ValueError).when_called_with().contains_error(KeyError), _InvokedAssertion)
    assert_type(assert_that(len).raises(ValueError).when_called_with().raised(), _CoreAssertion)
    invoked = assert_that(len).raises(ValueError).when_called_with()
    assert_type(invoked.does_not_contain_error(KeyError), _InvokedAssertion)
    assert_type(invoked.errors(), _ListAssertion[BaseException])
    assert_type(invoked.errors().value, list[BaseException])
    assert_type(invoked.error_of(KeyError), _InvokedAssertion)
    assert_type(invoked.error_of(KeyError).value, str)
    assert_type(invoked.error_of(KeyError).raised(), _CoreAssertion)

    maybe_name = cast("str | None", "fred")
    anything = cast("object", "fred")
    assert_type(assert_that(maybe_name), _ObjectAssertion[str | None])
    # the refinement answers with the view the factory would have given, since a refinement that ended the narrowing
    # would be a dead end
    assert_type(assert_that(maybe_name).is_not_none(), _StringAssertion)
    assert_type(assert_that(maybe_name).is_not_none().value, str)
    assert_type(assert_that(anything).is_instance_of(bool), _BoolAssertion)
    assert_type(assert_that(anything).is_instance_of(bool).value, bool)
    assert_type(assert_that(anything).is_instance_of(bool | int), _ObjectAssertion[bool | int])
    assert_type(assert_that(anything).is_instance_of(bool | int).value, bool | int)
    assert_type(assert_that(anything).is_instance_of((bool, int)), _ObjectAssertion[object])
    assert_type(assert_that(anything).is_instance_of((bool, int)).value, object)
    assert_type(assert_that(maybe_name).is_not_none().is_instance_of(str).value, str)
    assert_type(assert_that(anything).is_not_none(), _ObjectAssertion[object])

    # a value whose only claim is a shape is where the refinement stops, and a `TypeIs` predicate is the way back
    def _is_countable(value: object) -> TypeIs[_Countable]:
        return isinstance(value, _Countable)

    maybe_bag = cast("_Countable | None", _Countable())
    assert_type(assert_that(maybe_bag).is_not_none(), _ObjectAssertion[_Countable])
    assert_type(assert_that(anything).is_instance_of(_Countable), _ObjectAssertion[_Countable])
    assert_type(assert_that(anything).satisfies(_is_countable), AssertionBuilder[_Countable])

    class _Order: ...

    class _PaidOrder(_Order): ...

    class _Shouted(str): ...

    def _is_paid(order: _Order) -> TypeIs[_PaidOrder]:
        return isinstance(order, _PaidOrder)

    some_order = cast("_Order", _PaidOrder())
    assert_type(assert_that(some_order).satisfies(_is_paid), _ObjectAssertion[_PaidOrder])
    assert_type(assert_that(some_order).satisfies(_is_paid).value, _PaidOrder)
    assert_type(assert_that(anything).is_not_none().satisfies(_is_paid).value, _PaidOrder)
    assert_type(assert_that(some_order).satisfies(lambda item: bool(item)), _ObjectAssertion[_Order])

    # ... and refinement is not confined to the generic fallback. A concretely typed value reaches the
    # per-type Protocol, and it narrows from there too: a JSON payload typed `dict[str, Any]` is where a
    # domain predicate is most often applied, and it used to be the one place refinement stopped.
    payload = cast("dict[str, Any]", {"id": 1})
    assert_type(assert_that(payload).satisfies(_is_paid), _ObjectAssertion[_PaidOrder])
    assert_type(assert_that(payload).satisfies(_is_paid).value, _PaidOrder)

    # ... and the guard has to be one the subject can be handed to.  A concretely typed view binds the
    # predicate to its own value, so a guard about orders is refused on a `str` rather than promising a
    # narrowing of something that would raise on the first attribute it read
    def _is_shouted(text: str) -> TypeIs[_Shouted]:
        return text.isupper()

    assert_type(assert_that("x").satisfies(_is_shouted), AssertionBuilder[_Shouted])
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
    assert_type(assert_conforms(anything, _Order, each=True), AssertionBuilder[list[_Order]])
    assert_type(assert_conforms(anything, _Order, each=True).value, list[_Order])

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

    # a character of a string is a string and a byte is an int, so both stay on their own protocol.
    # The invoked view lands on text, which keeps a caught message from being asked to exist on disk
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
    assert_type(assert_that({"a": 1}).first(), AssertionBuilder[str])
    assert_type(assert_that({"a": 1}).filtered_on(lambda key: True), _ListAssertion[str])
    assert_type(assert_that({"a": 1}).mapped(str.upper), _ListAssertion[str])

    assert_type(assert_that(42).is_not_iterable(), _NumericAssertion[int])
    assert_type(assert_that(datetime.date(2026, 1, 1)).is_not_iterable(), _DateAssertion)
    assert_type(assert_that(pathlib.Path("/tmp")).is_iterable(), _PathAssertion)
    assert_type(assert_that("abc").is_iterable(), _StringAssertion)
    assert_type(assert_that({"a": 1}).is_iterable(), _DictAssertion[str, int])
    assert_type(assert_that("aBc").is_sorted(key=str.lower), _StringAssertion)
    assert_type(assert_that(b"abc").is_sorted(key=lambda byte: -byte), _BytesAssertion[bytes])
    assert_type(assert_that({"a": 1}).is_sorted(key=str.upper), _DictAssertion[str, int])
    assert_type(assert_that([3, 1]).is_sorted(key=abs), _IterableAssertion[int])
    assert_type(assert_that(b"ab").is_subset_of(b"abc"), _BytesAssertion[bytes])

    assert_type(assert_that("text").value, str)
    assert_type(assert_that(42).value, int)
    assert_type(assert_that({"key": 1}).value, dict[str, int])
    assert_type(assert_that([1, 2]).value, list[int] | tuple[int, ...] | set[int] | frozenset[int])
    assert_type(assert_that(b"raw").value, bytes)
    assert_type(assert_that(pathlib.Path("/tmp")).value, pathlib.Path)
    assert_type(assert_that(datetime.date(2026, 1, 1)).value, datetime.date)
    assert_type(assert_that(len).value, Callable[..., int])

    # A pivot on the builder hands back an element, and used to be declared as handing back the
    # chain.  That is the half a narrowing at `assert_that()` cannot reach: the second pivot lands on
    # the builder whatever the first returned, so depth is where it shows.
    rows = cast("Sequence[Sequence[int]]", [[1]])
    keys = cast("Mapping[str, int]", {"a": 1})
    assert_type(assert_that(rows).first(), AssertionBuilder[Sequence[int]])
    assert_type(assert_that(rows).first().first(), AssertionBuilder[int])
    assert_type(assert_that(rows).last().element(0), AssertionBuilder[int])
    assert_type(assert_that(keys).first(), AssertionBuilder[str])
    assert_type(assert_that(rows).first().single(), AssertionBuilder[int])
    assert_type(assert_that(rows).first().mapped(str), AssertionBuilder[list[str]])

    class _FakeFrame:
        def pivot(self, *args: object, **kwargs: object) -> object: ...

        @property
        def shape(self) -> object: ...

    class _FakeArray:
        def __array__(self) -> object: ...

        @property
        def strides(self) -> object: ...

    assert_type(assert_that(cast("_FrameShape", object())), _FrameAssertion[_FrameShape])
    assert_type(assert_that(cast("_ArrayShape", object())), _ArrayAssertion[_ArrayShape])
    frame = cast("_FakeFrame", object())
    array = cast("_FakeArray", object())
    assert_type(assert_that(frame), _FrameAssertion[_FakeFrame])
    assert_type(assert_that(array), _ArrayAssertion[_FakeArray])
    assert_type(assert_that(frame).value, _FakeFrame)
    assert_type(assert_that(array).value, _FakeArray)
    assert_type(assert_that(frame).is_frame_equal(frame), _FrameAssertion[_FakeFrame])
    assert_type(assert_that(array).is_array_equal(array), _ArrayAssertion[_FakeArray])
    assert_type(assert_that(array).is_array_close_to(array, rtol=0.1), _ArrayAssertion[_FakeArray])

    assert_type(match.is_instance_of(int), IsInstanceOfMatcher)
    assert_type(match.is_instance_of(int | str), IsInstanceOfMatcher)
    assert_type(match.is_instance_of((int, str)), IsInstanceOfMatcher)
    assert_type(match.is_instance_of((int | str, float)), IsInstanceOfMatcher)
    # nested to a second level, which `isinstance` accepts and the alias is recursive to match
    assert_type(match.is_instance_of((int, (str, float))), IsInstanceOfMatcher)
    assert_type(match.is_type_of(int), IsTypeOfMatcher)

    class _FakeResponse:
        status_code: int
        headers: dict[str, str]

        def json(self) -> Any: ...

    response = _FakeResponse()
    assert_type(assert_that(response), _CapableAssertion[_FakeResponse])
    assert_type(assert_that(response).decoded_as_json(), AssertionBuilder[object])
    assert_type(assert_that(response).decoded_as_json().value, object)

    # every shape `assert_warn` documents a logger as.  The docstring says `Logger`, the default the
    # builder installs is a `LoggerAdapter`, and the only thing reached on either is `warning()`, so
    # naming a concrete type here would refuse working code that the runtime accepts
    class _OwnLogger:
        def warning(self, msg: object) -> None: ...

    assert_type(assert_warn("foo", logger=logging.getLogger("app")), Any)
    assert_type(assert_warn("foo", logger=logging.LoggerAdapter(logging.getLogger("app"), None)), Any)
    assert_type(assert_warn("foo", logger=_OwnLogger()), Any)
    assert_type(assert_warn("foo"), Any)

    # comparator and placeholder tables built before the call, which is how the docs show them.  A `dict`
    # parameter refuses these outright, being invariant in both halves: a table declared `dict[str, ...]` is not
    # a `dict[object, ...]`, and one returning `bool` is not one returning `object`.  `Mapping[Any, ...]` is what
    # accepts them, and the runtime only ever reads them
    by_type: dict[type, Callable[[float, float], bool]] = {float: lambda a, e: round(a, 2) == round(e, 2)}
    by_field: dict[str, Callable[[Any, Any], bool]] = {"name": lambda a, e: a.lower() == e.lower()}
    volatile: dict[str, Matcher[str]] = {"id": match.is_uuid()}
    assert_type(assert_that({"n": 1.0}).snapshot(id="a", comparators=by_type), _DictAssertion[str, float])
    assert_type(assert_that({"name": "A"}).snapshot(id="b", comparators=by_field), _DictAssertion[str, str])
    assert_type(assert_that({"id": "x"}).snapshot(id="c", placeholders=volatile), _DictAssertion[str, str])
