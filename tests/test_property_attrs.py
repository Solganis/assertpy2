"""Property-based tests for attrs structural support (Hypothesis).

Mirrors the dataclass/namedtuple invariants for attrs-decorated classes: the structural comparison,
selective ignore (top-level and nested), matches_structure normalization, and the attrs diff branch
must agree with attrs' own equality and survive arbitrary generated instances. The whole module skips
when attrs is not installed.
"""

import copy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from assertpy2 import assert_that, match
from assertpy2.errors import AssertionFailure
from assertpy2.pytest_plugin import _format_diff

attrs = pytest.importorskip("attrs")


@attrs.define
class _AttrsInner:
    a: int
    b: str


@attrs.define
class _AttrsOuter:
    inner: _AttrsInner
    items: list[int]
    name: str


_attrs_inners = st.builds(_AttrsInner, a=st.integers(), b=st.text(max_size=5))
_attrs_outers = st.builds(
    _AttrsOuter, inner=_attrs_inners, items=st.lists(st.integers(), max_size=4), name=st.text(max_size=5)
)


@settings(deadline=None)
@given(left=_attrs_outers, right=_attrs_outers)
def test_attrs_is_equal_to_consistent_with_eq(left, right):
    if left == right:
        assert_that(left).is_equal_to(right)
    else:
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(left).is_equal_to(right)
        diff = exc_info.value.diff
        if diff is not None:  # the attrs diff branch must render without crashing
            assert isinstance(_format_diff(diff, color=True), str)


@settings(deadline=None)
@given(value=_attrs_outers)
def test_attrs_is_equal_to_reflexive(value):
    assert_that(value).is_equal_to(copy.deepcopy(value))


@settings(deadline=None)
@given(value=_attrs_outers, new_name=st.text(max_size=5))
def test_attrs_ignore_removes_top_level_field(value, new_name):
    other = attrs.evolve(value, name=new_name)
    assert_that(value).is_equal_to(other, ignore="name")


@settings(deadline=None)
@given(value=_attrs_outers, new_a=st.integers())
def test_attrs_ignore_reaches_into_nested_attrs(value, new_a):
    # a tuple is a single nested path: ignore the "a" field of the nested attrs instance, exercising
    # the recursive attrs.asdict path that shallow filtering used to get wrong
    other = attrs.evolve(value, inner=attrs.evolve(value.inner, a=new_a))
    assert_that(value).is_equal_to(other, ignore=("inner", "a"))


@settings(deadline=None)
@given(value=_attrs_outers)
def test_attrs_matches_structure_normalizes_instance(value):
    # StructureMatcher._as_mapping must normalize an attrs instance to its field dict, so matcher and
    # raw-value specs over its own fields always hold
    assert_that(value).matches_structure(
        {"name": match.is_instance_of(str), "items": match.is_instance_of(list), "inner": match.is_not_none()}
    )
