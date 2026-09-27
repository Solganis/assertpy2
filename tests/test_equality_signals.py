"""Equality and membership answer where Python's own ``==`` raises instead.

A signalling `Decimal` NaN signals `InvalidOperation` at ``==``, and a `numpy` float overflows converting a Python
int past its range, on its own or inside a list or a mapping.  Every equality and membership assertion let the
exception out.  Each now answers as the pair's plain stand-in does: a signalling NaN as a quiet one, which equals
nothing but itself by identity inside a container, and a `numpy.float32` as the Python `float` it holds.
"""

from __future__ import annotations

import collections
import collections.abc
import decimal
import numbers

import pytest

from assertpy2 import assert_that, match
from assertpy2._engine._membership import occurrences
from assertpy2._engine._ordering import _holds_nan, member

_ASKED = {
    "is_equal_to": lambda value, other: assert_that(value).check().is_equal_to(other).passed,
    "is_not_equal_to": lambda value, other: assert_that(value).check().is_not_equal_to(other).passed,
    "is_equal_to-list": lambda value, other: assert_that([value]).check().is_equal_to([other]).passed,
    "is_equal_to-dict": lambda value, other: assert_that({"a": value}).check().is_equal_to({"a": other}).passed,
    "is_equal_to-ignore": lambda value, other: (
        assert_that({"a": value, "b": 1}).check().is_equal_to({"a": other, "b": 2}, ignore="b").passed
    ),
    "is_in": lambda value, other: assert_that(value).check().is_in(other, 2).passed,
    "is_not_in": lambda value, other: assert_that(value).check().is_not_in(other, 2).passed,
    "contains": lambda value, other: assert_that([value]).check().contains(other).passed,
    "contains-two": lambda value, other: assert_that([value, 3]).check().contains(other, 3).passed,
    "does_not_contain": lambda value, other: assert_that([value]).check().does_not_contain(other).passed,
    "contains_only": lambda value, other: assert_that([value]).check().contains_only(other).passed,
    "contains_only_once": lambda value, other: assert_that([value]).check().contains_only_once(other).passed,
    "contains_exactly": lambda value, other: assert_that([value]).check().contains_exactly(other).passed,
    "contains_sequence": lambda value, other: assert_that([value, 2]).check().contains_sequence(other, 2).passed,
    "contains_in_order": lambda value, other: assert_that([value, 2]).check().contains_in_order(other, 2).passed,
    "contains_duplicates": lambda value, other: assert_that([value, other]).check().contains_duplicates().passed,
    "does_not_contain_duplicates": lambda value, other: (
        assert_that([value, other]).check().does_not_contain_duplicates().passed
    ),
    "is_subset_of": lambda value, other: assert_that([value]).check().is_subset_of([other]).passed,
    "contains_value": lambda value, other: assert_that({"a": value}).check().contains_value(other).passed,
    "does_not_contain_value": lambda value, other: (
        assert_that({"a": value}).check().does_not_contain_value(other).passed
    ),
    "contains_entry": lambda value, other: assert_that({"a": value}).check().contains_entry({"a": other}).passed,
    "does_not_contain_entry": lambda value, other: (
        assert_that({"a": value}).check().does_not_contain_entry({"a": other}).passed
    ),
    "starts_with": lambda value, other: assert_that([value]).check().starts_with(other).passed,
    "ends_with": lambda value, other: assert_that([value]).check().ends_with(other).passed,
    "match.equal_to": lambda value, other: match.equal_to(other).matches(value),
    "match.is_in": lambda value, other: match.is_in(other, 2).matches(value),
    "match.contains": lambda value, other: match.contains(other).matches([value]),
}


@pytest.mark.parametrize("asked", list(_ASKED))
@pytest.mark.parametrize("counterpart", [1, "same"], ids=["another-value", "the-same-object"])
def test_a_signalling_nan_answers_as_a_quiet_one(asked, counterpart):
    signalling, quiet = decimal.Decimal("sNaN"), decimal.Decimal("NaN")
    other = signalling if counterpart == "same" else counterpart
    stand_in = quiet if counterpart == "same" else counterpart
    assert_that(_ASKED[asked](signalling, other)).is_equal_to(_ASKED[asked](quiet, stand_in))


