# Comparison

assertpy2 is the only library compared here that gives you the fluent, matcher, and `==` styles in a
single import, then goes further with type-narrowing assertions, contract testing, thread- and async-safe soft assertions, async
polling, and structured failures. The tables below are a side-by-side comparison with the
common alternatives.

!!! success "In short"
    assertpy2 unifies the fluent, matcher, and `==` styles in one typed package,
    then adds thread- and async-safe soft assertions, async polling, structured failures, and rich
    pytest diffs. It ships **39 composable matchers** and **over 100 assertion methods** across **12 value types**,
    with no runtime dependencies on Python 3.11+. One import, all three styles.

## The approaches

- **pytest `assert`** rewrites plain `assert` statements to produce detailed introspection on failure.
  There is no API to learn and the failure output is excellent, but there are no reusable conditions and
  no fluent chaining.
- **PyHamcrest** is a matcher framework: `assert_that(value, is_(greater_than(5)))`. assertpy2 provides
  the same composable-matcher model (`&`, `|`, `~`, custom matchers) inside a typed fluent API.
- **assertpy** (the original) introduced the fluent `assert_that(x).is_...()` chaining this project is
  built on. Its last release is `1.1` (2020) and it has no static typing. assertpy2 is
  its successor and substantially expands the assertion set - adding the entire bytes
  family, more string and collection assertions, structural matching, the collection pipeline, JSON
  Path/Schema, regex group extraction, async polling, universal negation, and composable matchers on top
  of the original. See [Migrating from assertpy](migration.md) to switch.
- **dirty-equals** (mis)uses `__eq__` so you can write `assert response == {"id": IsPositive(), ...}`.
  assertpy2 matchers work the same way inside `==`, so the same single dependency covers this style too.

## In code

The same check - `id` is a positive integer and `name` is a non-empty string - in each library:

=== "assertpy2"

    ```python
    from assertpy2 import assert_that, match

    assert_that(response).matches_structure({
        "id": match.is_positive(),
        "name": match.is_non_empty_string(),
    })

    # or the dirty-equals style, no wrapper:
    assert response == {"id": match.is_positive(), "name": match.is_non_empty_string()}
    ```

=== "pytest assert"

    ```python
    assert response["id"] > 0
    assert isinstance(response["name"], str) and response["name"]
    ```

=== "PyHamcrest"

    ```python
    from hamcrest import assert_that, has_entries, greater_than, instance_of, all_of, not_, empty

    assert_that(response, has_entries({
        "id": greater_than(0),
        "name": all_of(instance_of(str), not_(empty())),
    }))
    ```

=== "assertpy"

    ```python
    from assertpy import assert_that

    assert_that(response["id"]).is_positive()
    assert_that(response["name"]).is_not_empty()
    ```

=== "dirty-equals"

    ```python
    from dirty_equals import IsPositiveInt, IsStr

    assert response == {"id": IsPositiveInt, "name": IsStr(min_length=1)}
    ```

Only assertpy2 offers both the typed structural form and the `==` form from a single import.

## When it fails

A nested response, after `role` comes back as `"superadmin"`. What each library prints on failure:

=== "assertpy2"

    ```text
    assert_that(response).matches_structure({...})
    --- Structured Diff ---
    diff (match):
      user.role: expected a value in <('admin', 'user')>, but was 'superadmin'
    ```

=== "pytest assert"

    ```text
    assert response == expected
    E   Differing items:
    E   {'user': {'name': 'Alice', 'role': 'superadmin', 'age': 30}} !=
    E   {'user': {'name': 'Alice', 'role': 'admin', 'age': 30}}
    ```

=== "dirty-equals"

    ```text
    assert response == {"user": {"role": IsOneOf("admin", "user"), ...}}
    E   Differing items:
    E   {'user': {'name': 'Alice', 'role': 'superadmin', 'age': 30}} !=
    E   {'user': {'name': IsStr, 'role': IsOneOf('admin', 'user'), 'age': IsInt}}
    ```

Only assertpy2 prints the path (`user.role`) and the exact predicate that failed. dirty-equals and the
assertpy2 `==` form both hand rendering to pytest, which dumps the whole differing container for you to
scan. The fluent form trades the zero-import convenience of `==` for a path-level diff.

### With a Pydantic model

When the value is a Pydantic model, `matches_structure()` accepts it directly, with no `.model_dump()`
step, and prints a path-level diff just like the one above:

```python
assert_that(user).matches_structure({"role": match.is_in("admin", "user")})
```

