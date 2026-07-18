# assertpy2

Fluent, fully type-aware assertions for Python.

A drop-in, fully typed fork of `assertpy` - the same fluent `assert_that(...)` chains, but the type
checker follows every one, and each assertion hands back the value it checked, statically narrowed.

```python
from assertpy2 import assert_that

# port is a typed int - the value the chain checked, narrowed
port = assert_that(8080).is_instance_of(int).is_positive().value
```

## Why assertpy2

<div class="grid cards" markdown>

-   :material-shield-check:{ .lg .middle } __Typed overloads__

    ---

    String methods on strings, numeric methods on numbers - the type checker rejects the wrong ones
    before the test even runs. The core advantage over `assertpy` and most alternatives.

    [:octicons-arrow-right-24: Type safety](concepts/type-safety.md)

-   :material-target:{ .lg .middle } __Typed narrowing & contracts__

    ---

    An assertion **returns the value it checked, statically narrowed** to the asserted type - so `.value`
    is typed, with no `cast` and no bare `assert`. `assert_conforms()` does the same against a Pydantic
    model.

    [:octicons-arrow-right-24: Typed narrowing](concepts/type-safety.md#typed-narrowing-with-value)

-   :material-puzzle:{ .lg .middle } __Composable matchers__

    ---

    Predicate matchers you combine with the `&`, `|`, and `~` operators and reuse across assertions - or
    register your own.

    [:octicons-arrow-right-24: Matchers](guides/matchers.md)

-   :material-file-tree:{ .lg .middle } __Structural matching__

    ---

    Declarative validation of dicts, Pydantic models, and API responses, with the exact path to each
    mismatch on failure.

    [:octicons-arrow-right-24: Structural matching](guides/matchers.md#structural-matching)

-   :material-timer-sand:{ .lg .middle } __Soft & async assertions__

    ---

    Collect multiple failures in one run. Poll for eventual consistency with `eventually()` (async) or
    `eventually_sync()` (blocking).

    [:octicons-arrow-right-24: Testing](guides/testing.md)

-   :material-alert-circle:{ .lg .middle } __Expected exceptions__

    ---

    Assert that a call raises, then chain onto the message, the cause chain, an `ExceptionGroup`, or the
    exception object itself.

    [:octicons-arrow-right-24: Errors & reporting](guides/errors.md#expected-exceptions)

-   :material-format-list-checks:{ .lg .middle } __Structured failures__

    ---

    Failures carry machine-readable `.actual`, `.expected`, and `.diff`. The diff renders into the message
    itself and, under pytest, as colored sections for dicts, dataclasses, attrs, and Pydantic models.

    [:octicons-arrow-right-24: Errors & reporting](guides/errors.md)

-   :material-camera:{ .lg .middle } __Snapshot testing__

    ---

    External-file, in-source, and value-tolerant contract snapshots - all three under one selective,
    typed API, with inline recording under `pytest-xdist`.

    [:octicons-arrow-right-24: Snapshots](guides/testing.md#snapshot-testing)

-   :material-table:{ .lg .middle } __Data frames & arrays__

    ---

    pandas / polars / numpy data-frame and array assertions, alongside Allure and Behave integrations.

    [:octicons-arrow-right-24: Integrations](extending/integrations.md)

-   :material-api:{ .lg .middle } __JSON & API assertions__

    ---

    Navigate JSON with JSON Path, validate it against a JSON Schema or an OpenAPI response contract, and
    pull values out with regex groups - built for API and service tests.

    [:octicons-arrow-right-24: JSON & data](guides/data.md)

</div>

## Install

```bash
pip install assertpy2
```

Optional extras:

- `assertpy2[json]` - JSONPath, JSON Schema, and OpenAPI contracts
- `assertpy2[inline]` - inline snapshots (`matches_inline()`)
- `assertpy2[data]` - pandas / polars / numpy
- `assertpy2[allure]` - Allure reporting
- `assertpy2[behave]` - Behave step matchers

## Quick example

```python
from assertpy2 import assert_that, match

assert_that("foobar").is_length(6).starts_with("foo").ends_with("bar")
assert_that([1, 2, 3]).contains(1).is_subset_of([1, 2, 3, 4])
assert_that({"id": 1, "name": "Alice"}).matches_structure(
    {"id": match.is_instance_of(int), "name": match.is_non_empty_string()}
)
```

When a check fails, the pytest plugin points at the exact field instead of dumping both structures:

<!-- docs-guard: skip -->
```python
assert_that(response).matches_structure({
    "user": match.structure({
        "name": match.is_non_empty_string(),
        "role": match.is_in("admin", "user"),
        "age": match.between(18, 120),
    }),
})
```

![Structured diff in the terminal: every failing field with its path and the predicate that failed, in color](assets/diff-match.svg)

See [Quickstart](getting-started/quickstart.md) to dive in, or browse [Type assertions](guides/assertions.md),
[Matchers](guides/matchers.md), and the rest of the navigation for the full set of assertions and integrations.