@pytest.mark.parametrize("asked", list(_ASKED))
@pytest.mark.parametrize("bignum", [10**400, 1], ids=["past-the-float-range", "within-it"])
def test_a_numpy_float_answers_as_the_float_it_holds(asked, bignum):
    numpy = pytest.importorskip("numpy")
    with numpy.errstate(all="ignore"):
        assert_that(_ASKED[asked](numpy.float32(1), bignum)).is_equal_to(_ASKED[asked](1.0, bignum))


def test_a_scalar_numpy_broadcasts_against_a_list_holding_a_signalling_nan_is_unequal():
    numpy = pytest.importorskip("numpy")
    assert_that(assert_that([decimal.Decimal("sNaN"), 1]).check().is_equal_to(numpy.float32(1)).passed).is_false()


class _ListOfItsOwn(list):
    def __eq__(self, other: object) -> bool:
        return list.__eq__(self, other)


class _DictOfItsOwn(dict):
    def __eq__(self, other: object) -> bool:
        return dict.__eq__(self, other)


class _ContainingOfItsOwn:
    """A container whose own `__contains__` raises what it was built with."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def __contains__(self, item: object) -> bool:
        raise self.error

    def __iter__(self):
        return iter([1])


class _ArrayShapedSignal:
    """Shaped like an array for the guard in front of `==`, with an `__eq__` of its own that signals."""

    __array__ = None

    def __eq__(self, other: object) -> bool:
        raise decimal.InvalidOperation("my own signal")


class _OverflowingButOrdered:
    """An `__eq__` that overflows in its own code, and an order that calls it equal to anything."""

    def __eq__(self, other: object) -> bool:
        raise OverflowError("my own overflow")

    def __lt__(self, other: object) -> bool:
        return False

    def __gt__(self, other: object) -> bool:
        return False


class _InvertedList(list):
    __eq__ = list.__ne__


class _InvertedDict(dict):
    __eq__ = dict.__ne__


@pytest.mark.parametrize(
    ("value", "other"),
    [(_InvertedList([decimal.Decimal("sNaN")]), [1]), (_InvertedDict(a=decimal.Decimal("sNaN")), {"a": 1})],
    ids=["list", "dict"],
)
def test_a_container_whose_equality_is_not_the_built_in_one_is_not_walked(value, other):
    """Written in C but not the built-in `==`, so its elements decide nothing, and the NaN it holds answers."""
    assert_that(assert_that(value).check().is_equal_to(other).passed).is_false()


def test_dicts_whose_keys_differ_after_the_signal_are_unequal():
    """`dict.__eq__` compared a value, which signalled, before it met the key the other lacks."""
    value, other = {"a": decimal.Decimal("sNaN"), "b": 1}, {"a": 1, "c": 1}
    assert_that(assert_that(value).check().is_equal_to(other).passed).is_false()
    assert_that(assert_that(value).check().is_not_equal_to(other).passed).is_true()


@pytest.mark.parametrize(
    ("call", "raised"),
    [
        (lambda: assert_that(_ListOfItsOwn([decimal.Decimal("sNaN")])).is_equal_to([1]), decimal.InvalidOperation),
        (lambda: assert_that(_DictOfItsOwn(a=decimal.Decimal("sNaN"))).is_equal_to({"a": 1}), decimal.InvalidOperation),
        (
            lambda: assert_that(_ContainingOfItsOwn(decimal.InvalidOperation("own"))).contains(1),
            decimal.InvalidOperation,
        ),
        (lambda: assert_that(_ContainingOfItsOwn(OverflowError("own"))).contains(1), OverflowError),
        (lambda: assert_that(_ArrayShapedSignal()).is_equal_to(1, tolerance=0.5), decimal.InvalidOperation),
        (lambda: assert_that(_OverflowingButOrdered()).is_equal_to(1), OverflowError),
        (lambda: assert_that(_SignallingOfItsOwn()).is_equal_to(decimal.Decimal("NaN")), decimal.InvalidOperation),
        (lambda: assert_that([_SignallingOfItsOwn()]).is_equal_to([decimal.Decimal("sNaN")]), decimal.InvalidOperation),
    ],
    ids=[
        "list-with-its-own-eq",
        "dict-with-its-own-eq",
        "contains-signal",
        "contains-overflow",
        "array-guard",
        "ordered",
        "beside-a-quiet-nan",
        "beside-a-signalling-nan",
    ],
)
def test_an_error_raised_in_code_of_the_values_own_is_handed_on(call, raised):
    """Its own `__eq__` or `__contains__`, even one delegating to the built-in, is the value's to answer for."""
    with pytest.raises(raised):
        call()


