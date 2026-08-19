"""Property-based tests (Hypothesis) for the riskiest pure-logic surfaces.

These complement the example-based suite: 100% line coverage does not exercise the *space* of
values, which is where recursive equality, ignore/include filtering, and matcher algebra hide bugs.
Each test states an invariant and lets Hypothesis attack it with generated data; on failure the
shrunk counterexample plus assertpy2's structured ``AssertionFailure`` pinpoint the mismatch.
"""

import ast
import copy
import datetime
import json
import pathlib
import re
import warnings
from collections import Counter, namedtuple
from collections.abc import Mapping
from dataclasses import dataclass, replace
from itertools import pairwise
from types import MappingProxyType

import pytest
from hypothesis import assume, find, given, settings
from hypothesis import strategies as st
from hypothesis.errors import HypothesisWarning

import assertpy2._engine._typing
import assertpy2.assertpy
from assertpy2 import assert_conforms, assert_that, match, soft_assertions
from assertpy2._clustering import _VALUE_LIMIT, Observation, Signature, _shown, clusters, render, stable_repr
from assertpy2._dangling import findings as dangling_findings
from assertpy2._engine._compare import _EQ_ATOMIC
from assertpy2._engine._contract import contract_drift, shape, shape_diff
from assertpy2._engine._diff import _build_equality_diff, _ordered_keys, _sub_diff_entries
from assertpy2._engine._equality import values_differ
from assertpy2._engine._introspection import is_mapping_like
from assertpy2._engine._membership import missing_items
from assertpy2._engine._ordering import compare, holds
from assertpy2._engine._path import _ROOT
from assertpy2._engine._require import refuse
from assertpy2._engine._size import length_of
from assertpy2._engine._text import contains as text_contains
from assertpy2._engine._text import ends_with as text_ends_with
from assertpy2._engine._text import starts_with as text_starts_with
from assertpy2._hints import diagnose
from assertpy2._inline import _format_literal, is_literalable
from assertpy2._snapshot_codec import _Decoder, _Encoder
from assertpy2.assertpy import _format_soft_errors
from assertpy2.errors import AssertionFailure, DiffEntry, DiffResult, _diff_sides, _disambiguated
from assertpy2.outcome import AssertionOutcome
from assertpy2.pytest_plugin import _format_diff
from tests.group_compat import BaseExceptionGroup, ExceptionGroup, needs_groups

try:  # the OpenAPI properties need the [json] extra; the rest of the file does not
    import jsonschema  # noqa: F401  # presence gate only

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover - exercised only in an env without the extra
    _HAS_JSONSCHEMA = False

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


# === Diff well-formedness: any unequal pair yields a renderable, well-formed DiffResult ===
# Fuzzes the whole failure path - _build_equality_diff, the disambiguating message, and the plugin's
# colored renderer - so no generated structure can make the diff crash or emit a non-string path.


@settings(deadline=None)
@given(left=_values, right=_values)
def test_diff_is_well_formed_for_unequal_values(left, right):
    if left == right:
        return
    with pytest.raises(AssertionFailure) as exc_info:
        assert_that(left).is_equal_to(right)
    failure = exc_info.value
    assert isinstance(str(failure), str)  # message (incl. _disambiguated) renders without raising
    diff = failure.diff
    if diff is not None:
        assert isinstance(diff.kind, str)
        assert all(isinstance(entry.path, str) for entry in diff.entries)
        assert isinstance(_format_diff(diff, color=True), str)  # plugin renderer survives any diff


@settings(deadline=None)
@given(left=_outers, right=_outers)
def test_diff_is_well_formed_for_unequal_dataclasses(left, right):
    if left == right:
        return
    with pytest.raises(AssertionFailure) as exc_info:
        assert_that(left).is_equal_to(right)
    diff = exc_info.value.diff
    if diff is not None:
        assert all(isinstance(entry.path, str) for entry in diff.entries)
        assert isinstance(_format_diff(diff, color=True), str)


# === Diff completeness: a failing sequence accounts for every one of its positions ===
# Well-formedness above says the diff renders.  This says it is complete, which is a claim about the
# layer underneath: pairing decides which element is compared with which, and the walk only ever sees
# the pairs handed to it.  A pair the pairing calls equal is never examined, so a wrong match takes a
# real difference out of the diff and out of the message's elision at once, and the failure names a
# smaller difference than the one that caused it.  Two defects of exactly that shape shipped, both
# because difflib's notion of a match is not this library's: keyed on reprs it matches values that
# print alike, keyed on the values it matches on ``==``, and every verdict here is reached with ``!=``.
#
# The atoms below are chosen for that: a homogeneous generator only exercises the half everyone sees.


class _Twin:
    """Unhashable and printed the same whatever it holds, so an alignment can only key on the repr."""

    __hash__ = None

    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return isinstance(other, _Twin) and self.value == other.value

    def __repr__(self):
        return "<twin>"


class _Split:
    """Hashable, with ``==`` and ``!=`` that disagree: difflib reads the first, the walk the second."""

    def __init__(self, value):
        self.value = value

    def __hash__(self):
        return 7

    def __eq__(self, other):
        return isinstance(other, _Split)

    def __ne__(self, other):
        return not isinstance(other, _Split) or self.value != other.value

    def __repr__(self):
        return f"_Split({self.value})"


_drift_atoms = st.one_of(
    st.integers(min_value=-2, max_value=2),
    st.sampled_from([0.0, 1.0, 2.0, True, False, None, "", "a", "b"]),
    st.builds(float, st.just("nan")),
    st.builds(_Twin, st.integers(min_value=0, max_value=2)),
    st.builds(_Split, st.integers(min_value=0, max_value=2)),
    st.lists(st.integers(min_value=0, max_value=2), max_size=2),
    st.dictionaries(st.sampled_from(["id", "name"]), st.integers(min_value=0, max_value=2), max_size=2),
)


@st.composite
def _drifted_pair(draw):
    """Two sequences sharing a run, which is the only shape that reaches the alignment at all.

    Pairing by index is used whenever the two are the same length, so a strategy drawing both sides
    independently spends most of its examples never touching the code under test.  Here one side is
    the other with a run inserted and a few positions rewritten, which is what a shifted payload looks
    like and what makes a matched run long enough for a wrong match inside it to hide something.

    Drawing every element from one small pool is load-bearing rather than a way to get repeats.  A dict
    lookup settles identity before it asks ``==``, so difflib matches a pair like ``nan`` against ``nan``
    only when both sides hold the same object - and that pair, matched and then never compared, is the
    whole failure this is looking for.  Redraw the elements per side and the case stops being generated.
    """
    element = st.sampled_from(draw(st.lists(_drift_atoms, min_size=1, max_size=3)))
    base = draw(st.lists(element, min_size=1, max_size=6))
    cut = draw(st.integers(min_value=0, max_value=len(base)))
    expected = [*base[:cut], *draw(st.lists(element, max_size=3)), *base[cut:]]
    for index in draw(st.lists(st.integers(min_value=0, max_value=len(expected) - 1), max_size=2)):
        expected[index] = draw(element)
    return (expected, base) if draw(st.booleans()) else (base, expected)


_pairs_of_sequences = st.one_of(
    st.tuples(st.lists(_drift_atoms, max_size=6), st.lists(_drift_atoms, max_size=6)),
    _drifted_pair(),
)


def _sequence_diff_of(actual, expected):
    """The sequence diff of a failing pair, or ``None`` when there is nothing of that shape to read."""
    try:
        assert_that(actual).is_equal_to(expected)
    except AssertionFailure as failure:
        diff = failure.diff
    else:
        return None
    return diff if diff is not None and diff.kind == "sequence" else None


def _edits(entries):
    """Which actual indices the diff dropped, which expected indices it added, and which it named.

    Only a one-step entry can be one-sided about the sequence itself: deeper down, ``absent`` belongs
    to the nested key or index it names, and the position above it was compared like any other.
    """
    dropped, added, named = set(), set(), set()
    for entry in entries:
        assert entry.steps, "a sequence entry has to say where it sits"
        step = entry.steps[0]
        assert step.kind == "index"
        if len(entry.steps) == 1 and entry.absent == "expected":
            dropped.add(step.value)
        elif len(entry.steps) == 1 and entry.absent == "actual":
            added.add(step.value)
        else:
            named.add(step.value)
    return dropped, added, named


@settings(deadline=None)
@given(pair=_pairs_of_sequences)
def test_a_sequence_diff_pairs_off_every_position_it_leaves_unnamed(pair):
    actual, expected = pair
    diff = _sequence_diff_of(actual, expected)
    if diff is None:
        return
    dropped, added, named = _edits(diff.entries)
    kept_actual = [index for index in range(len(actual)) if index not in dropped]
    kept_expected = [index for index in range(len(expected)) if index not in added]
    assert len(kept_actual) == len(kept_expected)  # what is left over on each side has to pair up
    unaccounted = [
        (left, right)
        for left, right in zip(kept_actual, kept_expected, strict=True)
        if left not in named and actual[left] != expected[right]
    ]
    assert unaccounted == []


@settings(deadline=None)
@given(pair=_pairs_of_sequences)
def test_a_one_sided_sequence_entry_carries_the_element_it_names(pair):
    actual, expected = pair
    diff = _sequence_diff_of(actual, expected)
    if diff is None:
        return
    for entry in diff.entries:
        if len(entry.steps) != 1 or entry.absent is None:
            continue
        index = entry.steps[0].value
        if entry.absent == "expected":
            assert entry.actual is actual[index]
            assert entry.expected is None
        else:
            assert entry.expected is expected[index]
            assert entry.actual is None


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


# === Multiset semantics of contains_exactly_in_any_order ===


@given(val=st.lists(st.integers(), max_size=6), expected=st.lists(st.integers(), min_size=1, max_size=6))
def test_contains_exactly_in_any_order_matches_multiset_equality(val, expected):
    if Counter(val) == Counter(expected):
        assert_that(val).contains_exactly_in_any_order(*expected)
    else:
        with pytest.raises(AssertionError):
            assert_that(val).contains_exactly_in_any_order(*expected)


@given(items=st.lists(st.integers(), min_size=1, max_size=6), data=st.data())
def test_contains_exactly_in_any_order_is_permutation_invariant(items, data):
    shuffled = data.draw(st.permutations(items))
    assert_that(items).contains_exactly_in_any_order(*shuffled)


@given(items=st.lists(st.lists(st.integers(), max_size=3), min_size=1, max_size=5), data=st.data())
def test_contains_exactly_in_any_order_unhashable_permutation_invariant(items, data):
    # lists as items force the quadratic non-Counter fallback
    shuffled = data.draw(st.permutations(items))
    assert_that(items).contains_exactly_in_any_order(*shuffled)


