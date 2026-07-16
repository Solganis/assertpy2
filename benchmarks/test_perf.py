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
