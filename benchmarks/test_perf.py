# CodSpeed regression gate: micro-benchmarks of assertpy2's own hot paths, measured commit-over-commit
# under CPU simulation. Run manually with `uv run --group benchmark pytest benchmarks/ --codspeed --no-cov`;
# the CodSpeed CI job runs the same. Not collected by the default suite (testpaths=tests), so it never gates
# on the machine's noise - only CodSpeed's simulated instruction count does.
#
# The local run prints a "Time (best)" column that is not a measurement: a callable taking 95 us of wall
# clock was reported as 85 ns, and the ordering of two cases came out reversed. Read `Run time / Iters`
# if a local number is wanted at all.
from __future__ import annotations

import contextlib
from dataclasses import dataclass

import pytest

from assertpy2 import assert_that, match
from assertpy2._clustering import clusters, observations_of, render
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
    left, right = _records(200), _records(200)
    benchmark(lambda: assert_that(left).is_equal_to(right))


def test_is_equal_to_nested_diff(benchmark):
    left, right = _records(200), _records(200)
    right[199]["profile"]["city"] = "changed"

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_matches_structure_with_matchers(benchmark):
    records = _records(200)

    def run():
        for record in records:
            assert_that(record).matches_structure(_SPEC)

    benchmark(run)


def test_dataclass_diff(benchmark):
    left = [_Row(i, f"n{i}", ["a", "b"]) for i in range(200)]
    right = [_Row(i, f"n{i}", ["a", "b"]) for i in range(200)]
    right[199].tags = ["a", "c"]

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_contains_exactly_large(benchmark):
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
    left = {f"k{i}": i for i in range(200)}
    right = {f"k{i}": -i for i in range(200)}

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_extracting_large(benchmark):
    records = _records(300)
    benchmark(lambda: assert_that(records).extracting("id", "name").is_not_empty())


def test_contains_only_large(benchmark):
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


# Everything above measures how the library walks a payload. These measure the fixed price of one
# assertion, which is what most suites actually pay: thousands of small assertions where nothing is
# walked. A regression in `assert_that()`, in the soft-mode ContextVar read or in per-link chaining
# moves nothing above and everything in a real run. One assertion is too small to time, so each
# repeats a fixed count.
_ASSERTIONS = 1000


def test_builder_construction(benchmark):
    def run():
        for index in range(_ASSERTIONS):
            assert_that(index)

    benchmark(run)


def test_scalar_equality_pass(benchmark):
    def run():
        for index in range(_ASSERTIONS):
            assert_that(index).is_equal_to(index)

    benchmark(run)


def test_short_chain_pass(benchmark):
    def run():
        for _ in range(_ASSERTIONS):
            assert_that("user-42").is_not_none().is_instance_of(str).starts_with("user").is_length(7)

    benchmark(run)


# The membership relations used to cost `len(a) * len(b)` comparisons, so a collection of a few thousand
# elements spent the whole assertion inside `in`.  Two sizes rather than one: the pair is what shows the
# shape, since a quadratic path grows 400x between them where a linear one grows 20x.
@pytest.mark.parametrize("size", [100, 2000])
def test_contains_only_pass(benchmark, size):
    values = list(range(size))
    items = tuple(range(size))
    benchmark(lambda: assert_that(values).contains_only(*items))


@pytest.mark.parametrize("size", [100, 2000])
def test_matcher_is_subset_of_pass(benchmark, size):
    values = list(range(size))
    superset = list(range(size + 1))
    benchmark(lambda: assert_that(values).satisfies(match.is_subset_of(superset)))


@pytest.mark.parametrize("size", [100, 2000])
def test_duplicates_reported(benchmark, size):
    # the failing side on purpose: naming the repeats is the part that used to count each element again.
    # The failure is required rather than suppressed: swallowing it would leave the benchmark green and
    # silently timing a passing assertion if the duplicate ever stopped being found
    values = [*range(size), 0]

    def run():
        try:
            assert_that(values).does_not_contain_duplicates()
        except AssertionFailure:
            return
        raise RuntimeError("the duplicate was not reported, so this measures the wrong path")

    benchmark(run)


# Polling and clustering run per *poll* and per *failing test* rather than per assertion, so their cost
# is multiplied by a loop nobody writes. The flight recorder is on by default and walks the probed value
# twice, once to sanitise a sample and once to key it for change: a failing poll over two hundred
# records measured 2.2 ms against 0.11 ms with the recorder off. Each case fixes the number of polls and
# checks it, so a benchmark cannot silently time a shape it did not intend.
_POLLS = 10

_WIDE_FAIL, _WIDE_PASS = _records(200), _records(200)
_WIDE_FAIL[199]["profile"]["city"] = "changed"


def _replays(steps: int) -> int:
    """Link calls a chain of *steps* makes: each link polls once as it is added, then all are replayed."""
    links = steps - 1
    return sum(range(steps)) + (_POLLS + 1 - links) * links


def _polled(failing, settling, *, trace=True, steps=1):
    """A runnable poll, reporting the polls it spent and the link calls the replay made."""

    def run():
        seen = {"n": 0, "links": 0}

        def probe():
            seen["n"] += 1
            return settling if seen["n"] > _POLLS else failing

        def link(_):
            seen["links"] += 1
            return True

        builder = assert_that(probe).eventually_sync(timeout=3600, interval=0, trace=trace)
        for _ in range(steps - 1):
            builder = builder.satisfies(link)
        # the links count themselves, so a replay that skipped them cannot pass for one that ran
        builder.is_equal_to(settling)
        return seen["n"], seen["links"]

    return run


@pytest.mark.parametrize("trace", [True, False], ids=["recorder-on", "recorder-off"])
def test_polling_a_scalar(benchmark, trace):
    run = _polled(41, 42, trace=trace)
    assert run() == (_POLLS + 1, _replays(1))
    benchmark(run)


@pytest.mark.parametrize("trace", [True, False], ids=["recorder-on", "recorder-off"])
def test_polling_a_wide_value(benchmark, trace):
    # the same loop over two hundred records, where the assertion walks the payload as well. The pair
    # isolates the recorder because both sides run that same assertion: it is 95% of a failing poll
    # here against a quarter of one over the scalar above
    run = _polled(_WIDE_FAIL, _WIDE_PASS, trace=trace)
    assert run() == (_POLLS + 1, _replays(1))
    benchmark(run)


@pytest.mark.parametrize("steps", [1, 5], ids=["one-step", "five-steps"])
def test_polling_replays_the_whole_chain(benchmark, steps):
    run = _polled(41, 42, steps=steps)
    assert run() == (_POLLS + 1, _replays(steps))
    benchmark(run)


def _wide_failure(differing: int):
    left, right = _records(200), _records(200)
    for index in range(differing):
        right[index]["profile"]["city"] = "changed"
    with pytest.raises(AssertionFailure) as failure:
        assert_that(left).is_equal_to(right)
    return failure.value.diff


def test_clustering_a_failure(benchmark):
    diff = _wide_failure(50)
    assert len(diff.entries) == 50
    benchmark(lambda: observations_of(diff))


def test_clustering_a_whole_run(benchmark):
    recorded = [(f"test_{index}", observations_of(_wide_failure(1))) for index in range(40)]
    assert len(clusters(recorded, 40)) == 1
    benchmark(lambda: render(clusters(recorded, 40), 40))