# === Bipartite pairing of satisfies_exactly_in_any_order ===
# With pure equality matchers a perfect pairing exists iff the two multisets are equal,
# so Python's Counter is an independent oracle for the Kuhn matching implementation.


@given(val=st.lists(st.integers(0, 5), max_size=5), expected=st.lists(st.integers(0, 5), min_size=1, max_size=5))
def test_satisfies_exactly_in_any_order_equality_matchers_match_multisets(val, expected):
    matchers = [match.equal_to(item) for item in expected]
    if Counter(val) == Counter(expected):
        assert_that(val).satisfies_exactly_in_any_order(*matchers)
    else:
        with pytest.raises(AssertionError):
            assert_that(val).satisfies_exactly_in_any_order(*matchers)


@given(items=st.lists(st.integers(), min_size=1, max_size=5), data=st.data())
def test_satisfies_exactly_in_any_order_is_permutation_invariant(items, data):
    shuffled = data.draw(st.permutations(items))
    assert_that(items).satisfies_exactly_in_any_order(*[match.equal_to(item) for item in shuffled])


# === Relational size family mirrors len() comparisons ===

_bounds = st.tuples(st.integers(0, 10), st.integers(0, 10)).map(sorted)


@given(items=st.lists(st.integers(), max_size=10), size=st.integers(0, 10))
def test_has_size_greater_than_matches_len_semantics(items, size):
    if len(items) > size:
        assert_that(items).has_size_greater_than(size)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).has_size_greater_than(size)


@given(items=st.lists(st.integers(), max_size=10), size=st.integers(0, 10))
def test_has_size_less_than_matches_len_semantics(items, size):
    if len(items) < size:
        assert_that(items).has_size_less_than(size)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).has_size_less_than(size)


@given(items=st.lists(st.integers(), max_size=10), bounds=_bounds)
def test_has_size_between_matches_len_semantics(items, bounds):
    low, high = bounds
    if low <= len(items) <= high:
        assert_that(items).has_size_between(low, high)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).has_size_between(low, high)


@given(items=st.lists(st.integers(), max_size=10), bounds=_bounds)
def test_is_length_between_matches_len_semantics(items, bounds):
    low, high = bounds
    if low <= len(items) <= high:
        assert_that(items).is_length_between(low, high)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).is_length_between(low, high)


# === String normalization sugar ===

_ascii_text = st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126))


@given(text=st.text(), data=st.data())
def test_inserting_whitespace_keeps_ignoring_whitespace_equality(text, data):
    position = data.draw(st.integers(0, len(text)))
    whitespace = data.draw(st.sampled_from([" ", "\t", "\n", "  ", "\r\n"]))
    padded = text[:position] + whitespace + text[position:]
    assert_that(padded).is_equal_to_ignoring_whitespace(text)


