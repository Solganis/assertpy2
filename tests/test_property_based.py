"""Property-based tests (Hypothesis) for the riskiest pure-logic surfaces.

These complement the example-based suite: 100% line coverage does not exercise the *space* of
values, which is where recursive equality, ignore/include filtering, and matcher algebra hide bugs.
Each test states an invariant and lets Hypothesis attack it with generated data; on failure the
shrunk counterexample plus assertpy2's structured ``AssertionFailure`` pinpoint the mismatch.
"""

import copy
import datetime
import json
import re
import warnings
from collections import Counter, namedtuple
from dataclasses import dataclass, replace
from itertools import pairwise

import pytest
from hypothesis import assume, find, given, settings
from hypothesis import strategies as st

from assertpy2 import assert_conforms, assert_that, match, soft_assertions
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
# Not "no message ever shows an address": rendering the value's own repr is inherited behaviour, and
# `is_equal_to` on a plain object does print `<Foo object at 0x...>`. The invariant covers the text
# assertpy2 writes around that value, which is where a leak is ours to prevent.

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


# Every type the walker dispatches on, not just the JSON-shaped subset `_values` covers. Only a property
# comparing a value against a copy of itself may use this. `_values` grows no sets on purpose, and a
# property that compares two *different* generated values would otherwise trip over the documented
# hash-matching gap, where a set element or dict key of a different type but the same hash is matched
# before anything looks at its type. Against a copy the values are identical, so the gap cannot arise.
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

    ``find`` is not deprecated; the filter is for one unrelated ``DeprecationWarning`` about a missing
    ``__spec__.loader``, which hypothesis's module introspection raises on 3.15 and this suite's
    ``filterwarnings = error`` would otherwise turn into a failure.  Matched by message rather than by
    category, so a real deprecation raised in here still fails the run, and scoped to this helper
    rather than the project config, so it never covers the library itself.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Module globals is missing", category=DeprecationWarning)
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
    # the first line pins the identity shortcut forced descent would otherwise take away; the second
    # pins that strictness does not depend on it, since a deep copy keeps every type and no identity.
    # The wide strategy belongs to this property in particular: a copy is type-identical, so widening
    # it costs nothing and covers the shapes nobody thought to write down - a set inside a list was one
    assert_that(value).is_equal_to(value, strict_types=True)
    assert_that(value).is_equal_to(copy.deepcopy(value), strict_types=True)


# --- rendering invariants: the one place a property test has paid for itself here ---
#
# A wide oracle over comparison *semantics* was measured net-negative: 12800 generated pairs found no
# bug the example suite had missed, because semantics is densely covered by examples. Rendering is the
# opposite. There is no natural example for "a caret row with nothing above it" or "a block that grew
# past its budget" - the case has to be invented before it can be written down, which is exactly what
# generation does for free.

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