dirty-equals cannot compare a model against a spec dict, because Pydantic's `__eq__` only matches another
model. You dump it first (`assert user.model_dump() == {"role": IsOneOf("admin", "user")}`), and pytest
again dumps the whole differing container. assertpy2 keeps a path-level diff on a model.

## Style and typing

| | pytest assert | PyHamcrest | assertpy | dirty-equals | **assertpy2** |
|---|:---:|:---:|:---:|:---:|:---:|
| Paradigm | rewritten `assert` | matchers | fluent chain | `==` objects | **[fluent + matchers + `==`](#all-three-styles-one-import)** |
| Mix styles in one suite | No | No | No | No | **[Yes](#all-three-styles-one-import)** |
| Static typing (`py.typed`, overloads) | n/a | No | No | **Typed** | **[Yes](../concepts/type-safety.md)** |
| Autocomplete filtered by value type | No | No | No | No | **[Yes](../concepts/type-safety.md#type-aware-autocomplete)** |
| Typed narrowing (the assertion returns the value, narrowed) | No | No | No | No | **[Yes](../concepts/type-safety.md#typed-narrowing-with-value)** |
| Contract testing (validate a payload and narrow to the model) | No | No | No | No | **[Yes](../concepts/type-safety.md#contract-narrowing-with-assert_conforms)** |
| Fluent chaining | No | No | **Yes** | No | **[Yes](../guides/fluent.md#chaining)** |
| Composable matchers | No | **Yes** | No | **Yes** | **[Yes](../guides/matchers.md)** |
| Works inside plain `==` | n/a | No | No | **Yes** | **[Yes](../guides/matchers.md)** |

## Assertions and matchers

| | pytest assert | PyHamcrest | assertpy | dirty-equals | **assertpy2** |
|---|:---:|:---:|:---:|:---:|:---:|
| Structural matching (nested) | manual | partial | No | **Yes** | **[Yes](../guides/matchers.md#structural-matching)** |
| Recursive comparison (tolerance / comparators / null-skip) | `approx` | No | No | partial | **[Yes](../guides/assertions.md#recursive-comparison-tolerance--custom-comparators)** |
| Collection / ordering assertions | manual | **Yes** | **Yes** | **Yes** | **[Yes](../guides/assertions.md#lists)** |
| Negation of any assertion (`.not_`) | manual | partial | No | partial | **[Yes](../guides/fluent.md#universal-negation)** |
| Collection pipeline (map / filter / flatten / navigate) | manual | No | No | No | **[Yes](../guides/fluent.md#collection-pipeline)** |
| Dynamic attribute assertions (`has_<name>()`) | No | No | **Yes** | No | **[Yes](../guides/assertions.md#dynamic-assertions-on-objects)** |
| Regex group extraction | manual | No | No | No | **[Yes](../guides/data.md#regex-group-extraction)** |
| JSON Path / JSON Schema | No | No | No | `IsJson` only | **[Yes](../guides/data.md)** |
| File / date / bytes assertions | No | No | file, date | date | **[Yes (all)](../guides/assertions.md#files)** |
| Exception cause chains / groups (`caused_by`, `contains_error`) | manual | No | No | No | **[Yes](../guides/errors.md#expected-exceptions)** |
| Data frame / array equality (pandas/polars/numpy) | manual | No | No | No | **[Yes](../extending/integrations.md#data-frames-and-arrays)** |
| Custom assertions or matchers | functions | **Yes** | **Yes** | **Yes** | **[Yes (both)](../extending/custom-assertions.md)** |

## Reporting, safety and tooling

| | pytest assert | PyHamcrest | assertpy | dirty-equals | **assertpy2** |
|---|:---:|:---:|:---:|:---:|:---:|
| Soft assertions | plugin | No | **Yes** | No | **[Yes](../guides/testing.md#soft-assertions)** |
| Soft assertions thread-safe **and** async-safe | n/a | n/a | No | n/a | **[Yes](../guides/testing.md#soft-assertions)** |
| Grouped soft assertions (`sa.group`) | No | No | No | No | **[Yes](../guides/testing.md#grouped-soft-assertions)** |
| Async / sync polling (`eventually()` / `eventually_sync()`) | No | No | No | No | **[Yes](../guides/testing.md#async-assertions)** |
| Structured failure data (`.actual` / `.expected` / `.diff`) | No | No | No | No | **[Yes](../guides/errors.md#structured-errors)** |
| Rich, recursive pytest diffs | built-in | No | No | No | **[Yes](../guides/errors.md#rich-pytest-diffs)** |
| Snapshot testing | plugin | No | **Yes** | No | **[Yes](../guides/testing.md#snapshot-testing)** |
| Warn mode (non-failing assertions) | No | No | **Yes** | No | **[Yes](../guides/errors.md#warnings-instead-of-failures)** |
| Allure / Behave integrations | No | No | No | No | **[Yes](../extending/integrations.md)** |

!!! note "On snapshot testing: where assertpy2 does and does not lead"
    That row compares assertion libraries, not the dedicated snapshot tools - and it is worth being
    straight about the difference. If snapshots are central to your workflow, the specialists lead that
    niche: [syrupy](https://github.com/syrupy-project/syrupy) for external-file snapshots, and
    [inline-snapshot](https://15r10nk.github.io/inline-snapshot/) for in-source snapshots (Pydantic-endorsed,
    with richer `snapshot()` operator semantics like `<=` and `in`).

    assertpy2's snapshot is an external-file (syrupy-family) convenience **bundled with the rest of your
    assertions**, so an occasional snapshot needs no extra tool and no extra dependency - it is not a
    category-leading snapshot engine, and it does not try to be. Where it is genuinely distinct is
    [`matches_contract_snapshot()`](../guides/testing.md#contract-snapshots): a value-tolerant *structural* snapshot
    (paths and type categories, not values) that neither syrupy nor inline-snapshot offers. Rule of thumb:
    reach for a specialist when snapshots are the point; reach for assertpy2's when you want a snapshot
    inline with everything else, or when you want structural (contract) regression rather than value-exact.

## Project health

| | pytest assert | PyHamcrest | assertpy | dirty-equals | **assertpy2** |
|---|:---:|:---:|:---:|:---:|:---:|
| Maintained | built-in | Yes | No | Yes | **Yes** |
| Property-based tests | n/a | No | No | No | **Yes** |
| Mutation testing | n/a | No | No | No | **Yes** |
| Runtime dependencies | **none** | **none** | **none** | **none** | **none on 3.11+** |
| License | MIT | BSD | BSD | MIT | BSD-3 |

!!! note
    The property-based-tests and mutation-testing rows reflect each project's published CI and test
    configuration. assertpy2 ships a [Hypothesis](https://hypothesis.readthedocs.io) suite covering its
    comparison, diff, and matcher logic, plus a
    [cosmic-ray](https://github.com/sixty-north/cosmic-ray) mutation-testing suite, on top of 100% branch
    coverage.

## All three styles, one import

The styles above are not mutually exclusive in assertpy2. A single import and no runtime dependencies
on Python 3.11+ give you all of them at once, and you can mix them freely in the same test suite:

```python
from assertpy2 import assert_that, match

# fluent chaining (the assertpy heritage)
assert_that(value).is_positive().is_less_than(100)

# matchers inside plain == (the dirty-equals style)
assert response == {"id": match.is_positive(), "name": match.is_non_empty_string()}

# composable matchers (the Hamcrest style)
assert_that(value).satisfies(match.greater_than(0) & match.less_than(100))
```

## What only assertpy2 does here

Across the columns above, assertpy2 is the only option that:

- covers the fluent, matcher, and `==` styles in a single import, mixable in one suite, so there is no
  juggling of libraries;
- is statically typed: `@overload` protocols and `py.typed` give autocomplete filtered by the value's
  type and usage verified by a type checker before the test runs;
- **returns the value it checked, statically narrowed** (`.value` after `is_not_none()` / `is_instance_of()`),
  and validates *and* narrows a whole payload against a Pydantic model with `assert_conforms()` - neither of
  which any other tool here does;
- has soft assertions that are both **thread-safe and async-safe** (independent state per thread and per
  `asyncio.Task` via `contextvars`). The original assertpy's soft assertions are not thread-safe, and
  the other tools have no soft assertions at all;
- polls for eventual consistency with `eventually()` (async) and `eventually_sync()` (blocking), for async
  operations and reactive systems;
- attaches structured failure data (`.actual` / `.expected` / `.diff`) and renders rich, recursive
  diffs in pytest reports;
- adds exception cause-chain and group assertions, a collection pipeline, regex group extraction, dynamic
  `has_<name>()` assertions, snapshot testing, JSON Path and Schema validation, file/date/bytes assertions,
  and Allure/Behave integrations.

All of that with no runtime dependencies on Python 3.11+ (one tiny backport on 3.10): breadth that
would otherwise require
several separate libraries.