@given(left=st.text(), right=st.text())
def test_is_equal_to_ignoring_whitespace_matches_normalization(left, right):
    if "".join(left.split()) == "".join(right.split()):
        assert_that(left).is_equal_to_ignoring_whitespace(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to_ignoring_whitespace(right)


# ascii-only: for unicode, lower(swapcase(s)) may differ from lower(s) (e.g. 'ß'.swapcase() == 'SS'),
# which is a property of Python casing rules rather than of the assertion under test
@given(text=_ascii_text.filter(lambda s: len(s) >= 1), data=st.data())
def test_starts_with_ignoring_case_accepts_case_mangled_prefix(text, data):
    prefix_length = data.draw(st.integers(1, len(text)))
    assert_that(text).starts_with_ignoring_case(text[:prefix_length].swapcase())


@given(text=_ascii_text.filter(lambda s: len(s) >= 1), data=st.data())
def test_ends_with_ignoring_case_accepts_case_mangled_suffix(text, data):
    suffix_length = data.draw(st.integers(1, len(text)))
    assert_that(text).ends_with_ignoring_case(text[-suffix_length:].swapcase())


# === Snapshot typed-codec round-trip ===
# The codec is exercised directly (no files): encode -> decode must reproduce an equal value.

_snapshot_zones = st.sampled_from(
    [
        None,
        datetime.timezone.utc,
        datetime.timezone(datetime.timedelta(hours=5, minutes=30)),
        datetime.timezone(datetime.timedelta(hours=-8)),
        datetime.timezone(datetime.timedelta(minutes=5, seconds=30)),  # sub-minute offsets are legal since 3.7
    ]
)
_snapshot_codec_values = (
    st.dates()
    | st.times(timezones=_snapshot_zones)
    | st.decimals(allow_nan=False)
    | st.binary(max_size=64)
    | st.datetimes(
        min_value=datetime.datetime(1900, 1, 1),
        max_value=datetime.datetime(9999, 12, 30),
        timezones=_snapshot_zones,
    )
)


@settings(deadline=None)
@given(value=_snapshot_codec_values)
def test_snapshot_codec_roundtrip(value):
    encoded = json.dumps({"v": value}, cls=_Encoder)
    decoded = json.loads(encoded, cls=_Decoder)
    assert_that(decoded["v"]).is_equal_to(value)


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


# --- contract shape / drift (assert_conforms exact + matches_contract_snapshot) ---

# JSON-like values including NaN/inf floats: contract shape must survive them (they are just "number").
_json_atoms = st.none() | st.booleans() | st.integers() | st.floats() | st.text()
_json = st.recursive(_json_atoms, lambda children: st.lists(children) | st.dictionaries(_keys, children), max_leaves=20)


def _canon(value):
    """Replace every scalar leaf with a fixed representative of its category, preserving structure."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return 0
    if isinstance(value, str):
        return ""
    if isinstance(value, dict):
        return {key: _canon(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canon(item) for item in value]
    return value  # None


@settings(deadline=None)
@given(value=_json)
def test_shape_never_drifts_from_itself(value):
    # P1: a value's shape is identical to itself - the snapshot never fails on unchanged structure
    assert_that(shape_diff(shape(value), shape(value))).is_empty()


@settings(deadline=None)
@given(value=_json)
def test_shape_ignores_leaf_values(value):
    # P2 (value-tolerance): rewriting every leaf with a same-category value leaves the shape unchanged
    assert_that(shape(value)).is_equal_to(shape(_canon(value)))
    assert_that(shape_diff(shape(value), shape(_canon(value)))).is_empty()


@settings(deadline=None)
@given(left=_json, right=_json)
def test_shape_diff_is_total(left, right):
    # P3 (totality): shape and shape_diff never raise on any pair of JSON-like values
    shape_diff(shape(left), shape(right))


@settings(deadline=None)
@given(number=st.integers() | st.floats())
def test_numbers_share_one_category(number):
    # P4: int and float (incl NaN/inf) collapse to one category, so 5 vs 5.0 is never drift
    assert_that(shape(number)).is_equal_to("number")


@settings(deadline=None)
@given(value=_json)
def test_duplicate_elements_merge_to_one(value):
    # P5: two identical elements merge to a single element shape (merge is reflexive)
    assert_that(shape([value, value])).is_equal_to(shape([value]))


@settings(deadline=None)
@given(ident=st.integers(), name=st.text(), tags=st.lists(st.text()))
def test_conforming_dump_has_no_drift(ident, name, tags):
    # P7: a model's own dumped instance never drifts from the model
    pytest.importorskip("pydantic", reason="pydantic not installed")
    from pydantic import BaseModel

    class Item(BaseModel):
        id: int
        name: str
        tags: list[str]

    assert_that(contract_drift(Item(id=ident, name=name, tags=tags).model_dump(), Item)).is_empty()


@settings(deadline=None)
@given(payload=st.dictionaries(_keys, _json_atoms), extra_key=st.text(min_size=1))
def test_undeclared_key_is_always_detected(payload, extra_key):
    # P8: any key the model does not declare surfaces as drift
    pytest.importorskip("pydantic", reason="pydantic not installed")
    from pydantic import BaseModel

    class Item(BaseModel):
        id: int

    assume(extra_key != "id")
    assert_that(contract_drift({**payload, extra_key: 1}, Item)).contains(extra_key)


@settings(deadline=None)
@given(payload=st.dictionaries(_keys, _json))
def test_contract_drift_is_total(payload):
    # P9: contract_drift never raises on an arbitrary dict payload, even through sub-model recursion
    pytest.importorskip("pydantic", reason="pydantic not installed")
    from pydantic import BaseModel

    class Sub(BaseModel):
        x: int

    class Item(BaseModel):
        id: int
        sub: Sub
        items: list[Sub]

    contract_drift(payload, Item)


# --- Invariants for the failure-diagnostics, soft-report, and list-conformance work ---

_collidable = st.sampled_from([0, 1, 2, "0", "1", "2", 1.0, 2.0, "1.0", "2.0", True, False, None, "None", "True"])


@settings(deadline=None)
@given(left=_collidable, right=_collidable)
def test_disambiguated_distinguishes_colliding_reprs(left, right):
    # two unequal values that render to the same repr stay distinguishable once tagged by type
    shown_left, shown_right = _disambiguated(left, right)
    if str(left) == str(right) and type(left) is not type(right):
        assert_that(shown_left).is_not_equal_to(shown_right)


_soft_groups = st.none() | st.sampled_from(["Headers", "Body"])
_soft_specs = st.lists(st.tuples(_soft_groups, st.booleans(), st.booleans()), min_size=1, max_size=8)


@settings(deadline=None)
@given(specs=_soft_specs)
def test_soft_report_numbers_every_failure_sequentially(specs):
    # the aggregated report carries every message once, numbered 1..N across any grouping, and the
    # numbering must survive the diff lines that a structured failure adds under its entry
    entries = [
        AssertionOutcome(
            group=group,
            location=(f"file{index}.py", index) if located else None,
            message=f"failure message {index}",
            diff=DiffResult(kind="dict", entries=[DiffEntry(path=f"field{index}", actual=index, expected=-index)])
            if diffed
            else None,
        )
        for index, (group, located, diffed) in enumerate(specs)
    ]
    report = _format_soft_errors(entries)
    for outcome in entries:
        assert_that(report).contains(outcome.message)
    for number in range(1, len(entries) + 1):
        assert_that(report).contains(f"{number}. ")


@settings(deadline=None)
@given(specs=_soft_specs)
def test_soft_report_shows_each_diff_path_under_its_own_entry(specs):
    entries = [
        AssertionOutcome(
            group=group,
            message=f"failure message {index}",
            diff=DiffResult(kind="dict", entries=[DiffEntry(path=f"field{index}", actual=index, expected=-index)])
            if diffed
            else None,
        )
        for index, (group, located, diffed) in enumerate(specs)
    ]
    report = _format_soft_errors(entries)
    for index, outcome in enumerate(entries):
        if outcome.diff is not None:
            assert_that(report).contains(f"field{index}: {index} != {-index}")


_field = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=6)


@settings(deadline=None)
@given(ids=st.lists(st.integers(), max_size=6), suffix=st.text(max_size=4))
def test_assert_conforms_each_preserves_length_and_order(ids, suffix):
    # each=True validates every item, preserving count and order (coercion applied per element)
    pytest.importorskip("pydantic", reason="pydantic not installed")
    from pydantic import BaseModel

    class Item(BaseModel):
        id: int
        name: str

    payloads = [{"id": ident, "name": f"{suffix}{ident}"} for ident in ids]
    validated = assert_conforms(payloads, Item, each=True).val
    assert_that(validated).is_length(len(ids))
    assert_that([item.id for item in validated]).is_equal_to(ids)


@settings(deadline=None)
@given(ids=st.lists(st.integers(), min_size=1, max_size=5), position=st.integers(), extra=_field)
def test_assert_conforms_each_exact_reports_indexed_drift(ids, position, extra):
    # an undeclared field on element i surfaces as drift path [i].field, tying each=exact to P8
    pytest.importorskip("pydantic", reason="pydantic not installed")
    from pydantic import BaseModel

    class Item(BaseModel):
        id: int

    assume(extra != "id")
    index = position % len(ids)
    payloads = [{"id": ident} for ident in ids]
    payloads[index] = {**payloads[index], extra: 1}
    with pytest.raises(AssertionError) as exc_info:
        assert_conforms(payloads, Item, each=True, exact=True)
    assert_that(str(exc_info.value)).contains(f"[{index}].{extra}")


_chain_types = st.sampled_from([ValueError, KeyError, TypeError, RuntimeError, IndexError, AttributeError])


@settings(deadline=None)
@given(chain=st.lists(_chain_types, min_size=1, max_size=6))
def test_has_root_cause_walks_to_the_deepest_link(chain):
    # a __cause__ chain of arbitrary depth: has_root_cause finds its last link, whatever the depth
    errors = [exc_type(f"e{index}") for index, exc_type in enumerate(chain)]
    for outer, inner in pairwise(errors):
        outer.__cause__ = inner

    def raise_head():
        raise errors[0]

    assert_that(raise_head).raises(chain[0]).when_called_with().has_root_cause(chain[-1])


@settings(deadline=None)
@given(
    common=st.dictionaries(_keys, st.integers(), max_size=5),
    nulls=st.dictionaries(_keys, st.integers(), max_size=3),
)
def test_ignore_null_skips_every_expected_none_key(common, nulls):
    # any key the expected leaves None accepts any actual value; the rest must still match
    expected = {**common, **dict.fromkeys(nulls, None)}
    actual = {**common, **nulls}
    assert_that(actual).is_equal_to(expected, ignore_null=True)


# --- OpenAPI response contracts: conformance is total and independent of the spec version ---

_OPENAPI_TYPES = {"string": st.text(max_size=5), "integer": st.integers(), "boolean": st.booleans()}


@st.composite
def _openapi_operation(draw, min_required=0):
    """A generated object schema, a body built to satisfy it, and one required key to drop.

    ``min_required`` pins the schema to at least that many required keys, for the tests whose whole
    point is a missing one: filtering those cases out afterwards would throw away half the examples.
    """
    names = draw(st.lists(st.text(alphabet="abcdef", min_size=1, max_size=3), min_size=1, max_size=4, unique=True))
    types = {name: draw(st.sampled_from(sorted(_OPENAPI_TYPES))) for name in names}
    required = sorted(draw(st.lists(st.sampled_from(names), unique=True, min_size=min_required)))
    body = {name: draw(_OPENAPI_TYPES[kind]) for name, kind in types.items()}
    schema = {
        "type": "object",
        "required": required,
        "properties": {name: {"type": kind} for name, kind in types.items()},
    }
    dropped = draw(st.sampled_from(required)) if required else None
    return schema, body, dropped


def _spec_30(schema):
    content = {"application/json": {"schema": schema}}
    return {"openapi": "3.0.3", "paths": {"/r": {"get": {"responses": {"200": {"content": content}}}}}}


def _spec_20(schema):
    operation = {"produces": ["application/json"], "responses": {"200": {"schema": schema}}}
    return {"swagger": "2.0", "paths": {"/r": {"get": operation}}}


def _conforms(spec, body):
    try:
        assert_that(body).conforms_to_openapi(spec, "/r", "get")
    except AssertionFailure:
        return False
    return True


@pytest.mark.skipif(not _HAS_JSONSCHEMA, reason="needs the [json] extra")
@settings(deadline=None)
@given(operation=_openapi_operation())
def test_a_body_built_from_the_schema_always_conforms(operation):
    schema, body, _dropped = operation
    assert_that(_conforms(_spec_30(schema), body)).is_true()


@pytest.mark.skipif(not _HAS_JSONSCHEMA, reason="needs the [json] extra")
@settings(deadline=None)
@given(operation=_openapi_operation(min_required=1))
def test_dropping_a_required_key_is_always_detected(operation):
    schema, body, dropped = operation
    broken = {name: value for name, value in body.items() if name != dropped}
    assert_that(_conforms(_spec_30(schema), broken)).is_false()


@pytest.mark.skipif(not _HAS_JSONSCHEMA, reason="needs the [json] extra")
@settings(deadline=None)
@given(operation=_openapi_operation())
def test_swagger_2_and_openapi_3_agree_on_every_verdict(operation):
    # the two spec versions reach the schema by different routes, so their verdicts must not diverge
    schema, body, dropped = operation
    assert_that(_conforms(_spec_20(schema), body)).is_equal_to(_conforms(_spec_30(schema), body))
    if dropped is not None:
        broken = {name: value for name, value in body.items() if name != dropped}
        assert_that(_conforms(_spec_20(schema), broken)).is_equal_to(_conforms(_spec_30(schema), broken))


# --- inline snapshots: a recorded literal round-trips through the source it is written into ---

_literal_atoms = (
    st.none() | st.booleans() | st.integers() | st.text(max_size=5) | st.floats(allow_nan=False, allow_infinity=False)
)
_literals = st.recursive(
    _literal_atoms,
    lambda children: (
        st.lists(children, max_size=4)
        | st.tuples(children)
        | st.dictionaries(st.text(max_size=3), children, max_size=4)
        | st.frozensets(st.integers(), max_size=4)
    ),
    max_leaves=8,
)


@settings(deadline=None)
@given(value=_literals, column=st.integers(min_value=0, max_value=40))
def test_a_recorded_inline_literal_round_trips(value, column):
    # matches_inline writes this text into the test source, so Python's own evaluation is the oracle.
    # eval is safe here: the input is the literal this very call just rendered, never outside data.
    assume(is_literalable(value))
    restored = eval(_format_literal(value, column))
    assert_that(restored).is_equal_to(value)


# --- string diffs: every caret row explains the content row above it ---


@st.composite
def _line_and_edit(draw):
    """A line plus a one-character edit of it, so the renderer has an intra-line change to point at.

    Two unrelated random strings would mostly be empty or share nothing, which never produces a caret
    row and leaves the property vacuous.
    """
    # every category str.splitlines() treats as a break is out, or the row extraction below over-splits
    printable = st.characters(exclude_categories=("Cc", "Cs", "Zl", "Zp"))
    base = draw(st.text(alphabet=printable, min_size=1, max_size=30))
    index = draw(st.integers(min_value=0, max_value=len(base) - 1))
    replacement = draw(printable)
    assume(base[index] != replacement)
    return base, base[:index] + replacement + base[index + 1 :]


@settings(deadline=None)
@given(pair=_line_and_edit())
def test_string_diff_shows_both_sides_with_anchored_carets(pair):
    left, right = pair
    rendered = _format_diff(DiffResult(kind="string", entries=[DiffEntry(path="line 1", actual=left, expected=right)]))
    rows = rendered.splitlines()[2:]  # past the "diff (string):" header and the path row
    # both sides must be spelled out: a renderer that drops one leaves the reader guessing
    assert_that([row[6:] for row in rows if row.startswith("    - ")]).is_equal_to([left])
    assert_that([row[6:] for row in rows if row.startswith("    + ")]).is_equal_to([right])
    # a caret row only ever annotates the content row directly above it
    assert_that(rows[0].startswith("    ?")).is_false()
    for previous, row in pairwise(rows):
        if row.startswith("    ?"):
            assert_that(previous.startswith(("    - ", "    + "))).is_true()


# --- collection pipeline: each transform mirrors its Python counterpart ---


@settings(deadline=None)
@given(items=st.lists(st.integers(), max_size=12))
def test_mapped_mirrors_the_comprehension(items):
    assert_that(assert_that(items).mapped(lambda item: item * 2).val).is_equal_to([item * 2 for item in items])


@settings(deadline=None)
@given(items=st.lists(st.integers(), max_size=12), threshold=st.integers())
def test_filtered_on_mirrors_the_comprehension(items, threshold):
    def keeps(item):
        return item > threshold

    assert_that(assert_that(items).filtered_on(keeps).val).is_equal_to([item for item in items if keeps(item)])


@settings(deadline=None)
@given(items=st.lists(st.integers(), max_size=12))
def test_flat_mapped_equals_flatten_of_map(items):
    def expand(item):
        return [item, -item]

    assert_that(assert_that(items).flat_mapped(expand).val).is_equal_to(
        [part for item in items for part in expand(item)]
    )


@settings(deadline=None)
@given(items=st.lists(st.integers(), min_size=1, max_size=12), offset=st.integers(min_value=0, max_value=100))
def test_element_first_and_last_agree_with_indexing(items, offset):
    index = offset % len(items)
    assert_that(assert_that(items).element(index).val).is_equal_to(items[index])
    assert_that(assert_that(items).first().val).is_equal_to(items[0])
    assert_that(assert_that(items).last().val).is_equal_to(items[-1])


# --- temporal assertions: the relational pairs are exact complements ---


def _holds(check):
    try:
        check()
    except AssertionError:
        return False
    return True


@settings(deadline=None)
@given(left=st.datetimes(), right=st.datetimes())
def test_is_before_is_the_exact_complement_of_is_after_or_equal_to(left, right):
    before = _holds(lambda: assert_that(left).is_before(right))
    after_or_equal = _holds(lambda: assert_that(left).is_after_or_equal_to(right))
    assert_that(before).is_not_equal_to(after_or_equal)


@settings(deadline=None)
@given(left=st.datetimes(), right=st.datetimes())
def test_is_after_is_the_exact_complement_of_is_before_or_equal_to(left, right):
    after = _holds(lambda: assert_that(left).is_after(right))
    before_or_equal = _holds(lambda: assert_that(left).is_before_or_equal_to(right))
    assert_that(after).is_not_equal_to(before_or_equal)


# --- the parts of a failure message this library composes itself ---
#
# Not "no message shows an address": a value's own repr is inherited behaviour.  This covers the text
# written around it, which is where a leak is ours to prevent.

_ADDRESS = re.compile(r"0x[0-9a-fA-F]{6,}")


class _Opaque:
    """No ``__repr__`` of its own, so ``repr()`` falls back to the address form."""


class _SelfIdentifying:
    def __repr__(self):
        return f"<Session {id(self):#x}>"  # a hand-written repr can leak an address just as well


@dataclass
class _Wrapper:
    payload: object


_leaky_items = st.recursive(
    st.sampled_from([_Opaque, _SelfIdentifying]).map(lambda factory: factory()),
    lambda children: st.builds(_Wrapper, payload=children),
    max_leaves=3,
)


@settings(deadline=None)
@given(item=_leaky_items, name=st.text(alphabet="abc", min_size=1, max_size=4))
def test_the_extracting_item_label_never_leaks_a_memory_address(item, name):
    """Whatever the item's repr does, the label assertpy2 writes for it stays reproducible.

    A message that differs between runs cannot be asserted on, cannot be diffed in CI, and sends the
    reader chasing a number that means nothing.
    """
    assume(not hasattr(item, name))
    with pytest.raises(ValueError) as exc_info:
        assert_that([item]).extracting(name)
    assert_that(_ADDRESS.search(str(exc_info.value))).is_none()


@settings(deadline=None)
@given(
    error_type=st.sampled_from([ValueError, RuntimeError, KeyError, ZeroDivisionError, LookupError]),
    message=st.text(alphabet="abc 123", min_size=1, max_size=20),
)
def test_an_error_raised_by_user_code_reaches_the_caller_unchanged(error_type, message):
    """``extracting()`` annotates its own failures with an index, so it must not repackage anyone else's.

    ``AttributeError`` is deliberately absent from the sample: that one assertpy2 does intercept, to
    tell a broken accessor from a missing name.
    """

    class Failing:
        @property
        def name(self):
            raise error_type(message)

    with pytest.raises(error_type) as exc_info:
        assert_that([Failing()]).extracting("name")
    assert_that(type(exc_info.value)).is_equal_to(error_type)
    assert_that(str(exc_info.value)).is_equal_to(str(error_type(message)))


def _unavailable(_self):
    raise AttributeError("unavailable")


@settings(deadline=None)
@given(
    attributes=st.lists(st.text(alphabet="abcdef", min_size=3, max_size=8), min_size=1, max_size=5, unique=True),
    requested=st.text(alphabet="abcdef", min_size=3, max_size=8),
    declared_but_raising=st.booleans(),
)
def test_a_suggestion_is_a_real_attribute_and_never_the_one_that_was_asked_for(
    attributes, requested, declared_but_raising
):
    """Suggesting the name the reader just typed is worse than saying nothing: it reads as a bug.

    ``declared_but_raising`` is the case that produced exactly that. A property that raises is invisible
    to ``hasattr()``, so the name lands in ``dir()`` as its own closest match.
    """
    assume(requested not in attributes)
    namespace = dict.fromkeys(attributes, 0)
    if declared_but_raising:
        namespace[requested] = property(_unavailable)
    item = type("Generated", (), namespace)()
    with pytest.raises(ValueError) as exc_info:
        assert_that([item]).extracting(requested)
    suggested = re.search(r"did you mean '([^']*)'\?", str(exc_info.value))
    if suggested:
        assert_that(suggested.group(1)).is_not_equal_to(requested)
        assert_that(attributes).contains(suggested.group(1))


# --- strict_types: the two spellings of one relation must not drift ---


class _Money:
    """A value object the walker does not take apart: deliberately **not** a dataclass.

    The gap between the eight atomic types and the five decomposable shapes is where a whole class of
    bugs lives, and a domain object with its own ``__eq__`` is its most common inhabitant - far more so
    than the set that led us here. A dataclass would not reach it: the dispatcher keys on
    ``is_dataclass``, not on who wrote ``__eq__``, so ``_Inner`` above already covers that branch.
    """

    def __init__(self, amount):
        self.amount = amount

    def __eq__(self, other):
        return isinstance(other, _Money) and self.amount == other.amount

    def __hash__(self):
        return hash(self.amount)

    def __repr__(self):
        return f"_Money({self.amount})"


# Every type the walker dispatches on, for properties comparing a value against a copy of itself only:
# two different generated values would trip over the documented hash-matching gap, a copy cannot.
_wide_atoms = (
    _atoms
    | st.binary()
    | st.decimals(allow_nan=False, allow_infinity=False)
    | st.dates()
    | st.uuids()
    | st.builds(_Money, amount=st.integers())
)
_wide_values = st.recursive(
    _wide_atoms,
    lambda children: (
        st.lists(children)
        | st.dictionaries(st.text(), children)
        | st.tuples(children, children)
        | st.sets(_wide_atoms)
        | st.frozensets(_wide_atoms)
        | st.builds(_Pair, first=children, second=children)
        | st.builds(_Inner, a=st.integers(), b=st.text())
    ),
    max_leaves=20,
)


def _reachable(predicate):
    """The minimal value in `_wide_values` satisfying *predicate*, or ``NoSuchExample``.

    ``find`` is not deprecated.  The filters are for two warnings hypothesis raises about itself, which
    this suite's ``filterwarnings = error`` would otherwise turn into failures: a ``DeprecationWarning``
    about a missing ``__spec__.loader`` from its module introspection on 3.15, and a notice that a value
    it drew renders to a very large repr, which is about what its own reporting would cost and says
    nothing about the value this lattice is being asked to reach.  Both are matched by message rather
    than by category, so another warning of either class still fails the run, and both are scoped to this
    helper rather than to the project config, so neither ever covers the library itself.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Module globals is missing", category=DeprecationWarning)
        warnings.filterwarnings("ignore", message="Generating overly large repr", category=HypothesisWarning)
        return find(_wide_values, predicate)


def test_the_wide_lattice_reaches_a_value_the_nested_walker_cannot_decompose():
    """`test_a_value_is_strictly_equal_to_itself` earns its keep only while the lattice grows values
    the walkers cannot take apart.  Narrowing it for speed would leave that property green and
    disarmed, so the reach is asserted rather than assumed - once per ladder, because the two answer
    different questions and disagree (see the module docstring of ``assertpy2._engine._diff``)."""
    found = _reachable(lambda value: type(value) not in _EQ_ATOMIC and _sub_diff_entries(value, value, _ROOT) is None)
    assert_that(type(found) in _EQ_ATOMIC).is_false()


def test_the_wide_lattice_reaches_a_value_the_top_level_ladder_runs_out_on():
    """The nested guard above is satisfied by a set, which the *top-level* builder does handle - and
    the top-level fall-through is the branch the `UUID` regression actually lived in.  Mappings are
    excluded because their ``"scalar"`` kind means "routed to _dict_err before reaching the ladder",
    not "the ladder ran out"."""
    found = _reachable(
        lambda value: (
            type(value) not in _EQ_ATOMIC
            and not is_mapping_like(value)
            and _build_equality_diff(value, value).kind == "scalar"
        )
    )
    assert_that(type(found) in _EQ_ATOMIC).is_false()


def _passes(callable_):
    try:
        callable_()
    except AssertionError:
        return False
    return True


@settings(deadline=None)
@given(left=_values, right=_values)
def test_the_flag_and_the_matcher_agree(left, right):
    # a scalar-only check cannot see this: on a composite expected value the matcher used to stop at
    # the top-level type and hand the rest to `==`, which is permissive inside
    by_flag = _passes(lambda: assert_that(left).is_equal_to(right, strict_types=True))
    by_matcher = match.equal_to(right, strict_types=True).matches(left)
    assert_that(by_matcher).is_equal_to(by_flag)


@settings(deadline=None)
@given(left=_values, right=_values)
def test_strictness_only_ever_refines_equality(left, right):
    # strictness may reject what `==` accepts, never the reverse
    if _passes(lambda: assert_that(left).is_equal_to(right, strict_types=True)):
        assert_that(left).is_equal_to(right)


@settings(deadline=None)
@given(value=_wide_values)  # must stay the same symbol the two reach guards above assert on
def test_a_value_is_strictly_equal_to_itself(value):
    # the first line pins the identity shortcut, the second that strictness does not depend on it.
    # The wide strategy is free here, and it covers shapes nobody wrote down, a set inside a list first
    assert_that(value).is_equal_to(value, strict_types=True)
    assert_that(value).is_equal_to(copy.deepcopy(value), strict_types=True)


# --- rendering invariants: the one place a property test has paid for itself here ---
#
# A wide oracle over comparison semantics measured net-negative, 12800 pairs finding nothing.  For
# rendering there is no natural example of "a caret row with nothing above it", so it must be invented.

# ESC is excluded from every generated string on purpose, paths included: a `kind="string"` diff
# prints its values raw and a path is echoed verbatim, so data carrying an escape puts one in the
# output legitimately. The colour invariants below are about what the renderer *adds*.
_NO_ESC = st.text(alphabet=st.characters(exclude_characters="\x1b"), max_size=200)
_TEXT_LEAVES = _NO_ESC | st.binary(max_size=200)
_ANY_LEAF = _TEXT_LEAVES | st.integers() | st.floats(allow_nan=True) | st.none() | st.booleans()
_DIFF_KINDS = st.sampled_from(["dict", "sequence", "string", "scalar", "model", "attrs", "set", "contains", "match"])


@st.composite
def _diffs(draw):
    """A `DiffResult` of any kind, whose entries may be one-sided, text-on-text, or mixed."""
    kind = draw(_DIFF_KINDS)
    entries = draw(
        st.lists(
            st.builds(
                DiffEntry,
                path=_NO_ESC,
                actual=_ANY_LEAF,
                expected=_ANY_LEAF,
            ),
            max_size=8,
        )
    )
    return DiffResult(kind=kind, entries=entries)


@settings(deadline=None)
@given(diff=_diffs(), color=st.booleans())
def test_rendering_a_diff_never_raises(diff, color):
    # the renderer runs while a failure is being reported, so an exception here replaces the failure
    # the reader was chasing with one of ours
    assert_that(_format_diff(diff, color=color)).is_instance_of(str)


@settings(deadline=None)
@given(diff=_diffs())
def test_a_caret_row_always_annotates_the_row_above_it(diff):
    # the guide points at a span of the line before it; alone it points at nothing.
    # Matched on the unindented prefix, not on a stripped one: a generated *path* of "?" renders as
    # `  ?: - ''` and would otherwise be mistaken for a guide row.
    rows = _format_diff(diff).splitlines()
    for previous, row in pairwise(rows):
        if row.startswith("    ?"):
            assert_that(previous.startswith(("    - ", "    + "))).is_true()
    if rows:
        assert_that(rows[0].startswith("    ?")).is_false()


@settings(deadline=None)
@given(count=st.integers(min_value=1, max_value=200), kind=_DIFF_KINDS, one_sided=st.booleans())
def test_the_block_never_outgrows_its_budget(count, kind, one_sided):
    # the filler is fixed rather than generated: hypothesis rightly objects to drawing forty
    # three-thousand-character strings per example, and its content is irrelevant - only the size is.
    # Sized so the budget is the binding constraint, otherwise the invariant holds for the wrong reason.
    filler = "x" * 3_000
    entries = [DiffEntry(path="k", actual=filler, expected=None if one_sided else filler[:-1]) for _ in range(count)]
    rendered = _format_diff(DiffResult(kind=kind, entries=entries), max_entries=0)
    assert_that(len(rendered)).is_less_than(21_000)


@settings(deadline=None)
@given(count=st.integers(min_value=30, max_value=200), kind=st.sampled_from(["set", "contains"]))
def test_a_clipped_block_still_shows_something(count, kind):
    # `set` and `contains` join every item into a single row, so dropping the row that crosses the
    # limit erased the whole diff: the reader got a header and a count and not one item
    filler = "x" * 3_000
    # `absent` is what puts an item in the extra group, and every producer of a set or containment
    # entry sets it: without it the entry claims its expected value really is None
    entries = [DiffEntry(path="extra", actual=filler, expected=None, absent="expected") for _ in range(count)]
    rendered = _format_diff(DiffResult(kind=kind, entries=entries), max_entries=0)
    assert_that(len(rendered)).is_greater_than(1_000)
    assert_that(rendered).contains("xxx")


@settings(deadline=None)
@given(diff=_diffs())
def test_an_uncoloured_render_adds_no_escape_sequences(diff):
    # the same renderer feeds the plain-text message, where an escape would be printed literally
    assert_that(_format_diff(diff, color=False)).does_not_contain("\033")


def _colour_is_balanced(rendered):
    opens = sum(rendered.count(code) for code in ("\033[31m", "\033[32m", "\033[36m"))
    return rendered.count("\033[0m") == opens


@settings(deadline=None)
@given(diff=_diffs())
def test_every_colour_opened_is_closed(diff):
    assert_that(_colour_is_balanced(_format_diff(diff, color=True))).is_true()


@settings(deadline=None)
@given(count=st.integers(min_value=1, max_value=200), kind=_DIFF_KINDS)
def test_colour_stays_balanced_when_the_block_is_clipped(count, kind):
    # the generated diffs above never reach the budget, so they never exercised the clip: a row cut
    # blind loses the reset that closed its colour and stains every line the terminal prints after it
    filler = "x" * 3_000
    entries = [DiffEntry(path="k", actual=filler, expected=None) for _ in range(count)]
    rendered = _format_diff(DiffResult(kind=kind, entries=entries), max_entries=0, color=True)
    assert_that(_colour_is_balanced(rendered)).is_true()


@settings(deadline=None)
@given(
    entries=st.lists(
        st.builds(DiffEntry, path=st.text(min_size=1, max_size=8), actual=st.integers(), expected=st.integers()),
        min_size=1,
        max_size=12,
    ),
    limit=st.integers(min_value=1, max_value=12),
)
def test_the_entry_cap_is_honoured_and_the_remainder_counted(entries, limit):
    rendered = _format_diff(DiffResult(kind="dict", entries=entries), max_entries=limit)
    # counting the rendered value rows, not the summary line: the summary is emitted from the entry
    # count alone, so it still appears when nothing was actually dropped. Rows are counted by their
    # `- ` marker, which no generated path can forge.
    shown = sum(1 for row in rendered.splitlines() if row.startswith("    - "))
    assert_that(shown).is_equal_to(min(len(entries), limit))
    if len(entries) > limit:
        assert_that(rendered).contains(f"... and {len(entries) - limit} more entries")
    else:
        assert_that(rendered).does_not_contain("more entries")


# --- report ordering and windowing ------------------------------------------------------------


@given(
    actual=st.dictionaries(st.text(min_size=1, max_size=4), st.integers(), max_size=8),
    expected=st.dictionaries(st.text(min_size=1, max_size=4), st.integers(), max_size=8),
)
def test_the_key_walk_covers_both_sides_once_and_keeps_the_written_order(actual, expected):
    # what the union of two sets used to give at the price of an imposed sort: every key, no repeats,
    # and a deterministic order. this adds the part the sort destroyed, which is the order itself
    walked = _ordered_keys(actual, expected)
    assert_that(walked).is_length(len(set(actual) | set(expected)))
    assert_that(set(walked)).is_equal_to(set(actual) | set(expected))
    assert_that([key for key in walked if key in actual]).is_equal_to(list(actual))
    assert_that(_ordered_keys(actual, expected)).is_equal_to(walked)


@given(
    lead=st.integers(min_value=0, max_value=3000),
    trail=st.integers(min_value=0, max_value=3000),
    marker=st.sampled_from("ABC"),
)
def test_a_windowed_pair_shows_where_the_two_sides_part_however_deep_it_is(lead, trail, marker):
    # the defect this replaced: each side was cut from its start, so a difference past the cap left two
    # identical-looking values printed under a heading saying they were not equal.  the shared run is
    # generated up to well past the 400-character cap, which is exactly where the old form went blind
    left, right = f"{'x' * lead}{marker}{'y' * trail}", f"{'x' * lead}z{'y' * trail}"
    rendered_left, rendered_right = _diff_sides(left, right)
    assert_that(rendered_left).is_not_equal_to(rendered_right)
    assert_that(rendered_left).contains(marker)
    assert_that(rendered_right).contains("z")


class TestOneDifferenceReadsTheSameInTextAndBytes:
    """The hint is about the difference, not about the type carrying it.

    It was type-dependent: the string branch demanded two `str` and returned nothing for anything else,
    so an upload compared as bytes got no hint while the identical comparison on text got one. Example
    tests pinned seven shapes. This states the rule over the space instead.
    """

    _TEXT = st.text(alphabet=st.sampled_from(" \t\r\n abcXYZ019"), max_size=24)

    @staticmethod
    def _hint(actual, expected):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(actual).is_equal_to(expected)
        return diagnose(failure.value.diff, actual, expected)

    @given(_TEXT, _TEXT)
    @settings(deadline=None)
    def test_the_same_pair_reads_the_same_in_both_types(self, actual, expected):
        assume(actual != expected)
        assert_that(self._hint(actual.encode(), expected.encode())).is_equal_to(self._hint(actual, expected))

    @given(_TEXT)
    @settings(deadline=None)
    def test_trailing_whitespace_is_named_in_both_types(self, value):
        assume(value.strip() and value.strip() != value)
        stripped = value.strip()
        assert_that(self._hint(value, stripped)).contains("surrounding whitespace")
        assert_that(self._hint(value.encode(), stripped.encode())).contains("surrounding whitespace")


class TestTheDanglingScanCountsWhatWasWritten:
    """The check's whole value is that it does not miss the shape it exists for, and its whole cost is
    reporting a working chain. Generated modules attack both at once.
    """

    _STATEMENTS = st.lists(
        st.sampled_from(
            [
                ("    assert_that(1)\n", 1),
                ("    assert_that(2).is_equal_to(2)\n", 0),
                ("    assert_that(3)  # assertpy2: allow-dangling\n", 0),
                ('    assert_that("# assertpy2: allow-dangling")\n', 1),
                ("    builder = assert_that(4)\n", 0),
                ("    assert_that(5).is_none\n", 1),
            ]
        ),
        min_size=1,
        max_size=8,
    )

    @given(_STATEMENTS)
    @settings(deadline=None)
    def test_every_dangling_line_is_reported_and_no_other(self, statements):
        body = "".join(line for line, _ in statements)
        source = "from assertpy2 import assert_that\n\n\ndef test_generated():\n" + body
        assert_that(dangling_findings(source, "generated.py")).is_length(sum(count for _, count in statements))


class TestTheCompactRenderingKeepsThePositionOfChange:
    """A soft entry drops the detail row when the headline already carries both values readably.

    "Readably" is a threshold, and a threshold is where an example-based test stops being convincing:
    every string long enough must keep a window around its first difference, wherever that difference
    falls, and every short one must stay a single line.  Generated pairs attack both sides of it.
    """

    @staticmethod
    def _detail(actual: str, expected: str) -> list[str]:
        """The diff rows of the single collected entry, without the one-cause hint above them.

        The hint is indented into the entry the same way, and it is about the whole failure rather than
        about a path: a pair like `''` against `' '` is explained by one and has no rows at all.
        """
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(actual).is_equal_to(expected)
        _header, _entry, *detail = str(failure.value).splitlines()
        return [row for row in detail if not row.strip().startswith(("every difference here is", "the values are"))]

    @given(
        head=st.text(alphabet="abcdefghij", min_size=61, max_size=200),
        tail=st.text(alphabet="abcdefghij", max_size=200),
    )
    @settings(deadline=None)
    def test_a_long_pair_always_shows_where_it_diverges(self, head, tail):
        actual, expected = head + "X" + tail, head + "Y" + tail
        detail = self._detail(actual, expected)
        assert_that(detail).is_length(1)
        assert_that(detail[0]).starts_with("   line 1: ").contains("X").contains("Y")

    # control characters are excluded because `\r` and friends are line breaks to `splitlines()`, which
    # is how the message is read back here: a value carrying one is a *multi*-line failure, and those
    # keep their per-line rows by design
    _ONE_LINE = st.text(st.characters(exclude_categories=("Cc", "Cs", "Zl", "Zp")), max_size=60)

    @given(actual=_ONE_LINE, expected=_ONE_LINE)
    @settings(deadline=None)
    def test_a_short_pair_never_repeats_the_headline(self, actual, expected):
        assume(actual != expected)
        assert_that(self._detail(actual, expected)).is_empty()


class TestEveryRefusalIsReadableWhateverArrived:
    """The refusal shape has to survive the value it is describing.

    It embeds `repr(value)`, and a repr can be empty, enormous, multi-line, or contain the very
    brackets the shape uses. Generated values attack all four at once, which no fixed set of examples
    covers: what a reader must always get back is the subject, the expectation and a named type.
    """

    @given(value=_values, expectation=st.text(min_size=1, max_size=20).filter(str.strip))
    @settings(deadline=None)
    def test_the_sentence_survives_any_value(self, value, expectation):
        with pytest.raises(TypeError) as failure:
            refuse(value, expectation)
        message = str(failure.value)
        assert_that(message).starts_with(f"val must be {expectation}, but was <")
        assert_that(message).ends_with(f"({type(value).__name__})")

    @given(value=st.text(min_size=200, max_size=4000))
    @settings(deadline=None)
    def test_a_long_value_never_floods_the_line(self, value):
        with pytest.raises(TypeError) as failure:
            refuse(value, "a number")
        # the cap is on the rendered value; the sentence around it is short and fixed
        assert_that(len(str(failure.value))).is_less_than(140)


class TestTheEvaluationCoresAgreeWithPython:
    """The cores answer the same questions Python does, over generated values rather than chosen ones.

    Each core replaced a rule that was written twice, and the risk of that kind of move is a shift at the
    edges rather than in the middle: the examples that were in mind when it was written keep passing.
    """

    @given(left=_values, right=_values)
    @settings(deadline=None)
    def test_equality_without_options_is_python_equality(self, left, right):
        assert_that(values_differ(left, right, None)).is_equal_to(not bool(left == right))

    @given(left=st.integers(), right=st.integers())
    def test_ordering_is_a_total_order_on_integers(self, left, right):
        assert_that(compare(left, right)).is_equal_to((left > right) - (left < right))
        assert_that(holds(left, right, "lt")).is_equal_to(left < right)
        assert_that(holds(left, right, "ge")).is_equal_to(left >= right)

    @given(left=st.integers(), middle=st.integers(), right=st.integers())
    def test_ordering_is_transitive(self, left, middle, right):
        if holds(left, middle, "lt") and holds(middle, right, "lt"):
            assert_that(holds(left, right, "lt")).is_true()

    @given(items=st.lists(st.integers(), max_size=8), wanted=st.integers())
    def test_membership_matches_the_in_operator(self, items, wanted):
        absent = missing_items(items, [wanted], lambda candidate: False)
        assert_that(not absent).is_equal_to(wanted in items)

    @given(items=st.lists(st.integers(), min_size=1, max_size=8))
    def test_a_collection_contains_all_of_its_own_elements(self, items):
        assert_that(missing_items(items, items, lambda candidate: False)).is_empty()

    @given(
        value=st.one_of(st.text(), st.lists(st.integers()), st.dictionaries(st.text(), st.integers()), st.integers())
    )
    def test_size_answers_none_exactly_when_len_refuses(self, value):
        try:
            expected = len(value)  # ty: ignore[invalid-argument-type]  # the refusal is the point
        except TypeError:
            expected = None
        assert_that(length_of(value)).is_equal_to(expected)

    @given(left=st.text(max_size=20), right=st.text(max_size=20))
    def test_text_relations_match_their_str_methods(self, left, right):
        assert_that(text_contains(left, right)).is_equal_to(right in left)
        assert_that(text_starts_with(left, right)).is_equal_to(left.startswith(right))
        assert_that(text_ends_with(left, right)).is_equal_to(left.endswith(right))

    @given(left=st.binary(max_size=20), right=st.binary(max_size=20))
    def test_text_relations_do_the_same_for_bytes(self, left, right):
        assert_that(text_contains(left, right)).is_equal_to(right in left)
        assert_that(text_starts_with(left, right)).is_equal_to(left.startswith(right))

    @given(text=st.text(max_size=20), raw=st.binary(max_size=20))
    def test_the_two_text_families_never_match_each_other(self, text, raw):
        assert_that(text_contains(text, raw)).is_false()
        assert_that(text_contains(raw, text)).is_false()
        assert_that(text_starts_with(text, raw)).is_false()
        assert_that(text_ends_with(raw, text)).is_false()


# Which narrowed view each subject reaches, so the table below can be checked against the typed surface
# rather than trusted.  A hand-written list of "types with a pipeline" is exactly the kind of thing that
# stops matching the code the first time a view is added.
_PIPELINE_VIEWS = {
    "list": "_IterableAssertion",
    "tuple": "_IterableAssertion",
    "set": "_IterableAssertion",
    "frozenset": "_IterableAssertion",
    "str": "_StringAssertion",
    "bytes": "_BytesAssertion",
    "bytearray": "_BytesAssertion",
    "dict": "_DictAssertion",
}

# every subject `assert_that` narrows to a view carrying the pipeline steps, built from one list of ints
_PIPELINE_SUBJECTS = {
    "list": list,
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    "str": lambda items: "".join(chr(ord("a") + item % 26) for item in items),
    "bytes": lambda items: bytes(item % 256 for item in items),
    "bytearray": lambda items: bytearray(item % 256 for item in items),
    "dict": lambda items: dict.fromkeys(items, 0),
}
_PIPELINE_STEPS = {
    "filtered_on": lambda view: view.filtered_on(lambda item: True),
    "mapped": lambda view: view.mapped(str),
    "flat_mapped": lambda view: view.flat_mapped(lambda item: [item, item]),
}


# what `assert_that` answers when no concrete overload matches, and so the one overload with no subject
_FALLBACK_VIEW = "AssertionBuilder"


def _plain_name(annotation) -> str:
    """The bare name an annotation is written with, or `""` for anything qualified, quoted or absent.

    Reading `.value.id` straight off a subscript raised `AttributeError` on `module.View[T]`, which is
    the opposite of the deliberate refusal the caller promises: an accident, not a diagnostic.
    """
    if isinstance(annotation, ast.Subscript):
        annotation = annotation.value
    return annotation.id if isinstance(annotation, ast.Name) else ""


def _pinned_pairs() -> dict[str, str]:
    """``{subject type name: view}`` read from the `assert_type(assert_that(<literal>), View)` calls.

    Written as a syntactic walk rather than a text search on purpose: `", _DateAssertion"` matches an
    import, a comment or an unrelated tuple just as happily as the call that proves anything.
    """
    source = pathlib.Path(__file__).with_name("test_typing.py").read_text(encoding="utf-8")
    pinned: dict[str, str] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or _plain_name(node.func) != "assert_type" or len(node.args) != 2:
            continue
        checked, view = node.args
        if not isinstance(checked, ast.Call) or _plain_name(checked.func) != "assert_that" or not checked.args:
            continue
        subject = _literal_type(checked.args[0])
        if not subject:
            continue
        # pinned twice to different views is a contradiction and stops the run.  Pinned twice to the same
        # view is ordinary and allowed: `test_typing.py` checks a list subject in many chains, and each
        # of those lines is a real assertion rather than a duplicate to remove
        if subject in pinned and pinned[subject] != _plain_name(view):
            raise AssertionError(f"{subject} is pinned to both {pinned[subject]} and {_plain_name(view)}")
        pinned[subject] = _plain_name(view)
    return pinned


def _literal_type(expression) -> str:
    """The type name a literal subject has, or `""` when the expression is not a literal.

    Only literals are read, because only they say what type `assert_that` was handed without resolving
    a name.  A subject pinned solely through a variable simply does not count towards the pairs.
    """
    match expression:
        case ast.Constant(value=value):
            return type(value).__name__
        case ast.List():
            return "list"
        case ast.Tuple():
            return "tuple"
        case ast.Dict():
            return "dict"
        case ast.Set():
            return "set"
        case ast.Lambda():
            return "Callable"
        case ast.Call(func=ast.Name(id="cast"), args=[ast.Constant(value=str(name)), *_]):
            # the only way to write a value of a protocol type: a shape-keyed overload has no literal
            return name
        case ast.Call(func=ast.Attribute(value=ast.Name(id=module), attr=name)):
            return f"{module}.{name}"
        case ast.Call(func=ast.Name(id=name)):
            return name
    return ""


def _shape_bounds() -> dict[str, str]:
    """``{type variable: the shape it is bound to}``, for the overloads that key on a bound variable.

    A shape-keyed overload names a type variable rather than the protocol, so the view can carry the
    subject through to `.value`.  Resolving the bound is what keeps the subject readable here, and
    `tests/test_overload_order.py` reads the same declarations for the order it holds.
    """
    source = pathlib.Path(assertpy2._engine._typing.__file__).read_text(encoding="utf-8")
    bounds = {}
    for node in ast.walk(ast.parse(source)):
        match node:
            case ast.Assign(
                targets=[ast.Name(id=name)],
                value=ast.Call(func=ast.Name(id="TypeVar"), keywords=keywords),
            ):
                for keyword in keywords:
                    if keyword.arg == "bound" and isinstance(keyword.value, ast.Name):
                        bounds[name] = keyword.value.id
    return bounds


def _dispatch_relation() -> dict[str, str]:
    """``{subject type name: protocol}`` for every `assert_that` overload that names a concrete type.

    Only top-level definitions carrying `@overload` are read.  Walking every `assert_that` in the file
    would take the implementation as well, whose annotation is the generic fallback and describes no
    subject, and any nested definition a test happens to declare.

    A subject appearing twice with different views is an error rather than a last-one-wins: the point of
    reading this relation is to notice a change, and a silent overwrite is how a change goes unnoticed.
    """
    source = pathlib.Path(assertpy2.assertpy.__file__).read_text(encoding="utf-8")
    relation: dict[str, str] = {}
    fallbacks: list[list[str]] = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef) or node.name != "assert_that":
            continue
        if not any(_is_overload(decorator) for decorator in node.decorator_list):
            continue
        returns, arguments = node.returns, node.args.args
        view = _plain_name(returns)
        subjects = _annotated_types(arguments[0].annotation) if arguments and arguments[0].annotation else []
        if view == _FALLBACK_VIEW:
            # the overload answering for anything unrecognised.  Its subject is a bare TypeVar, and
            # requiring that here is what stops a concrete overload from hiding behind the same return
            fallbacks.append(subjects)
            continue
        # a return this walk cannot decode is refused for the same reason an unreadable subject is: a
        # quoted or qualified annotation would drop its subject out of the relation without a word
        if not view.endswith("Assertion"):
            written = ast.unparse(returns) if returns else "nothing"
            raise AssertionError(f"an assert_that overload returns {written}, which this walk cannot read")
        # an overload this walk cannot read would drop out of the relation without a word, and the
        # relation is the whole claim: refuse instead, the same way the protocol walk refuses a base
        if not subjects:
            raise AssertionError(f"an assert_that overload returning {view} has a subject this walk cannot read")
        bounds = _shape_bounds()
        for subject in (bounds.get(name, name) for name in subjects):
            # a repeat is an error even when it agrees: two overloads naming one subject is a
            # duplicate to remove, and letting the agreeing case through would hide it
            if subject in relation:
                raise AssertionError(f"{subject} is dispatched by more than one overload")
            relation[subject] = view
    if fallbacks != [["_T"]]:
        raise AssertionError(f"expected exactly one generic fallback overload, found subjects {fallbacks}")
    return relation


