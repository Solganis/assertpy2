"""Property-based tests (Hypothesis) for the riskiest pure-logic surfaces.

These complement the example-based suite: 100% line coverage does not exercise the *space* of
values, which is where recursive equality, ignore/include filtering, and matcher algebra hide bugs.
Each test states an invariant and lets Hypothesis attack it with generated data; on failure the
shrunk counterexample plus assertpy2's structured ``AssertionFailure`` pinpoint the mismatch.
"""

import copy
from collections import namedtuple
from dataclasses import dataclass, replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from assertpy2 import assert_that, match

# JSON-like values: atoms plus nested lists/dicts. NaN is excluded so equality stays reflexive.
_atoms = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text()
_values = st.recursive(
    _atoms,
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=20,
)
_keys = st.text(min_size=1, max_size=5)


# --- is_equal_to / is_not_equal_to mirror Python equality ---


@settings(deadline=None)
@given(value=_values)
def test_is_equal_to_is_reflexive(value):
    assert_that(value).is_equal_to(copy.deepcopy(value))


@settings(deadline=None)
@given(left=_values, right=_values)
def test_is_equal_to_consistent_with_eq(left, right):
    if left == right:
        assert_that(left).is_equal_to(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to(right)


@settings(deadline=None)
@given(left=_values, right=_values)
def test_is_not_equal_to_is_the_inverse(left, right):
    if left != right:
        assert_that(left).is_not_equal_to(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_not_equal_to(right)


@given(left=st.sets(st.integers()), right=st.sets(st.integers()))
def test_is_equal_to_consistent_with_eq_for_sets(left, right):
    if left == right:
        assert_that(left).is_equal_to(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to(right)


# --- ignore / include selective comparison ---


@settings(deadline=None)
@given(base=st.dictionaries(_keys, _atoms, max_size=6), perturbations=st.dictionaries(_keys, _atoms, max_size=4))
def test_ignore_removes_differences(base, perturbations):
    # left keeps base values; right overlays perturbations. Ignoring exactly the perturbed keys
    # leaves both dicts identical on the remaining (base) keys, so they compare equal.
    left = dict(base)
    right = {**base, **perturbations}
    assert_that(left).is_equal_to(right, ignore=list(perturbations))


@settings(deadline=None)
@given(
    common=st.dictionaries(_keys, _atoms, min_size=1, max_size=4),
    left_extra=st.dictionaries(_keys, _atoms, max_size=3),
    right_extra=st.dictionaries(_keys, _atoms, max_size=3),
)
def test_include_compares_only_listed_keys(common, left_extra, right_extra):
    # both dicts agree on every common key; extras (outside the common set) differ but are excluded.
    included = list(common)
    left = {**{k: v for k, v in left_extra.items() if k not in common}, **common}
    right = {**{k: v for k, v in right_extra.items() if k not in common}, **common}
    assert_that(left).is_equal_to(right, include=included)


# --- matcher predicates mirror their Python semantics ---


@given(value=st.integers(), low=st.integers(), high=st.integers())
def test_between_matcher_matches_python_semantics(value, low, high):
    assert match.between(low, high).matches(value) == (low <= value <= high)


@given(value=st.integers(), boundary=st.integers())
def test_greater_than_matcher_matches_python_semantics(value, boundary):
    assert match.greater_than(boundary).matches(value) == (value > boundary)


@given(value=st.integers(), low=st.integers(), high=st.integers())
def test_satisfies_between_consistent_with_semantics(value, low, high):
    if low <= value <= high:
        assert_that(value).satisfies(match.between(low, high))
    else:
        with pytest.raises(AssertionError):
            assert_that(value).satisfies(match.between(low, high))


# --- matcher boolean algebra (& | ~) ---


@given(value=st.integers(), boundary_low=st.integers(), boundary_high=st.integers())
def test_matcher_combinators_follow_boolean_logic(value, boundary_low, boundary_high):
    matcher_a = match.greater_than(boundary_low)
    matcher_b = match.less_than(boundary_high)
    result_a = matcher_a.matches(value)
    result_b = matcher_b.matches(value)

    assert (matcher_a & matcher_b).matches(value) == (result_a and result_b)
    assert (matcher_a | matcher_b).matches(value) == (result_a or result_b)
    assert (~matcher_a).matches(value) == (not result_a)
    # de Morgan: ~(a & b) == (~a | ~b)
    assert (~(matcher_a & matcher_b)).matches(value) == ((~matcher_a) | (~matcher_b)).matches(value)


# --- collection roundtrips ---


@given(items=st.lists(st.integers()))
def test_is_length_matches_len(items):
    assert_that(items).is_length(len(items))


@given(items=st.lists(st.integers(), min_size=1))
def test_contains_every_element(items):
    assert_that(items).contains(*items)


@given(items=st.lists(st.integers()), candidate=st.integers())
def test_contains_present_iff_member(items, candidate):
    if candidate in items:
        assert_that(items).contains(candidate)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).contains(candidate)


# === Point 1: recursive comparison over dataclasses / namedtuples ===
# Exercises the riskiest code: _build_equality_diff / _sub_diff_entries (nesting, models, lists).


@dataclass
class _Inner:
    a: int
    b: str


@dataclass
class _Outer:
    inner: _Inner
    items: list[int]
    name: str


_Pair = namedtuple("_Pair", ["first", "second"])

_inners = st.builds(_Inner, a=st.integers(), b=st.text(max_size=5))
_outers = st.builds(_Outer, inner=_inners, items=st.lists(st.integers(), max_size=4), name=st.text(max_size=5))
_pairs = st.builds(_Pair, first=st.integers(), second=st.text(max_size=5))


@settings(deadline=None)
@given(left=_outers, right=_outers)
def test_dataclass_is_equal_to_consistent_with_eq(left, right):
    if left == right:
        assert_that(left).is_equal_to(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to(right)


@settings(deadline=None)
@given(value=_outers)
def test_dataclass_is_equal_to_reflexive(value):
    assert_that(value).is_equal_to(copy.deepcopy(value))


@settings(deadline=None)
@given(value=_outers, new_name=st.text(max_size=5))
def test_dataclass_ignore_removes_field_difference(value, new_name):
    other = replace(value, name=new_name)
    assert_that(value).is_equal_to(other, ignore="name")


@given(left=_pairs, right=_pairs)
def test_namedtuple_is_equal_to_consistent_with_eq(left, right):
    if left == right:
        assert_that(left).is_equal_to(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to(right)


@given(value=_pairs)
def test_namedtuple_is_equal_to_reflexive(value):
    assert_that(value).is_equal_to(copy.deepcopy(value))


# === Point 2: multiset / ordering semantics of collection assertions ===


def _is_subsequence(sub, seq):
    # shared iterator advances across the any() calls - the classic subsequence check
    iterator = iter(seq)
    return all(any(candidate == element for candidate in iterator) for element in sub)


@given(val=st.lists(st.integers(), max_size=6), expected=st.lists(st.integers(), min_size=1, max_size=6))
def test_contains_exactly_matches_list_equality(val, expected):
    if val == expected:
        assert_that(val).contains_exactly(*expected)
    else:
        with pytest.raises(AssertionError):
            assert_that(val).contains_exactly(*expected)


@given(val=st.lists(st.integers(), max_size=6), items=st.lists(st.integers(), min_size=1, max_size=6))
def test_contains_only_matches_set_equality(val, items):
    if set(val) == set(items):
        assert_that(val).contains_only(*items)
    else:
        with pytest.raises(AssertionError):
            assert_that(val).contains_only(*items)


@given(val=st.lists(st.integers(), max_size=8), items=st.lists(st.integers(), min_size=1, max_size=4))
def test_contains_sequence_matches_contiguous_slice(val, items):
    window = len(items)
    is_contiguous = any(val[index : index + window] == items for index in range(len(val) - window + 1))
    if is_contiguous:
        assert_that(val).contains_sequence(*items)
    else:
        with pytest.raises(AssertionError):
            assert_that(val).contains_sequence(*items)


@given(val=st.lists(st.integers(), max_size=8), items=st.lists(st.integers(), min_size=1, max_size=4))
def test_contains_in_order_matches_subsequence(val, items):
    if _is_subsequence(items, val):
        assert_that(val).contains_in_order(*items)
    else:
        with pytest.raises(AssertionError):
            assert_that(val).contains_in_order(*items)


@given(items=st.lists(st.integers(), max_size=10))
def test_does_not_contain_duplicates_iff_unique(items):
    if len(items) == len(set(items)):
        assert_that(items).does_not_contain_duplicates()
    else:
        with pytest.raises(AssertionError):
            assert_that(items).does_not_contain_duplicates()


@given(items=st.lists(st.integers(), max_size=10))
def test_is_sorted_matches_python_sorted(items):
    if items == sorted(items):
        assert_that(items).is_sorted()
    else:
        with pytest.raises(AssertionError):
            assert_that(items).is_sorted()


@given(items=st.lists(st.integers(), max_size=10))
def test_is_sorted_reverse_matches_python_sorted(items):
    if items == sorted(items, reverse=True):
        assert_that(items).is_sorted(reverse=True)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).is_sorted(reverse=True)


@given(items=st.lists(st.integers(), max_size=8), superset=st.lists(st.integers(), max_size=10))
def test_is_subset_of_matches_set_subset(items, superset):
    if set(items) <= set(superset):
        assert_that(items).is_subset_of(superset)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).is_subset_of(superset)


# === Point 3: nested ignore via tuple key-paths (recursion in _dict_not_equal) ===

_two_level = st.dictionaries(
    st.text(min_size=1, max_size=3),
    st.dictionaries(st.text(min_size=1, max_size=3), st.integers(), max_size=3),
    max_size=3,
)


@settings(deadline=None)
@given(base=_two_level, data=st.data())
def test_nested_ignore_removes_leaf_differences(base, data):
    paths = [(outer, leaf) for outer, inner in base.items() for leaf in inner]
    perturbed = data.draw(st.lists(st.sampled_from(paths), unique=True)) if paths else []
    right = {outer: dict(inner) for outer, inner in base.items()}
    for outer, leaf in perturbed:
        right[outer][leaf] += 1000  # ints, so always a real difference
    # ignoring exactly the perturbed leaf-paths leaves both dicts identical elsewhere
    assert_that(base).is_equal_to(right, ignore=list(perturbed))


@settings(deadline=None)
@given(base=_two_level, data=st.data())
def test_nested_include_compares_only_listed_leaves(base, data):
    paths = [(outer, leaf) for outer, inner in base.items() for leaf in inner]
    if not paths:
        return  # include needs at least one referenced path; nothing to compare on an empty dict
    included = data.draw(st.lists(st.sampled_from(paths), unique=True, min_size=1))
    included_set = set(included)
    right = {outer: dict(inner) for outer, inner in base.items()}
    for outer, leaf in paths:
        if (outer, leaf) not in included_set:
            right[outer][leaf] += 1000  # perturb only NON-included leaves (keys untouched)
    # comparing only the included leaf-paths -> equal, since those leaves are left intact
    assert_that(base).is_equal_to(right, include=list(included))
