# assertpy2

Fluent, fully type-aware assertions for Python.

`assertpy2` is a modern fork of `assertpy`: readable `assert_that(...)` chains,
composable matchers, structural matching, type-narrowing assertions and contract testing, soft and async
assertions, and a pytest plugin that renders rich structural diffs on failure.

## Why assertpy2

<div class="grid cards" markdown>

-   :material-shield-check:{ .lg .middle } __Typed overloads__

    ---

    `assert_that("hello").` offers only string methods, `assert_that(42).` only numeric ones, and a type
    checker rejects `assert_that("foo").is_positive()` before the test runs. The core advantage over
    `assertpy` and most alternatives.

    [:octicons-arrow-right-24: Type safety](concepts/type-safety.md)

-   :material-target:{ .lg .middle } __Typed narrowing & contracts__

    ---

    An assertion **returns the value it checked, statically narrowed** (`.value` after `is_not_none()` /
    `is_instance_of()`), and `assert_conforms()` validates a payload against a Pydantic model and narrows
    to it - no `cast`, no bare `assert`.

    [:octicons-arrow-right-24: Typed narrowing](concepts/type-safety.md#typed-narrowing-with-value)

-   :material-puzzle:{ .lg .middle } __Composable matchers__

    ---

    `match.greater_than(5)`, `match.is_uuid()`, combined with `&`, `|`, `~`, reusable across assertions.

    [:octicons-arrow-right-24: Matchers](guides/matchers.md)

-   :material-file-tree:{ .lg .middle } __Structural matching__

    ---

    Declarative validation of dicts, Pydantic models, and API responses, with the exact path to each
    mismatch on failure.

    [:octicons-arrow-right-24: Structural matching](guides/matchers.md#structural-matching)

-   :material-timer-sand:{ .lg .middle } __Soft & async assertions__

    ---

    Collect multiple failures in one run; poll for eventual consistency with `eventually()` (async) or
    `eventually_sync()` (blocking).

    [:octicons-arrow-right-24: Testing](guides/testing.md)

-   :material-alert-circle:{ .lg .middle } __Expected exceptions__

    ---

    `raises().when_called_with()`, then assert on the message, walk the cause chain (`caused_by()`,
    `has_root_cause()`), match an `ExceptionGroup` (`contains_error()`), or pivot to the exception object
    (`raised()`).

    [:octicons-arrow-right-24: Errors & reporting](guides/errors.md#expected-exceptions)

-   :material-format-list-checks:{ .lg .middle } __Structured failures__

    ---

    `AssertionFailure` exposes `.actual`, `.expected`, and `.diff`; the pytest plugin renders recursive
    diffs for lists, dicts, dataclasses, namedtuples, attrs classes, and Pydantic models.

    [:octicons-arrow-right-24: Errors & reporting](guides/errors.md)

-   :material-table:{ .lg .middle } __Data frames & arrays__

    ---

    pandas / polars / numpy data-frame and array assertions, alongside Allure and Behave integrations.

    [:octicons-arrow-right-24: Integrations](extending/integrations.md)

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