def _is_overload(decorator) -> bool:
    """`@overload` or `@typing.overload`, the two ways the same decorator gets written."""
    if isinstance(decorator, ast.Name):
        return decorator.id == "overload"
    return isinstance(decorator, ast.Attribute) and decorator.attr == "overload"


def _annotated_types(annotation) -> list[str]:
    """The concrete type names an annotation mentions, with `list[_E] | tuple[_E, ...]` giving two."""
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _annotated_types(annotation.left) + _annotated_types(annotation.right)
    if isinstance(annotation, ast.Subscript):
        return _annotated_types(annotation.value)
    if isinstance(annotation, ast.Attribute):
        return [
            f"{annotation.value.id}.{annotation.attr}" if isinstance(annotation.value, ast.Name) else annotation.attr
        ]
    return [annotation.id] if isinstance(annotation, ast.Name) else []


def _reachable_methods(protocol: str) -> set[str]:
    """Every method a protocol offers, inherited ones included."""
    source = pathlib.Path(assertpy2._engine._typing.__file__).read_text(encoding="utf-8")
    declared: dict[str, tuple[set[str], list[str]]] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Assertion"):
            bases = [_plain_name(base) for base in node.bases]
            methods = {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
            declared[node.name] = (methods, [base for base in bases if base.endswith("Assertion")])

    def walk(name: str) -> set[str]:
        methods, parents = declared[name]
        return methods.union(*(walk(parent) for parent in parents)) if parents else methods

    return walk(protocol)


def _form_names(test_name: str) -> list[str]:
    """The keys of the `forms` dictionary inside one test, read from this file's own syntax."""
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == test_name:
            assigned = [
                statement
                for statement in node.body
                if isinstance(statement, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "forms" for target in statement.targets)
            ]
            # taking the first would compare one dictionary while another held the cases that ran
            if len(assigned) != 1:
                raise AssertionError(f"{test_name} has {len(assigned)} `forms` dictionaries, expected one")
            for statement in assigned:
                if True:
                    # a computed key would otherwise be dropped here and the form would vanish from the
                    # comparison, which is the drift this gate exists to catch
                    if not isinstance(statement.value, ast.Dict):
                        raise AssertionError(f"`forms` in {test_name} is not a dictionary literal")
                    if not all(
                        isinstance(key, ast.Constant) and isinstance(key.value, str) for key in statement.value.keys
                    ):
                        raise AssertionError(f"`forms` in {test_name} has a key this gate cannot read")
                    return [key.value for key in statement.value.keys]
    raise AssertionError(f"no `forms` dictionary found in {test_name}")


class _TakesAnyKey(Mapping):
    """A row that reads a key without hashing it, which is why the selector type stays `object`.

    Written out rather than assumed: a mapping is free to define `__getitem__` however it likes, and
    this one answers for a list.  Every narrowing of the selector type tried during review refused this
    call, and the runtime takes it.
    """

    def __getitem__(self, key):
        return f"got {key!r}"

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0


class TestEveryPipelineStepHandsBackAList:
    """The runtime half of what the typed surface promises after a pivot.

    `_ListAssertion` says `value` is a `list`, and the point of saying so is that it holds for every
    subject a pipeline accepts, not only for the `list` a suite usually starts from.  The check is the
    whole product of subject and operation rather than a sample of it: the union that used to be
    declared here came precisely from reasoning about one container and assuming the other three.
    """

    def test_the_subject_table_matches_what_assert_that_dispatches(self):
        """The whole subject-to-view relation, read out of the overloads rather than remembered.

        Comparing only the set of view names was not enough, and the hole is worth naming: a new subject
        dispatched to a view already in the table, or one of several subjects sharing a view going away,
        both left the comparison equal.  So the relation is compared as a relation.

        Inheritance is resolved on the way, because a carrier can hold the pipeline without declaring it:
        `_ListAssertion` gets `filtered_on` from `_IterableAssertion` and an inherited method is as real
        to a caller as a declared one.
        """
        dispatched = _dispatch_relation()
        with_a_pipeline = {
            subject: view for subject, view in dispatched.items() if "filtered_on" in _reachable_methods(view)
        }
        assert_that(with_a_pipeline).described_as(
            "what assert_that narrows to a view with a pipeline, against the subjects this file walks"
        ).is_equal_to(_PIPELINE_VIEWS)

    def test_every_subject_and_view_pair_is_pinned_by_an_assert_type(self):
        """The structural relation says what is written; `test_typing.py` says what a checker picks.

        This gate reads annotations, so it cannot see overload resolution: a wider overload written
        above a narrower one would change which view a checker actually chooses while leaving the text
        here untouched.  What closes that gap is the other file, where the pair is pinned with
        `assert_type` and run through ty, mypy and pyright.

        Pairs, not views.  Several subjects reach the same view, so pinning the view once would let the
        resolution of every other subject in that group drift to the fallback unnoticed.
        """
        pinned = _pinned_pairs()
        missing = {
            f"{subject} -> {view}" for subject, view in _dispatch_relation().items() if pinned.get(subject) != view
        }
        assert_that(missing).described_as("subject-to-view pairs with no assert_type on them").is_empty()

    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("View", "View"),
            ("View[int]", "View"),
            ("module.View", ""),
            ("module.View[int]", ""),
            ("'View'", ""),
            ("View[int, str]", "View"),
        ],
    )
    def test_the_name_reader_says_what_it_can_and_cannot_read(self, written, expected):
        """The syntax these gates understand, written down instead of implied.

        Every walk here reads source rather than resolved types, so which spellings it understands is a
        real limit and belongs in a test: a form it cannot read has to come back empty and reach the
        caller's explicit refusal, never an `AttributeError` and never a wrong answer.
        """
        assert_that(_plain_name(ast.parse(written, mode="eval").body)).is_equal_to(expected)

    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("[1, 2]", "list"),
            ("(1, 2)", "tuple"),
            ("{1, 2}", "set"),
            ("{'a': 1}", "dict"),
            ("'text'", "str"),
            ("b'raw'", "bytes"),
            ("1", "int"),
            ("True", "bool"),
            ("lambda: None", "Callable"),
            ("frozenset([1])", "frozenset"),
            ("datetime.date(2026, 1, 1)", "datetime.date"),
            ("some_variable", ""),
            ("a + b", ""),
        ],
    )
    def test_the_literal_reader_names_the_types_it_supports(self, written, expected):
        """Which subjects count towards the pinned pairs, and which are simply not literals."""
        assert_that(_literal_type(ast.parse(written, mode="eval").body)).is_equal_to(expected)

    def test_a_second_step_runs_on_what_the_first_one_returned(self):
        """The result of a pivot carries the pivots itself, which is what makes a chain a chain."""
        chained = assert_that([1, 2, 3]).mapped(str).filtered_on(lambda item: item != "2")
        assert_that(type(chained.value)).is_equal_to(list)
        assert_that(chained.value).is_equal_to(["1", "3"])
        assert_that(type(chained.mapped(int).value)).is_equal_to(list)

    @pytest.mark.parametrize("subject", sorted(_PIPELINE_SUBJECTS), ids=sorted(_PIPELINE_SUBJECTS))
    @pytest.mark.parametrize("step", sorted(_PIPELINE_STEPS), ids=sorted(_PIPELINE_STEPS))
    @given(items=st.lists(st.integers(min_value=0, max_value=255), max_size=8))
    def test_a_step_builds_a_list_whatever_the_subject_was(self, subject, step, items):
        built = _PIPELINE_STEPS[step](assert_that(_PIPELINE_SUBJECTS[subject](items)))
        assert_that(type(built.value)).described_as(f"{step} on a {subject}").is_equal_to(list)

    @pytest.mark.parametrize("subject", ["list", "tuple", "set", "frozenset"], ids=lambda name: name)
    @given(identifiers=st.lists(st.integers(), max_size=6, unique=True))
    def test_extraction_ends_on_a_list_from_every_collection(self, subject, identifiers):
        """The subject reaches `extracting` as the container under test, not as a list of its items.

        The first version of this built the container and then rebuilt a list out of it before calling
        `extracting`, so all four cases were the same case.  Rows are tuples here because a `set` and a
        `frozenset` need hashable members, and a tuple is extracted by index the same way a mapping row
        is extracted by key.
        """
        rows = _PIPELINE_SUBJECTS[subject]((identifier, "name") for identifier in identifiers)
        extracted = assert_that(rows).extracting(0)
        assert_that(type(extracted.value)).described_as(f"extracting from a {subject}").is_equal_to(list)

    @given(rows=st.lists(st.tuples(st.integers(), st.text(alphabet="ab", max_size=3)), max_size=6))
    def test_every_call_form_of_extraction_ends_on_a_list(self, rows):
        """One name, several names, and each keyword option the signature accepts.

        The declared return covers `*names` and `**kwargs` alike, so checking a single positional name
        would leave the multi-name form, `filter` and `sort` resting on nothing.  Several names build
        tuples rather than scalars, which is a different code path to the same promise.
        """
        subject = [{"id": identifier, "name": name} for identifier, name in rows]
        # held in a variable rather than written inline, which is the shape the typed suite pins: an
        # invariant `dict[str, str]` would not fit a `dict[str, object]` parameter
        criteria: dict[str, str] = {"name": "a"}
        forms = {
            # keyed by the name of the case recording the same form in `typing_cases.py`, so the two
            # suites compare as sets rather than as two numbers that happen to be equal
            "one-name": lambda: assert_that(subject).extracting("id"),
            "several-names": lambda: assert_that(subject).extracting("id", "name"),
            "filter-callable": lambda: assert_that(subject).extracting("id", filter=lambda row: True),
            "filter-by-key": lambda: assert_that(subject).extracting("id", filter="name"),
            "sort-callable": lambda: assert_that(subject).extracting("id", sort=lambda row: row["id"]),
            "filter-by-mapping": lambda: assert_that(subject).extracting("id", filter={"name": "a"}),
            "sort-by-key": lambda: assert_that(subject).extracting("id", sort="id"),
            "sort-by-keys": lambda: assert_that(subject).extracting("id", sort=["name", "id"]),
            "filter-and-sort": lambda: assert_that(subject).extracting("id", filter="name", sort="id"),
            "filter-from-a-variable": lambda: assert_that(subject).extracting("id", filter=criteria),
            "filter-from-a-mapping": lambda: assert_that(subject).extracting(
                "id", filter=MappingProxyType({"name": "a"})
            ),
            "a-slice": lambda: assert_that([(1, 2, 3)]).extracting(slice(0, 2)),
            "an-unhashable-selector": lambda: assert_that([_TakesAnyKey()]).extracting([]),
        }
        for description, build in forms.items():
            assert_that(type(build().value)).described_as(f"extracting {description}").is_equal_to(list)

    def test_the_call_forms_here_match_the_ones_the_typed_suite_records(self):
        """The two halves of the same claim, compared as sets of named forms.

        `typing_cases.py` records each accepted call form as a case a checker must accept, and the test
        above runs each one.  They drifted once already: the runtime side was missing the mapping filter
        and the multi-key sort while the report said both were covered.

        The keys are read out of the syntax of that test's own dictionary, not by searching the file for
        text: a second variable named `forms` anywhere above would have won the search, and the answer
        would have been about the wrong dictionary.
        """
        here = _form_names("test_every_call_form_of_extraction_ends_on_a_list")
        assert_that(here).described_as("call forms named twice").does_not_contain_duplicates()

        recorded = pathlib.Path(__file__).with_name("typing_cases.py").read_text(encoding="utf-8")
        # the marker has to sit on a line that actually calls `extracting`: a label left behind after
        # its call was deleted would otherwise keep the two sets equal while the form was gone
        marked = [
            found.group(1)
            for line in recorded.splitlines()
            if (found := re.search(r"# case: (valid-extracting-[\w-]+)", line)) and ".extracting(" in line
        ]
        every_marker = re.findall(r"# case: (valid-extracting-[\w-]+)", recorded)
        assert_that(marked).described_as("markers that no longer sit on a call").is_equal_to(every_marker)
        assert_that(marked).described_as("cases marked twice").does_not_contain_duplicates()

        typed = {name.removeprefix("valid-extracting-") for name in marked}
        assert_that(set(here)).described_as(
            "call forms exercised here, against the ones typing_cases.py records"
        ).is_equal_to(typed)

    @given(keys=st.lists(st.text(alphabet="abc", min_size=1, max_size=3), max_size=6))
    def test_extraction_from_a_mapping_walks_its_keys(self, keys):
        """What extraction does to a mapping, recorded as measured rather than as intended.

        A mapping is walked over its keys, so `extracting(0)` indexes into the key itself and a mapping
        with integer keys raises.  Whether that is the API anyone wants is an open question, and this
        test deliberately asserts only the part the typed surface depends on, that the result is a list.
        Pinning the extracted values here would turn an unreviewed behaviour into a contract and make
        fixing it look like a regression.
        """
        extracted = assert_that(dict.fromkeys(keys, 0)).extracting(0)
        assert_that(type(extracted.value)).is_equal_to(list)