def test_an_operand_refusal_is_told_apart_beside_a_signal():
    """The bytes' own ints signal against the NaN, and the NaN in the bytes is the operator refusing it."""
    with pytest.raises(TypeError, match="bytes-like"):
        assert_that(b"").contains_only(decimal.Decimal("sNaN"))


@pytest.mark.parametrize(("item", "held"), [(3, True), (4, False), (2, True)])
def test_an_iterator_is_searched_on_from_where_the_signal_stopped_it(item, held):
    """What `in` consumed before the signal compared unequal, and the NaN that signalled equals nothing."""
    assert_that(member(item, iter([2, decimal.Decimal("sNaN"), 3]))).is_equal_to(held)


class _RefusingSet(collections.abc.Set):
    """A set whose own `__contains__` raises `TypeError`, in the very words a hash refusal uses."""

    def __contains__(self, item: object) -> bool:
        raise TypeError("my own refusal: Cannot hash a signaling NaN value")

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0


@pytest.mark.parametrize(
    "item",
    [1, (1,), (decimal.Decimal("NaN"),), decimal.Decimal("sNaN"), (decimal.Decimal("sNaN"),)],
    ids=["plain", "tuple", "hashable-nan", "signalling-nan", "tuple-holding-one"],
)
def test_a_sets_own_refusal_of_a_hashable_item_is_handed_on(item):
    """Answered as absent only where the set's refusal is the item's own refusal to hash, as a NaN's is."""
    with pytest.raises(TypeError, match="my own refusal"):
        member(item, _RefusingSet())


class _RefusingMapping(collections.abc.Mapping):
    """A mapping whose own lookup raises `TypeError` in the very words a hash refusal uses."""

    def __getitem__(self, key: object) -> object:
        raise TypeError("Cannot hash a signaling NaN value")

    def __contains__(self, key: object) -> bool:
        raise TypeError("Cannot hash a signaling NaN value")

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0


def _user_dict_over(mapping: object) -> collections.UserDict:
    held = collections.UserDict()
    held.data = mapping  # ty: ignore[invalid-assignment]  # the path a trusted lookup must not assume is a dict
    return held


@pytest.mark.parametrize(
    "container",
    [
        lambda: _user_dict_over(_RefusingMapping()),
        lambda: collections.abc.KeysView(_RefusingMapping()),
        lambda: collections.abc.KeysView(_user_dict_over(_RefusingMapping())),
    ],
    ids=["user-dict-over-a-mapping", "keys-view-over-a-mapping", "keys-view-over-that-user-dict"],
)
def test_a_lookup_that_does_not_end_in_a_built_in_one_hands_its_refusal_on(container):
    """The path is followed down to a built-in dict, and a mapping of anybody's saying the same words is not one."""
    with pytest.raises(TypeError, match="Cannot hash"):
        member(decimal.Decimal("sNaN"), container())


def test_a_user_dicts_items_view_hands_the_hash_refusal_on_as_python_does():
    """The recorded boundary: the view looks a key up through `__getitem__`, whose path is not followed."""
    with pytest.raises(TypeError):
        member((decimal.Decimal("sNaN"), 1), collections.UserDict(a=1).items())


