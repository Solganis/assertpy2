# CodSpeed regression gate: micro-benchmarks of assertpy2's own hot paths, measured commit-over-commit
# under CPU simulation. Run manually with `uv run --group benchmark pytest benchmarks/ --codspeed --no-cov`;
# the CodSpeed CI job runs the same. Not collected by the default suite (testpaths=tests), so it never gates
# on the machine's noise - only CodSpeed's simulated instruction count does.
from __future__ import annotations

import contextlib
from dataclasses import dataclass

from assertpy2 import assert_that, match
from assertpy2.errors import AssertionFailure


def _records(count: int) -> list[dict]:
    return [
        {
            "id": i,
            "name": f"user-{i}",
            "active": i % 2 == 0,
            "roles": ["admin", "user"] if i % 3 == 0 else ["user"],
            "profile": {"age": 20 + (i % 50), "city": f"city-{i % 20}", "score": i * 1.5},
        }
        for i in range(count)
    ]


@dataclass
class _Row:
    id: int
    name: str
    tags: list[str]


_SPEC = {"id": match.is_instance_of(int), "name": match.is_non_empty_string(), "active": match.is_instance_of(bool)}


def test_is_equal_to_nested_pass(benchmark):
    # the common success path: structural equality delegates to == and builds no diff
    left, right = _records(200), _records(200)
    benchmark(lambda: assert_that(left).is_equal_to(right))


def test_is_equal_to_nested_diff(benchmark):
    # the failure path: _build_equality_diff walks the whole graph to produce a structured diff
    left, right = _records(200), _records(200)
    right[199]["profile"]["city"] = "changed"

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_matches_structure_with_matchers(benchmark):
    # matcher dispatch (_is_matcher), StructureMatcher._walk and _as_mapping over many records
    records = _records(200)

    def run():
        for record in records:
            assert_that(record).matches_structure(_SPEC)

    benchmark(run)


def test_dataclass_diff(benchmark):
    # recursive structured diff over dataclasses (the _sub_diff_entries path)
    left = [_Row(i, f"n{i}", ["a", "b"]) for i in range(200)]
    right = [_Row(i, f"n{i}", ["a", "b"]) for i in range(200)]
    right[199].tags = ["a", "c"]

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_contains_exactly_large(benchmark):
    # the contains engine: exact membership over a sizeable list
    items = list(range(300))
    benchmark(lambda: assert_that(items).contains_exactly(*items))


def test_string_diff_with_carets(benchmark):
    # difflib.ndiff costs ~175x a plain pair of prints, and is guarded by a length cutoff. Rendering is
    # lazy, so str() has to be called or the carets never run and the benchmark guards nothing.
    left = "the quick brown fox jumps over the lazy dog " * 3
    right = left.replace("brown", "brawn", 1)

    def run():
        try:
            assert_that(left).is_equal_to(right)
        except AssertionFailure as failure:
            return str(failure)
        return None

    benchmark(run)


def test_wide_dict_diff(benchmark):
    # _dict_repr over a wide mapping where nearly every key differs, so there is little to collapse and
    # every entry is rendered. (The cap on how many are named is free at runtime, so nothing guards it.)
    left = {f"k{i}": i for i in range(200)}
    right = {f"k{i}": -i for i in range(200)}

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_extracting_large(benchmark):
    # the success path of the collection pipeline, the common shape of an API assertion
    records = _records(300)
    benchmark(lambda: assert_that(records).extracting("id", "name").is_not_empty())


def test_contains_only_large(benchmark):
    # membership both ways over a sizeable list, the multiset engine rather than the ordered one
    items = list(range(300))
    benchmark(lambda: assert_that(items).contains_only(*items))


def test_shifted_list_diff(benchmark):
    # the alignment path: one element inserted at the head, which positional pairing would report as a
    # difference at every later index. difflib runs on the failure path only, so this is where it costs
    left, right = list(range(500)), list(range(1, 500))

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_shifted_records_diff(benchmark):
    # the same shift over unhashable elements, which difflib cannot index directly: the alignment falls
    # back to keying on reprs, and rendering 500 dict reprs is the price
    left = _records(500)
    right = _records(500)[1:]

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_unshifted_list_diff(benchmark):
    # the alignment loses here and the walk stays positional, so this measures what the losing branch
    # costs everyone whose sequence did not shift: no common run exists, and the opcodes are computed
    # and thrown away
    left = [value * 2 for value in range(500)]
    right = [value * 2 + 1 for value in range(500)]

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_long_records_one_field_diff(benchmark):
    # the common QA failure: a long list of records with one field changed. Pairing by index already
    # yields the single entry an alignment could, so this is the case that must not pay for difflib
    left = _records(200)
    right = _records(200)
    right[199]["profile"]["city"] = "changed"

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_over_cap_list_diff(benchmark):
    # past _ALIGN_MAX_ELEMENTS the alignment is skipped entirely, which is the branch that keeps a
    # quadratic search off a very large failure
    left, right = list(range(2000)), list(range(1, 2000))

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


# Everything above hands the library a payload - 200 records, a wide dict, a 2000-element list - and
# measures how well it walks it. The fixed price of a single assertion disappears into that. It is
# also the only price most consuming suites ever pay: thousands of small assertions on small values,
# where nothing is walked and the whole cost is getting in and out of the builder. A regression in
# `assert_that()` itself, in the soft-mode ContextVar read, or in the per-link chaining overhead moves
# nothing in the benchmarks above and everything in a real test run.
#
# One assertion is too small to read on its own, so these repeat a fixed count and are read as the
# cost of that many assertions.
_ASSERTIONS = 1000


def test_builder_construction(benchmark):
    # `assert_that(...)` with nothing asserted: the ContextVar lookup that decides soft mode, and the
    # builder dispatch on the value's type. this is the floor every other assertion is charged
    def run():
        for index in range(_ASSERTIONS):
            assert_that(index)  # assertpy2: allow-dangling

    benchmark(run)


def test_scalar_equality_pass(benchmark):
    # the same construction plus the cheapest terminal assertion there is. read against the floor
    # above, the difference is what a passing `is_equal_to` costs with no structure to walk
    def run():
        for index in range(_ASSERTIONS):
            assert_that(index).is_equal_to(index)

    benchmark(run)


def test_short_chain_pass(benchmark):
    # what assertions look like in a suite that is not testing assertpy2: several links on one small
    # value, where the cost is per-link overhead rather than data
    def run():
        for _ in range(_ASSERTIONS):
            assert_that("user-42").is_not_none().is_instance_of(str).starts_with("user").is_length(7)

    benchmark(run)
