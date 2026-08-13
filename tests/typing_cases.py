"""Relations a type checker either catches or does not, one per line, each tagged with its own name.

Nothing here runs.  The body is never called, so the checkers read it and the interpreter does not: half
of these would raise at import, which is the point of writing them down.

`tests/test_typing_negative.py` reads the tags, runs ty, mypy and pyright over this file, and compares
what each one reported against `typing_negative_baseline.py`.  The file exists because the shipped
library advertises a typed surface, and nothing measured which incompatible operands actually reach the
checkers.  A gap nobody wrote down is a gap nobody can close on purpose.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import TYPE_CHECKING, Any, TypedDict

import numpy

from assertpy2 import assert_that, match

if TYPE_CHECKING:
    from collections import Counter
    from collections.abc import Mapping


class _Person:
    name: str = "x"


class _Colour(Enum):
    RED = "red"


class _Row(TypedDict):
    id: int
    name: str


class _Records(list[str]):
    """A container of one's own, which suites write more often than a bare `list`."""


class _OnlyFloat:
    """Convertible to a float and not a number: the gap between the capability and the runtime check."""

    def __float__(self) -> float:
        return 0.0


class _Ordered:
    """Ordered against anything and convertible to nothing, which both sides refuse alike."""

    def __lt__(self, other: object) -> bool:
        return True

    def __gt__(self, other: object) -> bool:
        return False


def _incompatible_operands() -> None:
    """Pairs where the two sides cannot be compared, whatever the runtime does with them."""
    assert_that([1, 2, 3]).contains("wrong type")  # case: contains-item-of-another-type
    assert_that(1).is_greater_than("wrong type")  # case: numeric-compared-to-text
    assert_that({"id": 1}).contains_key(3.14)  # case: mapping-key-of-another-type
    assert_that({"id": 1}).contains_value(object())  # case: mapping-value-of-another-type
    assert_that(1).is_between("a", "b")  # case: numeric-range-of-text
    assert_that([1, 2]).contains_exactly("a", "b")  # case: exact-items-of-another-type
    assert_that([1, 2]).is_subset_of("abc")  # case: collection-subset-of-text
    assert_that("text").is_length("3")  # case: length-given-text
    assert_that(b"data").starts_with("text")  # case: bytes-prefixed-with-text
    assert_that(datetime.date(2026, 1, 1)).is_before(5)  # case: date-compared-to-number
    # ordered against anything, convertible to nothing: the checker and the runtime agree to refuse it,
    # which is the half of the approximation that works
    assert_that(1).is_greater_than(_Ordered())  # case: ordered-but-not-convertible
    assert_that(1).satisfies(match.starts_with("a"))  # case: matcher-for-another-type


def _numbers_that_are_not_ordinary_numbers() -> None:
    """`complex` and `bool` are numbers whose assertion set is smaller, and the runtime already says so.

    Every line here raises `TypeError` when run. They used to type-check, because both resolved to the
    numeric protocol: `complex` is one, and `bool` is a subclass of `int`.
    """
    assert_that(1 + 2j).is_greater_than(1)  # case: complex-ordered
    assert_that(1 + 2j).is_positive()  # case: complex-signed
    assert_that(1 + 2j).is_nan()  # case: complex-nan
    assert_that(True).is_even()  # case: bool-parity
    assert_that(True).is_divisible_by(2)  # case: bool-divisibility


def _chaining_must_not_widen_what_the_value_offers() -> None:
    """A step returns `Self`, so the protocol after it is the protocol before it.

    Worth stating rather than assuming: a chain that collapsed to the generic builder would hand back
    every assertion there is, and the narrowing would hold only for the first call.
    """
    assert_that(1 + 2j).is_not_zero().is_positive()  # case: complex-widened-by-chaining
    assert_that(True).is_greater_than(0).is_even()  # case: bool-widened-by-chaining
    # `.not_` is the exception, and it is a known one: the proxy resolves any name through
    # `__getattr__`, so the negated branch accepts what the protocol does not. Closing it means a
    # second protocol per type, which is a doubling of the typed surface for one inverted call
    assert_that(1 + 2j).not_.is_greater_than(0)  # case: negation-widens-the-protocol


def _where_the_numeric_bound_is_wider_than_the_runtime() -> None:
    """`SupportsFloat` is the closest expressible approximation of what the runtime accepts, not a match.

    The runtime asks `isinstance(other, numbers.Number)`, and a numeric tower built on registration is
    invisible to a checker: `numpy.int64` is a `numbers.Number` at runtime and inherits nothing static.
    So the type says "anything that can produce a float", which lets two shapes through that the
    runtime then refuses by name.

    Both are recorded rather than fixed, because the error runs the other way from the one that hurt:
    letting through a value the runtime rejects with `given arg must be a number, but was <ndarray>` is
    a worse message, while rejecting `numpy.int64` outright was a broken test suite.
    """
    assert_that(1).is_greater_than(_OnlyFloat())  # case: convertible-but-not-a-number
    assert_that(1).is_greater_than(numpy.array([0, 1]))  # case: array-as-a-scalar-operand


