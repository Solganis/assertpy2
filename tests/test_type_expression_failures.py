"""Hold every assertion that takes a type expression to failing, rather than crashing, on all of them.

`isinstance`, `issubclass` and our own cause matching all accept three shapes: a class, a union, and a
tuple of either.  Each of the assertions below accepts all three when the value *matches*, because the
builtin does the matching.  Composing the failure message is ours, and reading `__name__` off the
argument works for a class and for nothing else: a tuple has never had one, and a union only grew one
in 3.14.

That combination is the worst shape a defect can take in an assertion library.  The passing path works,
so a suite stays green while the code is right, and the moment something breaks the assertion raises
`AttributeError` out of the formatter instead of reporting what went wrong.  It was found on
`is_instance_of` by an external contributor and this table is what a sweep for the same shape turned up.

Two of the methods are left out on purpose, with the reason and the exit written down in `_PENDING`.
The point of the table is the class of defect, so an omission belongs in it visibly rather than as a
method quietly missing from a list.

The version matters and is not decoration.  On 3.14 and later a union renders as the useless but
harmless `<Union>`, so half of these cases look fine there and fail on the supported floor.  Anything
added here has to be run on 3.10 as well as on the development interpreter.
"""

from __future__ import annotations

import sys

import pytest

from assertpy2 import assert_that
from assertpy2.errors import AssertionFailure


class _Person:
    pass


class _Car:
    pass


def _chained() -> None:
    try:
        raise KeyError("root")
    except KeyError as cause:
        raise RuntimeError("outer") from cause


def _instance_of(spec: object) -> None:
    assert_that(_Car()).is_instance_of(spec)  # ty: ignore[invalid-argument-type]  # the shape under test


def _instance_of_any(spec: object) -> None:
    assert_that(_Car()).is_instance_of_any(spec)  # ty: ignore[invalid-argument-type]  # the shape under test


def _subclass_of(spec: object) -> None:
    assert_that(_Car).is_subclass_of(spec)  # ty: ignore[invalid-argument-type]  # the shape under test


def _caused_by(spec: object) -> None:
    assert_that(_chained).raises(RuntimeError).when_called_with().caused_by(spec)  # ty: ignore[invalid-argument-type]  # the shape under test


def _has_root_cause(spec: object) -> None:
    assert_that(_chained).raises(RuntimeError).when_called_with().has_root_cause(spec)  # ty: ignore[invalid-argument-type]  # the shape under test


_COVERED = {
    "is_subclass_of": _subclass_of,
    "caused_by": _caused_by,
    "has_root_cause": _has_root_cause,
}

# `is_instance_of` and `is_instance_of_any` carry the same defect and are being fixed in PR #33 by the
# contributor who reported it.  Listed rather than omitted so the table describes the whole class, and
# so the day that lands is the day these two move up into `_COVERED` and this note goes away.
_PENDING = {
    "is_instance_of": _instance_of,
    "is_instance_of_any": _instance_of_any,
}

# what the builtin behind each of these accepts besides a bare class.  No member matches any subject
# above: a shape that happens to match makes the assertion pass, and a test that then expects a failure
# reports a defect in its own fixture
_SHAPES = {
    "a union": _Person | IndexError,
    "a tuple": (_Person, IndexError),
    "a tuple holding a union": (_Person | IndexError, TypeError),
}


@pytest.mark.parametrize("shape", _SHAPES.values(), ids=_SHAPES.keys())
@pytest.mark.parametrize("call", _COVERED.values(), ids=_COVERED.keys())
def test_a_failing_type_expression_fails_rather_than_crashes(call, shape) -> None:
    """The whole point: an assertion that cannot hold must say so, not raise from its own formatter."""
    with pytest.raises(AssertionFailure) as failure:
        call(shape)
    assert_that(failure.value).is_instance_of(AssertionFailure)


@pytest.mark.parametrize("shape", _SHAPES.values(), ids=_SHAPES.keys())
@pytest.mark.parametrize("call", _COVERED.values(), ids=_COVERED.keys())
def test_the_message_names_the_members_rather_than_the_container(call, shape) -> None:
    """`<Union>` and `<(<class '...'>, ...)>` are both answers a reader cannot act on."""
    with pytest.raises(AssertionFailure) as failure:
        call(shape)
    message = str(failure.value)
    assert_that(message).described_as("the failure message").contains("_Person").does_not_contain("<Union>")


@pytest.mark.parametrize("call", _PENDING.values(), ids=_PENDING.keys())
def test_the_pending_two_are_still_pending(call) -> None:
    """Fails the day PR #33 lands, which is the reminder to move them into `_COVERED`.

    A pending list nobody is forced to revisit is how an exclusion outlives the reason for it.
    """
    shape = _SHAPES["a tuple"]
    with pytest.raises(AttributeError):
        call(shape)


def test_the_floor_is_where_this_hides() -> None:
    """A union has carried `__name__` since 3.14, so the union half of the table is silent above it.

    Recorded as a test rather than as a comment because it is the reason the suite has to be run on
    3.10 before this file is believed.
    """
    has_name = hasattr(int | str, "__name__")
    assert_that(has_name).described_as("union carries __name__").is_equal_to(sys.version_info >= (3, 14))