@needs_groups
class TestEveryLeafOfAGroupIsReachable:
    """What the group pivots promise on a tree of arbitrary shape.

    The example-based tests use one flat group and one with a single nested level, which is the shape
    anyone writes by hand.  Real groups come out of `asyncio.TaskGroup` and retry loops, where nesting
    is whatever the failures happened to produce.  Two invariants: the leaves pivot loses nothing and
    invents nothing, and the three type questions answer with one voice.
    """

    @staticmethod
    def _tree(draw):
        """A group whose members are leaves or further groups, drawn to an arbitrary depth.

        The leaf types vary so that a drawn question has no fixed answer: with every leaf a `ValueError`
        the agreement below would hold on a constant, which is close to asserting nothing.
        """
        leaf = st.builds(
            lambda kind, text: kind(text),
            st.sampled_from([ValueError, KeyError, TypeError]),
            st.integers(min_value=0, max_value=99).map(str),
        )
        return draw(
            st.recursive(
                leaf,
                lambda inner: st.builds(
                    lambda members: ExceptionGroup("generated", members),
                    st.lists(inner, min_size=1, max_size=4),
                ),
                max_leaves=12,
            )
        )

    @staticmethod
    def _flatten(exc):
        """The leaves, computed the obvious way, to compare the implementation against."""
        if not isinstance(exc, BaseExceptionGroup):
            return [exc]
        return [leaf for member in exc.exceptions for leaf in TestEveryLeafOfAGroupIsReachable._flatten(member)]

    @given(data=st.data())
    @settings(max_examples=50)
    def test_the_pivot_reaches_every_leaf_and_no_more(self, data):
        group = self._tree(data.draw)
        assume(isinstance(group, BaseExceptionGroup))

        def raise_it():
            raise group

        caught = assert_that(raise_it).raises(type(group)).when_called_with()
        expected = self._flatten(group)
        assert_that(caught.errors().value).is_length(len(expected))
        assert_that([id(leaf) for leaf in caught.errors().value]).is_equal_to([id(leaf) for leaf in expected])

    @given(data=st.data(), asked=st.sampled_from([ValueError, KeyError, TypeError, LookupError, Exception]))
    @settings(max_examples=100)
    def test_the_three_group_forms_agree_on_whatever_is_asked(self, data, asked):
        """One verdict, three spellings.

        All three walk the same nodes, groups included, so a type one of them finds the others have to
        agree about. A type the group holds has to be found
        by both and refused by `does_not_contain_error`, and a type it does not hold the other way round.
        The drawn types include a base class and a group type on purpose: those are the two shapes that
        told the leaves-only version of `error_of` apart from this one.
        """
        group = self._tree(data.draw)
        assume(isinstance(group, BaseExceptionGroup))

        def raise_it():
            raise group

        for wanted in (asked, type(group)):
            caught = assert_that(raise_it).raises(type(group)).when_called_with()
            present = caught.check().contains_error(wanted).passed
            assert_that(caught.check().error_of(wanted).passed).described_as(
                f"error_of({wanted.__name__}) against contains_error"
            ).is_equal_to(present)
            assert_that(caught.check().does_not_contain_error(wanted).passed).described_as(
                f"does_not_contain_error({wanted.__name__}) against contains_error"
            ).is_equal_to(not present)