def test_a_container_that_holds_itself_is_searched_for_a_nan_once():
    looped: list = [1]
    looped.append(looped)
    mapping: dict = {"a": 1}
    mapping["self"] = mapping
    assert_that(_holds_nan(looped)).is_false()
    assert_that(_holds_nan(mapping)).is_false()
    looped.append(decimal.Decimal("sNaN"))
    assert_that(_holds_nan(looped)).is_true()


_HASHED_ASKED = {
    "set-contains": lambda nan: assert_that({1, 2}).check().contains(nan).passed,
    "set-does_not_contain": lambda nan: assert_that({1, 2}).check().does_not_contain(nan).passed,
    "dict-contains": lambda nan: assert_that({"a": 1}).check().contains(nan).passed,
    "contains_key": lambda nan: assert_that({"a": 1}).check().contains_key(nan).passed,
    "does_not_contain_key": lambda nan: assert_that({"a": 1}).check().does_not_contain_key(nan).passed,
    "set-contains_only": lambda nan: assert_that({1}).check().contains_only(nan).passed,
    "set-is_subset_of": lambda nan: assert_that([nan]).check().is_subset_of({1, 2}).passed,
    "match.contains-set": lambda nan: match.contains(nan).matches({1, 2}),
    "match.is_in-frozenset": lambda nan: match.is_in(frozenset({1})).matches(nan),
}


@pytest.mark.parametrize(
    "asked",
    [
        lambda nan: member((nan,), {(1,)}),
        lambda nan: member((nan, 1), {"a": 1}.keys()),
        lambda nan: member((nan, 1), {"a": 1}.items()),
        lambda nan: member(("a", nan), {"a": 1}.items()),
        lambda nan: member(((nan,),), {(1,)}),
        lambda nan: member((nan, []), {"a": 1}.items()),
        lambda nan: member(nan, collections.UserDict(a=1)),
        lambda nan: member(nan, collections.UserDict(a=1).keys()),
    ],
    ids=[
        "tuple-in-set",
        "tuple-in-keys",
        "key-in-items",
        "value-in-items",
        "nested-tuple",
        "key-beside-an-unhashable-value-in-items",
        "user-dict",
        "user-dict-keys",
    ],
)
def test_a_hashed_container_holds_no_tuple_holding_a_signalling_nan(asked):
    assert_that(asked(decimal.Decimal("sNaN"))).is_equal_to(asked(decimal.Decimal("NaN")))


@pytest.mark.parametrize(
    "probe",
    [
        lambda nan: ({"a": nan},),
        lambda nan: ([nan],),
        lambda nan: (collections.UserDict(a=nan),),
        lambda nan: (nan, [1]),
        lambda nan: ([1], nan),
    ],
    ids=["dict", "list", "user-dict", "nan-then-list", "list-then-nan"],
)
def test_a_probe_unhashable_without_the_nan_is_refused_as_a_quiet_one_is(probe):
    """A list or a mapping in a tuple refuses to hash whatever it holds, so the NaN changes nothing."""
    for nan in (decimal.Decimal("sNaN"), decimal.Decimal("NaN")):
        with pytest.raises(TypeError):
            member(probe(nan), {(1,)})


@pytest.mark.parametrize("asked", list(_HASHED_ASKED))
def test_a_hashed_container_holds_no_signalling_nan(asked):
    """A signalling NaN refuses to hash, so a set or a mapping's keys cannot hold one, and the answer says so."""
    signalling, quiet = decimal.Decimal("sNaN"), decimal.Decimal("NaN")
    assert_that(_HASHED_ASKED[asked](signalling)).is_equal_to(_HASHED_ASKED[asked](quiet))


@pytest.mark.parametrize("asked", list(_ASKED))
def test_a_signalling_nan_on_the_other_side_answers_as_a_quiet_one(asked):
    """Rich comparison dispatches from the left, so the NaN is asked from the argument's side as well."""
    assert_that(_ASKED[asked](1, decimal.Decimal("sNaN"))).is_equal_to(_ASKED[asked](1, decimal.Decimal("NaN")))


