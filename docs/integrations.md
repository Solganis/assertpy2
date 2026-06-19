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
  "kind": "dict",
  "entries": [
    {"path": "user.settings.theme", "actual": "'dark'", "expected": "'light'"},
    {"path": "user.settings.lang", "actual": "'en'", "expected": "'ru'"}
  ]
}
```

An **AssertionFailure** attachment (mode `full` only) with actual and expected values:

```json
{
  "actual": "{'name': 'Alice', 'age': 30}",
  "expected": "{'name': 'Alice', 'age': 25}"
}
```

Regardless of Allure mode, the plugin always adds human-readable sections to the pytest terminal output:

```
--- AssertionFailure ---
  actual:   {'name': 'Alice', 'age': 30}
  expected: {'name': 'Alice', 'age': 25}
--- Structured Diff ---
diff (dict):
  at age: actual=<30>, expected=<25>
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
