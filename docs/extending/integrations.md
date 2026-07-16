# Integrations

## Allure

When `allure-pytest` is installed, the assertpy2 pytest plugin automatically attaches structured failure
data to Allure reports as JSON attachments. No code changes needed.

!!! note "Optional dependency"
    ```bash
    pip install assertpy2[allure]
    ```

### Attachment modes

Control what gets attached via the `assertpy2_allure` ini option:

| Mode | Structured Diff | Actual/Expected |
|---|:---:|:---:|
| `diff` (default) | Yes | No |
| `full` | Yes | Yes |
| `off` | No | No |

```toml
[tool.pytest.ini_options]
assertpy2_allure = "full"
```

### What gets attached

A **Structured Diff** attachment (modes `diff`, `full`) with a path-level breakdown:

```json
{
  "format": 2,
  "kind": "dict",
  "entries": [
    {"path": "user.settings.theme", "actual": "dark", "expected": "light"},
    {"path": "user.settings.retries", "actual": 3, "expected": 5}
  ]
}
```

Values are native JSON (numbers, strings, booleans, nested objects and arrays), so the Allure viewer
renders them as a collapsible tree and downstream tooling can parse them.

Anything JSON cannot express degrades to a marked fallback instead of failing the attachment:

- `{"__repr__": "..."}` for arbitrary objects, datetimes, non-finite floats, and circular references;
- `{"__type__": "set", "__data__": [...]}` for sets.

Oversized values are capped: strings at 4000 chars, containers at 100 items.

An **AssertionFailure** attachment (mode `full` only) with actual and expected values:

```json
{
  "format": 2,
  "actual": {"name": "Alice", "age": 30},
  "expected": {"name": "Alice", "age": 25}
}
```

A **Polling Trace** attachment (modes `diff`, `full`) when an
[`eventually()`](../guides/testing.md#polling-trace) assertion times out, with per-poll samples and diffs
between consecutive distinct values:

```json
{
  "format": 2,
  "kind": "polling-trace",
  "total_polls": 9,
  "elapsed": 5.0,
  "summary": "probe recovered after 2 raising polls; value then changed 1 time",
  "samples": [
    {"t": 0.0, "outcome": "error", "detail": "ConnectionError('boot')", "repeats": 2},
    {"t": 0.5, "outcome": "fail", "value": {"status": "PENDING"}, "detail": "Expected ...", "repeats": 2}
  ],
  "deltas": [
    {"from_t": 0.5, "to_t": 1.5, "entries": [{"path": "status", "actual": "PENDING", "expected": "SHIPPED"}]}
  ]
}
```

The `format` field versions the attachment schema (`2` = typed values; attachments without the field
are the older repr-string format), so downstream tooling can branch explicitly.

Regardless of Allure mode, the plugin always adds human-readable sections to the pytest terminal output:

```
--- AssertionFailure ---
  actual:   {'name': 'Alice', 'age': 30}
  expected: {'name': 'Alice', 'age': 25}
--- Structured Diff ---
diff (dict):
  age:
    - 30
    + 25
```

!!! note
    If Allure is not installed or `allure.attach()` fails, the plugin silently continues; test results
    are never affected. An invalid mode value falls back to `diff` with a warning.

## Behave

assertpy2 provides ready-made parameter types for [Behave](https://behave.readthedocs.io/) step
definitions that parse and validate step parameters automatically.

!!! note "Optional dependency"
    ```bash
    pip install assertpy2[behave]
    ```

Register the types once, typically in `environment.py` or a step file:

```python
from assertpy2.behave_matchers import register_assertpy_types

register_assertpy_types()
```

### Available types

| Type | Pattern | Description | Example input |
|---|---|---|---|
| `PositiveInt` | `\d+` | Integer > 0 | `1`, `42`, `100` |
| `NonNegativeInt` | `\d+` | Integer >= 0 | `0`, `1`, `42` |
| `PositiveFloat` | `\d+\.?\d*` | Float > 0 | `1.5`, `42`, `0.01` |
| `NonEmptyString` | `.+?` | Stripped non-blank string | `hello`, `foo bar` |
| `BoolLike` | `\w+` | Boolean from text | `true`, `yes`, `1`, `on`, `false`, `no`, `0`, `off` |

```python
@given("a user aged {age:PositiveInt}")
def step_user_aged(context, age):
    context.age = age  # int, guaranteed > 0

@given("the feature is {enabled:BoolLike}")
def step_feature_toggle(context, enabled):
    context.enabled = enabled  # bool

@when("the user searches for {query:NonEmptyString}")
def step_search(context, query):
    context.query = query  # str, stripped, non-blank
```

Invalid values raise `ValueError` with a descriptive message (for example, `expected positive integer,
got 0`).

### Using types directly

The `ASSERTPY_TYPES` dict exposes the parsers without Behave:

```python
from assertpy2.behave_matchers import ASSERTPY_TYPES

parse_int = ASSERTPY_TYPES["PositiveInt"]
value = parse_int("42")  # 42
```

## Data frames and arrays

Fluent equality assertions for [pandas](https://pandas.pydata.org/),
[polars](https://pola.rs/) and [numpy](https://numpy.org/). These types compare element-wise, so a
plain `is_equal_to()` cannot reduce them to a single truth value.

Instead it raises a clear `TypeError` pointing you to the methods below - including when the array or
frame sits nested inside a dict, dataclass, or list under comparison.

!!! note "Optional dependency"
    Each library is its own extra, so you only install what you use (a polars user does not pull in
    pandas or numpy):
    ```bash
    pip install assertpy2[pandas]    # or assertpy2[polars], or assertpy2[numpy]
    pip install assertpy2[data]      # convenience: all three at once
    ```

### DataFrames and Series

`is_frame_equal()` works on both pandas and polars `DataFrame` and `Series`. Comparison **semantics are
the library's own**: it delegates to `pandas.testing.assert_frame_equal` /
`polars.testing.assert_frame_equal` (and the `assert_series_equal` variants), so dtype strictness, row
and column order, tolerance and categoricals behave exactly as that library defines.

Any keyword options are forwarded straight through.

```python
import pandas as pd
from assertpy2 import assert_that

assert_that(pd.DataFrame({"a": [1, 2]})).is_frame_equal(pd.DataFrame({"a": [1, 2]}))

# forward options to the underlying assert_frame_equal:
assert_that(actual).is_frame_equal(expected, check_dtype=False)
assert_that(actual).is_frame_equal(expected, check_exact=False, rtol=1e-3)
```

```python
import polars as pl

assert_that(pl.DataFrame({"a": [1, 2]})).is_frame_equal(pl.DataFrame({"a": [1, 2]}))
```

On failure the library's own detailed diff is carried in the assertion message.

### numpy arrays

Two array assertions, both accepting any array-like numpy can coerce:

- `is_array_equal()` - exact, via `numpy.testing.assert_array_equal`;
- `is_array_close_to()` - float-tolerant, via `numpy.testing.assert_allclose`, for comparing computed
  arrays.

```python
import numpy as np
from assertpy2 import assert_that

assert_that(np.array([1, 2, 3])).is_array_equal(np.array([1, 2, 3]))
assert_that(np.array([1.0, 2.0])).is_array_close_to(np.array([1.0, 2.0000001]))
assert_that(computed).is_array_close_to(expected, rtol=1e-3, atol=1e-6)
```

!!! note "Delegated semantics"
    This integration adds only the fluent entry point and routes failures through the standard
    assertpy2 error model (so soft assertions, `described_as`, and warn mode all apply). The actual
    comparison is always the source library's, never a reimplementation.
