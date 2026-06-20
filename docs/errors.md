# Errors & Reporting

## Structured errors

A failing assertion raises `AssertionFailure`, a subclass of `AssertionError` that carries structured
data. Existing `except AssertionError` handlers keep working unchanged.

```python
from assertpy2 import assert_that

try:
    assert_that(1).is_equal_to(2)
except AssertionError as e:
    print(e.actual)     # 1
    print(e.expected)   # 2
```

For comparisons, a `DiffResult` with path-level entries is attached:

```python
try:
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 99})
except AssertionError as e:
    print(e.diff)
    # DiffResult(kind='dict', entries=[DiffEntry(path='b', actual=2, expected=99)])
```

When the pytest plugin is active (auto-registered via the `pytest11` entry point, no configuration
needed), this data is rendered as extra report sections. See [Rich pytest diffs](#rich-pytest-diffs)
for supported types and configuration.

## Rich pytest diffs

When `is_equal_to()` or `contains()`/`contains_exactly()` fail, the `DiffResult` on the exception is
rendered by the plugin as colored diff sections.

| Type | Diff kind | How it works |
|---|---|---|
| `list`, `tuple` | `sequence` | Element-by-element, recursive into nested dicts/dataclasses/models |
| `set`, `frozenset` | `set` | Extra and missing items |
| `str` | `string` | Line-by-line comparison |
| `dict` | `dict` | Key-by-key, recursive into nested dicts and lists |
| `dataclass` | `dataclass` | Field-by-field, handles differing types with overlapping fields |
| `namedtuple` | `namedtuple` | Field-by-field comparison |
| Pydantic model | `model` | Field-by-field via `model_dump()`, recursive into nested models |
| other | `scalar` | Single actual-vs-expected entry |
| `contains` family | `contains` | Missing and extra items |

```
--- AssertionFailure ---
  actual:   [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
  expected: [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Robert'}]
--- Structured Diff ---
diff (sequence):
  [1].name:
    - 'Bob'
    + 'Robert'
```

Nested structures are diffed recursively and report the exact path to the differing value (for example
`[1].name`). Circular references are detected and shown as `<circular ref>` rather than recursing
forever.

### Configuration

```toml
[tool.pytest.ini_options]
assertpy2_diff = "off"              # disable structured diff sections entirely
assertpy2_diff_max_entries = "100"  # max entries to show (default 50, 0 = unlimited)
```

With `--color=yes`, diffs are colored: red removals, green additions, cyan headers. Entries beyond
the limit are hidden behind a `... and N more entries` summary.

## Failure and expected exceptions

### fail()

Force a test failure explicitly:

```python
from assertpy2 import fail

fail("forced failure")
```

### Expected exceptions

For a called function, assert it raises and chain assertions on the message:

```python
assert_that(some_func).raises(RuntimeError).when_called_with("foo")
assert_that(some_func).raises(RuntimeError).when_called_with("foo").is_equal_to("some err")
```

Or assert it does **not** raise a given exception:

```python
assert_that(safe_func).does_not_raise(ValueError).when_called_with("foo")
```

!!! tip
    For the common "did it raise?" case without inspecting the message, prefer pytest's
    `pytest.raises` context manager.

### Expected warnings

For a called function, assert it emits a warning and chain assertions on the warning message:

```python
assert_that(deprecated_func).warns(DeprecationWarning).when_called_with("foo")
assert_that(deprecated_func).warns(DeprecationWarning).when_called_with("foo").matches("since 2.6")
```

The category defaults to `Warning` (matches any warning) and matches subclasses. Or assert it does
**not** emit a given category:

```python
assert_that(safe_func).does_not_warn(DeprecationWarning).when_called_with("foo")
```

!!! warning "Not thread-safe"
    `warns()` / `does_not_warn()` rely on `warnings.catch_warnings()`, which mutates process-global
    state. They are safe within a single thread (including multiple `asyncio` tasks on one event
    loop), but concurrent use across OS threads can interfere - the same limitation as
    `pytest.warns` and `unittest.assertWarns`.

### Custom error messages

`described_as()` prepends a custom label to the failure message:

```python
assert_that(1 + 2).described_as("adding stuff").is_equal_to(2)
# [adding stuff] Expected <3> to be equal to <2>, but was not.
```

### Warnings instead of failures

For defensive assertions outside tests, replace `assert_that` with `assert_warn`: failures log a
warning instead of raising:

```python
assert_warn("foo").is_length(4)   # logs a warning, does not raise
```

!!! note "`assert_warn()` vs `warns()`"
    These are unrelated despite the similar names. `assert_warn(...)` is a *soft* entry point: the
    assertion still checks your value, but logs a warning instead of raising on failure.
    `assert_that(func).warns(...)` is the opposite direction - it asserts that calling `func`
    *emits* a Python warning.

??? note "Warning output and custom logger"
    ```
    2019-10-27 20:00:35 WARNING [app.py:42]: Expected <foo> to be of length <4>, but was <3>.
    ```

    Pass your own logger for custom formatting:

    ```python
    assert_warn("foo", logger=my_logger).is_length(4)
    ```