# --- the summary layers added last: a value walk, a grouping, and a static scan ------------------

_LEAVES = st.one_of(
    st.integers(), st.floats(allow_nan=False), st.text(max_size=8), st.booleans(), st.none(), st.binary(max_size=8)
)
_STRUCTURES = st.recursive(
    _LEAVES,
    lambda inner: st.one_of(
        st.lists(inner, max_size=4),
        st.tuples(inner, inner),
        st.dictionaries(st.text(max_size=4), inner, max_size=4),
        st.frozensets(_LEAVES, max_size=4),
    ),
    max_leaves=12,
)


class TestStableReprHoldsOverArbitraryStructures:
    """It runs inside a pytest report hook, where an exception costs the reader the whole run.

    Both shapes that used to escape were found by a reviewer rather than by the example suite, so the
    invariant is stated here as a property instead of as more examples.
    """

    @given(_STRUCTURES)
    @settings(deadline=None)
    def test_it_never_raises_and_repeats_itself(self, value):
        first = stable_repr(value)
        assert_that(first).is_instance_of(str)
        assert_that(stable_repr(value)).described_as("same value, same text").is_equal_to(first)

    @given(st.frozensets(_LEAVES, max_size=6))
    @settings(deadline=None)
    def test_a_set_reads_the_same_however_it_was_built(self, members):
        # the xdist hazard in miniature: two processes iterate one set in two orders
        rebuilt = frozenset(reversed(list(members)))
        assert_that(stable_repr(rebuilt)).is_equal_to(stable_repr(members))

    @given(st.dictionaries(st.text(max_size=4), _LEAVES, max_size=4))
    @settings(deadline=None)
    def test_a_value_that_contains_itself_terminates(self, value):
        value["self"] = value
        assert_that(stable_repr(value)).contains("...")