@pytest.mark.parametrize("asked", list(_ASKED))
@pytest.mark.parametrize("bignum", [10**400, 1], ids=["past-the-float-range", "within-it"])
def test_a_bignum_against_a_numpy_float_answers_as_against_the_float_it_holds(asked, bignum):
    numpy = pytest.importorskip("numpy")
    with numpy.errstate(all="ignore"):
        assert_that(_ASKED[asked](bignum, numpy.float32(1))).is_equal_to(_ASKED[asked](bignum, 1.0))


def _decimal_and_int64(text: str, *, decimal_first: bool) -> tuple[list[object], list[object]]:
    """The pair of a `Decimal` and a `numpy.int64(5)`, and the same pair with a Python ``5`` standing in."""
    numpy = pytest.importorskip("numpy")
    pair, stand_in = [decimal.Decimal(text), numpy.int64(5)], [decimal.Decimal(text), 5]
    if not decimal_first:
        pair.reverse()
        stand_in.reverse()
    return pair, stand_in


@pytest.mark.parametrize("asked", list(_ASKED))
@pytest.mark.parametrize("text", ["5", "1.5"], ids=["equal", "apart"])
@pytest.mark.parametrize("decimal_first", [True, False], ids=["decimal-first", "int64-first"])
def test_a_decimal_against_a_numpy_integer_answers_as_against_the_int_it_holds(asked, text, decimal_first):
    """The `Decimal` reads the integer's numerator, a `numpy` one, and raises `TypeError` rather than answering."""
    pair, stand_in = _decimal_and_int64(text, decimal_first=decimal_first)
    assert_that(_ASKED[asked](*pair)).is_equal_to(_ASKED[asked](*stand_in))


_HOLDERS_ASKED = {
    "set-contains": lambda held, item: assert_that({held}).check().contains(item).passed,
    "set-does_not_contain": lambda held, item: assert_that({held}).check().does_not_contain(item).passed,
    "set-contains_only": lambda held, item: assert_that({held}).check().contains_only(item).passed,
    "set-is_subset_of": lambda held, item: assert_that([item]).check().is_subset_of({held}).passed,
    "contains_key": lambda held, item: assert_that({held: 1}).check().contains_key(item).passed,
    "keys-contains": lambda held, item: assert_that({held: 1}.keys()).check().contains(item).passed,
    "items-contains": lambda held, item: assert_that({held: 1}.items()).check().contains((item, 1)).passed,
    "deque-contains": lambda held, item: assert_that(collections.deque([held])).check().contains(item).passed,
    "match.contains-set": lambda held, item: match.contains(item).matches({held}),
}


@pytest.mark.parametrize("asked", list(_HOLDERS_ASKED))
@pytest.mark.parametrize("text", ["5", "1.5"], ids=["equal", "apart"])
@pytest.mark.parametrize("decimal_held", [True, False], ids=["decimal-held", "int64-held"])
def test_a_set_or_a_deque_searched_for_a_decimal_against_a_numpy_integer_answers(asked, text, decimal_held):
    """Equal hashes lead a set to compare the pair, and a deque compares every element, where the `Decimal` raises."""
    (held, item), (held_stand_in, item_stand_in) = _decimal_and_int64(text, decimal_first=decimal_held)
    expected = _HOLDERS_ASKED[asked](held_stand_in, item_stand_in)
    assert_that(_HOLDERS_ASKED[asked](held, item)).is_equal_to(expected)


@pytest.mark.parametrize(
    "asked",
    [
        lambda held, item: assert_that({held}).contains(item, [1]),
        lambda held, item: assert_that({held}).contains_only(item, [1]),
    ],
    ids=["contains", "contains_only"],
)
def test_the_refusal_named_after_a_pair_a_decimal_refuses_is_the_item_refused(asked):
    """Asked again one item at a time, the `Decimal` refused ahead of the list, which is what the set refuses."""
    numpy = pytest.importorskip("numpy")
    with pytest.raises(TypeError, match="unhashable type: 'list'"):
        asked(decimal.Decimal(5), numpy.int64(5))