def _methods_that_do_not_fit_the_value() -> None:
    """Assertions the value's own type has no business answering."""
    assert_that(_Person()).is_positive()  # case: numeric-assertion-on-an-object
    assert_that("text").is_close_to(1, 2)  # case: numeric-assertion-on-text
    assert_that({"id": 1}).has_id("no such comparison")  # case: dynamic-attribute-on-a-mapping


def _shapes_other_people_write(
    typed: _Row,
    mapping: Mapping[str, int],
    counted: Counter[str],
    mixed: list[int | str],
    heterogeneous: tuple[int, str],
    members: set[int],
    by_enum: dict[_Colour, int],
    payloads: list[dict[str, Any]],
    subclassed: _Records,
    loose: list[Any],
    stamp: datetime.datetime,
) -> None:
    """Container and mapping shapes from real suites, none of which this library wrote.

    An author's idea of ordinary usage is narrower than a user's, which is how a numeric bound written
    as `float | Decimal | Fraction` shipped and rejected `numpy.int64`.  These are the shapes probed
    afterwards: every one of them type-checks, and they are here so that stays true.
    """
    assert_that(typed).contains_key("id")  # case: valid-typed-dict-key
    assert_that(mapping).contains_key("id")  # case: valid-mapping-protocol-key
    assert_that(counted).contains_key("word")  # case: valid-counter-key
    assert_that(by_enum).contains_key(_Colour.RED)  # case: valid-enum-key
    assert_that(mixed).contains(1)  # case: valid-union-element
    assert_that(heterogeneous).contains("a")  # case: valid-heterogeneous-tuple
    assert_that(members).contains(1)  # case: valid-set-member
    assert_that(payloads).contains({"id": 1})  # case: valid-nested-payload
    assert_that(subclassed).contains("row")  # case: valid-list-subclass
    assert_that(loose).contains("whatever")  # case: valid-any-element
    assert_that(stamp).is_before(stamp)  # case: valid-datetime-against-datetime
    assert_that(stamp.date()).is_after(datetime.date(2020, 1, 1))  # case: valid-date-from-datetime


def _relations_that_must_keep_working() -> None:
    """The other half of the measurement: tightening a signature must not cost these.

    Every one is ordinary usage, and a checker rejecting any of them is a defect in the typing rather
    than a success.
    """
    assert_that([1, 2, 3]).contains(2)  # case: valid-contains-an-item
    assert_that([1, 2, 3]).contains(match.greater_than(1))  # case: valid-contains-a-matcher
    assert_that(1).is_greater_than(1.5)  # case: valid-int-compared-to-float
    assert_that({"id": 1}).contains_key("id")  # case: valid-mapping-key
    assert_that("abc").contains("a")  # case: valid-substring
    assert_that(b"data").starts_with(b"da")  # case: valid-bytes-prefix
    assert_that(1).satisfies(lambda value: value > 0)  # case: valid-predicate
    assert_that([1, 2, 3]).is_length(3)  # case: valid-length
    assert_that(datetime.date(2026, 1, 1)).is_before(datetime.date(2026, 2, 1))  # case: valid-date-order
    assert_that(_Person()).has_name("x")  # case: valid-dynamic-attribute
    assert_that(1).is_greater_than(0.5)  # case: valid-int-against-float
    assert_that(1.0).is_greater_than(0)  # case: valid-float-against-int
    assert_that(Decimal("1.1")).is_greater_than(Decimal("1.0"))  # case: valid-decimal-order
    assert_that(Fraction(3, 2)).is_greater_than(Fraction(1, 2))  # case: valid-fraction-order
    assert_that(1 + 2j).is_zero()  # case: valid-complex-zero
    assert_that(True).is_greater_than(0)  # case: valid-bool-compared
    assert_that(1).is_equal_to(True)  # case: valid-int-equals-bool
    assert_that(1 + 2j).is_equal_to(1 + 2j)  # case: valid-complex-equality
    assert_that(1 + 2j).is_instance_of(complex)  # case: valid-complex-instance
    assert_that(1 + 2j).satisfies(lambda value: value == 0)  # case: valid-complex-predicate
    assert_that(True).is_true()  # case: valid-bool-truth
    # the regression this half of the file exists for: the numeric bound was first written as a list of
    # types and rejected `numpy.int64`, which this library documents support for and which compares
    # happily at runtime. Named as a capability now, so anything that can produce a float is accepted
    assert_that(1).is_greater_than(numpy.int64(0))  # case: valid-numpy-integer
    assert_that(1.5).is_greater_than(numpy.float64(0))  # case: valid-numpy-float
    assert_that(1).is_close_to(numpy.float64(1), numpy.float64(0.1))  # case: valid-numpy-tolerance
    assert_that(1).is_greater_than(numpy.int32(0))  # case: valid-numpy-int32
    assert_that(1).is_greater_than(numpy.uint64(0))  # case: valid-numpy-uint64
    assert_that(1.5).is_greater_than(numpy.float32(0))  # case: valid-numpy-float32