class TestClusteringDoesNotDependOnArrivalOrder:
    """Under xdist the controller receives failures in whatever order workers finish in.

    A summary that changes with that order is a summary a reader cannot compare between two runs of the
    same red suite, and one such dependency shipped into the rewrite before a reviewer caught it.
    """

    _OBSERVATIONS = st.lists(
        st.builds(
            Observation,
            st.builds(Signature, st.just(True), st.sampled_from(["a", "b.c", "d[*]"]), st.just((("key", "'a'"),))),
            st.sampled_from(["1", "2", "3"]),
            st.sampled_from(["9", "8"]),
        ),
        min_size=1,
        max_size=3,
    )

    @given(st.lists(st.tuples(st.text(min_size=1, max_size=6), _OBSERVATIONS), min_size=3, max_size=12), st.randoms())
    @settings(deadline=None)
    def test_the_rendered_summary_is_a_function_of_the_set_not_the_sequence(self, recorded, random):
        shuffled = list(recorded)
        random.shuffle(shuffled)
        total = len(recorded)
        assert_that(render(clusters(shuffled, total), total)).is_equal_to(render(clusters(recorded, total), total))

    @given(st.lists(st.tuples(st.text(min_size=1, max_size=6), _OBSERVATIONS), max_size=12))
    @settings(deadline=None)
    def test_no_cluster_ever_claims_more_failures_than_the_run_had(self, recorded):
        total = len(recorded)
        for cluster in clusters(recorded, total):
            assert_that(cluster.size).is_less_than_or_equal_to(total)


class TestSummaryValuesStayWithinTheirBudget:
    """Two failures over a large payload used to put the payload on the terminal twice and through the
    xdist transport once per failure. The cap is what keeps a summary a summary.
    """

    @given(_STRUCTURES)
    @settings(deadline=None)
    def test_no_value_exceeds_the_cap_by_more_than_its_own_notice(self, value):
        shown = _shown(value)
        assert_that(len(shown)).is_less_than_or_equal_to(_VALUE_LIMIT + len("... (999999 more chars)"))

    @given(st.text(min_size=400, max_size=900))
    @settings(deadline=None)
    def test_a_long_value_says_how_much_was_cut(self, value):
        shown = _shown(value)
        assert_that(shown).starts_with(stable_repr(value)[:_VALUE_LIMIT]).ends_with("more chars)")
