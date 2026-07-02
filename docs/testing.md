# Testing

## Soft assertions

By default a failure halts the test immediately. Soft assertions collect failures and raise them
together at the end, so one run reports every problem:

```python
from assertpy2 import assert_that, soft_assertions

with soft_assertions():
    assert_that("foo").is_length(4)
    assert_that("foo").is_empty()
    assert_that("foo").is_equal_to("bar")
```

??? failure "Collected failures raised at the end of the block"
    ```
    AssertionError: soft assertion failures:
    1. Expected <foo> to be of length <4>, but was <3>.
    2. Expected <foo> to be empty string, but was not.
    3. Expected <foo> to be equal to <bar>, but was not.
    ```

!!! note
    Only assertion failures are collected. Errors like `TypeError`/`ValueError` and an explicit `fail()`
    halt immediately; use `soft_fail()` to collect a forced failure. Soft state is thread-safe and
    async-safe (independent per thread and per `asyncio.Task` via `contextvars`).

## Grouped soft assertions

Bind the collector with `as sa` and group failures by section with `sa.group(label)`:

```python
with soft_assertions() as sa:
    with sa.group("Headers"):
        assert_that(headers["Content-Type"]).is_equal_to("application/json")
    with sa.group("Body"):
        assert_that(body["status"]).is_equal_to("ok")
```

??? failure "Grouped output"
    ```
    soft assertion failures:
      [Headers]
        1. Expected <text/html> to be equal to <application/json>, but was not.
      [Body]
        2. Expected <error> to be equal to <ok>, but was not.
    ```

### assert_all

A convenience wrapper for inline soft assertions, equivalent to wrapping the calls in
`with soft_assertions():`:

```python
from assertpy2 import assert_all, assert_that

assert_all(
    lambda: assert_that(x).is_positive(),
    lambda: assert_that(y).is_not_none(),
    lambda: assert_that(z).is_length(3),
)
```

## Async assertions

`eventually()` creates a polling assertion that retries until the condition holds or a timeout is
reached, useful for eventual consistency and reactive systems:

```python
async def test_status_converges():
    await assert_that(get_status).eventually().is_equal_to("ready")
```

By default it polls for 5 seconds every 0.5 seconds; tune with `within()` and `every()`:

```python
await assert_that(get_count).eventually().within(10).every(0.2).is_greater_than(100)
```

Both sync and async callables work, and any assertion method is available after `eventually()`:

```python
await assert_that(async_get_status).eventually().is_equal_to("done")
await assert_that(get_name).eventually().starts_with("Al")
await assert_that(get_count).eventually().is_between(10, 20)
```

By default only a failing assertion is retried: any exception raised by the probe itself propagates
immediately. When "not ready yet" manifests as an exception (a connection refused while a service
boots, a record not yet visible), list those exception types in `ignoring`:

```python
await assert_that(get_order).eventually(timeout=10, ignoring=ConnectionError).has_status("PAID")

# or configure fluently, like within()/every()
await assert_that(get_order).eventually().within(10).ignoring(ConnectionError, TimeoutError).has_status("PAID")
```

!!! note
    Only `AssertionError` (plus any `ignoring` types) is retried; other exceptions propagate
    immediately. On timeout the last failure is chained for context. `ignoring` accepts only
    `Exception` subclasses, so `KeyboardInterrupt` and friends can never be swallowed.

## Snapshot testing

Capture a data structure to disk as JSON and compare against it on every run. Borrowed from
[Jest](https://jestjs.io/).

```python
assert_that({"a": 1, "b": 2, "c": 3}).snapshot()
```

On the first run the snapshot file is created and the test passes; on later runs the value is compared
to the stored snapshot and the test fails on any mismatch. Most Python structures are supported
(`dict`, `list`, `set`, objects, numbers, `None`, complex). Commit snapshot artifacts (the
`__snapshots` folder) to source control.

### Updating snapshots

Delete the snapshot files and re-run the suite to regenerate them.

### Parameters

Snapshots are keyed by test filename plus line number by default; override with `id` or `path`:

```python
assert_that({"a": 1}).snapshot(id="my-custom-id")
assert_that({"a": 1}).snapshot(path="my-custom-folder")
```
