# assertpy2

Fluent, fully type-aware assertions for Python.

`assertpy2` is a modern fork of `assertpy`: readable `assert_that(...)` chains,
composable matchers, structural matching, soft and async assertions, and a pytest plugin that renders
rich structural diffs on failure.

## Why assertpy2

- **Typed overloads.** `assert_that("hello").` offers only string methods, `assert_that(42).` only numeric
  ones, and a type checker rejects `assert_that("foo").is_positive()` before the test runs. The core
  advantage over `assertpy` and most alternatives - [see how it works](type-safety.md).
- **Composable matchers.** `match.greater_than(5)`, `match.is_uuid()`, combined with `&`, `|`, `~`.
- **Structural matching.** Declarative validation of dicts, Pydantic models, and API responses, with the exact path to each mismatch on failure.
- **Soft and async assertions.** Collect multiple failures; poll for eventual consistency with `eventually()`.
- **Structured failures.** `AssertionFailure` exposes `.actual`, `.expected`, and `.diff`; the pytest plugin
  renders recursive diffs for lists, dicts, dataclasses, namedtuples, and Pydantic models.

## Install

```bash
pip install assertpy2
```

Optional extras: `assertpy2[json]` (JSONPath / JSON Schema), `assertpy2[allure]`, `assertpy2[behave]`.

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

See [Getting Started](getting-started.md) to dive in, or browse [Type Assertions](assertions.md),
[Matchers](matchers.md), and the rest of the navigation for the full set of assertions and integrations.