@pytest.mark.parametrize("asked", [match.contains, match.contains_only], ids=["contains", "contains_only"])
def test_a_matcher_reads_the_refusal_after_a_pair_a_decimal_refuses_as_no_match(asked):
    numpy = pytest.importorskip("numpy")
    assert_that(asked(numpy.int64(5), [1]).matches({decimal.Decimal(5)})).is_false()


class _EqualityBrokenInside:
    """An `__eq__` of its own that raises `TypeError`, met through a hash equal to the probe's."""

    def __eq__(self, other: object) -> bool:
        raise TypeError("my own __eq__")

    def __hash__(self) -> int:
        return 7


class _CountedHash:
    """Hashes as `_EqualityBrokenInside` does, counting how often it is asked."""

    def __init__(self) -> None:
        self.asked = 0

    def __hash__(self) -> int:
        self.asked += 1
        return 7


class _CountOfItsOwn(collections.UserList):
    """A sequence whose own `count` raises `TypeError`."""

    def count(self, item: object) -> int:
        raise TypeError("my own count")


def test_an_error_raised_inside_a_sequences_own_count_is_handed_on():
    """Counted element by element only where `count` itself refused a pair, as `member` searches."""
    with pytest.raises(TypeError, match="my own count"):
        occurrences(_CountOfItsOwn([[1]]), [[1]])


def test_an_error_raised_inside_a_hashed_lookup_is_handed_on_before_the_key_is_hashed_again():
    probe = _CountedHash()
    with pytest.raises(TypeError, match="my own __eq__"):
        member(probe, {_EqualityBrokenInside()})
    assert_that(probe.asked).is_equal_to(1)


class _RationalOfItsOwn:
    """Registered as a rational, with a numerator a `Decimal` refuses and no exact value to answer by."""

    numerator = 1.5
    denominator = 1


class _IntegralOfItsOwn:
    """Registered as an integral, with a numerator a `Decimal` refuses and a conversion of its own to 5."""

    numerator = 1.5
    denominator = 1

    def __index__(self) -> int:
        return 5

    __int__ = __index__


numbers.Rational.register(_RationalOfItsOwn)
numbers.Integral.register(_IntegralOfItsOwn)


@pytest.mark.parametrize("refused", [_RationalOfItsOwn, _IntegralOfItsOwn])
@pytest.mark.parametrize(
    "asked", ["is_equal_to", "is_equal_to-list", "contains", "is_in", "match.equal_to", "starts_with"]
)
def test_a_refusal_with_no_exact_value_to_answer_by_is_handed_on(asked, refused):
    """Only `int`'s own or a `numpy` integer's conversion is read: the value's own could answer anything."""
    with pytest.raises(TypeError, match="argument must be an integer"):
        _ASKED[asked](decimal.Decimal(5), refused())


@pytest.mark.parametrize("refused", [_RationalOfItsOwn, _IntegralOfItsOwn])
def test_a_pair_with_no_exact_value_to_order_by_is_left_unordered(refused):
    with pytest.raises(TypeError, match="must be comparable"):
        assert_that(decimal.Decimal(5)).is_less_than(refused())


class _SignallingOfItsOwn:
    """An `__eq__` that raises `InvalidOperation` of its own, with no NaN anywhere in the pair."""

    def __eq__(self, other: object) -> bool:
        raise decimal.InvalidOperation("my own signal")

    __hash__ = object.__hash__


class _OverflowingOfItsOwn:
    """An `__eq__` that overflows in its own code."""

    def __eq__(self, other: object) -> bool:
        raise OverflowError("my own overflow")

    __hash__ = object.__hash__


@pytest.mark.parametrize(
    ("value", "raised"),
    [(_SignallingOfItsOwn(), decimal.InvalidOperation), (_OverflowingOfItsOwn(), OverflowError)],
    ids=["signal", "overflow"],
)
@pytest.mark.parametrize("asked", ["is_equal_to", "is_equal_to-list", "contains", "is_in", "match.equal_to"])
def test_an_error_of_the_values_own_equality_is_handed_on(value, raised, asked):
    """Only a NaN, or a number overflowing its own conversion, makes the raise an answer."""
    with pytest.raises(raised, match="my own"):
        _ASKED[asked](value, 1)
