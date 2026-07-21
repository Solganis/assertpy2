# Comparison

The tables below compare assertpy2 side-by-side with the common alternatives: pytest's `assert`,
PyHamcrest, the original assertpy, and dirty-equals.

!!! success "In short"
    assertpy2 unifies the fluent, matcher, and `==` styles in one typed package, then adds thread-
    and async-safe soft assertions, async polling, structured failures, and rich pytest diffs.

    It ships **39 composable matchers** and **over 100 assertion methods** across **12 value types**,
    with no runtime dependencies on Python 3.11+.

## All three styles, one import

assertpy2's fluent, matcher, and `==` styles are not mutually exclusive. A single import gives you all
three, mixable in the same test suite:

```python
from assertpy2 import assert_that, match

# fluent chaining (the assertpy heritage)
assert_that(value).is_positive().is_less_than(100)

# matchers inside plain == (the dirty-equals style)
assert response == {"id": match.is_positive(), "name": match.is_non_empty_string()}

# composable matchers (the Hamcrest style)
assert_that(value).satisfies(match.greater_than(0) & match.less_than(100))
```

## The approaches

- **pytest `assert`** rewrites plain `assert` statements to produce detailed introspection on failure.
  There is no API to learn and the failure output is excellent, but there are no reusable conditions and
  no fluent chaining.
- **PyHamcrest** is a matcher framework: `assert_that(value, is_(greater_than(5)))`. assertpy2 provides
  the same composable-matcher model (`&`, `|`, `~`, custom matchers) inside a typed fluent API.
- **assertpy** (the original) introduced the fluent `assert_that(x).is_...()` chaining this project is
  built on. assertpy2 is its typed successor and substantially expands the assertion set. See
  [Migrating from assertpy](migration.md) to switch.
- **dirty-equals** (mis)uses `__eq__` so you can write `assert response == {"id": IsPositive(), ...}`.
  assertpy2 matchers work the same way inside `==`, so the same single dependency covers this style too.

## In code

The same check, that `id` is a positive integer and `name` a non-empty string, in each library:

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
    from hamcrest import (
        assert_that, has_entries, greater_than, instance_of, all_of, not_, empty,
    )

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

Only assertpy2 prints the path (`user.role`) and the exact predicate that failed.

dirty-equals and the assertpy2 `==` form both hand rendering to pytest, which dumps the whole differing
container for you to scan. The fluent form trades the zero-import convenience of `==` for a path-level
diff.

### With a Pydantic model or attrs instance

When the value is a Pydantic model or an `attrs` instance, `matches_structure()` accepts it directly,
with no `.model_dump()` / `attrs.asdict()` step. It is normalized to its fields and printed with a
path-level diff just like the one above:

```python
assert_that(user).matches_structure({"role": match.is_in("admin", "user")})
```

dirty-equals cannot compare a model against a spec dict, because Pydantic's `__eq__` only matches another
model. You dump it first (`user.model_dump() == {"role": IsOneOf(...)}`), and pytest again dumps the
whole differing container. assertpy2 keeps a path-level diff on either.

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
| OpenAPI response-contract validation | No | No | No | No | **[Yes](../guides/data.md#conforms_to_openapi)** |
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
| Convergence trace on a timed-out poll | No | No | No | No | **[Yes](../guides/testing.md#polling-trace)** |
| Guard against an assertion that checked nothing | No | No | No | No | **[Yes](../guides/assertions.md#assertions-that-checked-nothing)** |
| Structured failure data (`.actual` / `.expected` / `.diff`) | No | No | No | No | **[Yes](../guides/errors.md#structured-errors)** |
| Rich, recursive pytest diffs | built-in | No | No | No | **[Yes](../guides/errors.md#rich-pytest-diffs)** |
| Snapshot testing | plugin | No | **Yes** | No | **[Yes](../guides/testing.md#snapshot-testing)** |
| Warn mode (non-failing assertions) | No | No | **Yes** | No | **[Yes](../guides/errors.md#warnings-instead-of-failures)** |
| Allure / Behave integrations | No | No | No | No | **[Yes](../extending/integrations.md)** |

!!! note "On snapshot testing: where assertpy2 does and does not lead"
    That row compares assertion libraries, not the dedicated snapshot tools, and the difference is
    worth being straight about.

    If snapshots are central to your workflow, the specialists lead that niche:
    [syrupy](https://github.com/syrupy-project/syrupy) for external-file snapshots, and
    [inline-snapshot](https://15r10nk.github.io/inline-snapshot/) for in-source snapshots.

    assertpy2 gives you three snapshot styles bundled with the rest of your assertions, with no extra
    tool and no extra dependency:

    - [`snapshot()`](../guides/testing.md#snapshot-testing) - external-file, syrupy-family.
    - [`matches_inline()`](../guides/testing.md#inline-snapshots) - in-source literal. Records correctly
      under `pytest-xdist`, where inline-snapshot disables itself.
    - [`matches_contract_snapshot()`](../guides/testing.md#contract-snapshots) - value-tolerant
      *structural* snapshot (paths and type categories, not values), which neither syrupy nor
      inline-snapshot offers.

    The first two are not category-leading engines, and do not try to be.

    **Rule of thumb:** reach for a specialist when snapshots are the point. Reach for assertpy2's when
    you want a snapshot inline with everything else, or structural regression rather than value-exact.

## What only assertpy2 does here

Across the columns above, assertpy2 is the only option that:

- covers the fluent, matcher, and `==` styles in a single import, mixable in one suite, so there is no
  juggling of libraries
- is statically typed: `@overload` protocols and `py.typed` give autocomplete filtered by the value's
  type and usage verified by a type checker before the test runs
- **returns the value it checked, statically narrowed** (`.value` after `is_not_none()` / `is_instance_of()`),
  and validates *and* narrows a whole payload against a Pydantic model with `assert_conforms()` - neither of
  which any other tool here does
- has soft assertions that are both **thread-safe and async-safe** (independent state per thread and per
  `asyncio.Task` via `contextvars`). The original assertpy's soft assertions are not thread-safe, and
  the other tools have no soft assertions at all
- polls for eventual consistency with `eventually()` (async) and `eventually_sync()` (blocking), and a
  timed-out poll [diagnoses itself](../guides/testing.md#polling-trace): the failure says whether the
  value never moved, cycled between states, or was still converging when time ran out
- [warns when a universal assertion passed over an empty collection](../guides/assertions.md#assertions-that-checked-nothing),
  the silent false pass that a green run never reveals
- attaches structured failure data (`.actual` / `.expected` / `.diff`) and renders rich, recursive
  diffs in pytest reports
- adds exception cause-chain and group assertions, a collection pipeline, regex group extraction, dynamic
  `has_<name>()` assertions, snapshot testing, JSON Path and Schema validation, file/date/bytes assertions,
  and Allure/Behave integrations.
