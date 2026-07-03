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

!!! note
    Soft mode collects *assertion* failures only. After a failed `raises()` / `warns()` +
    `when_called_with()` inside a soft context there is no captured value to assert on, so the rest
    of that one chain becomes inert and is skipped silently; independent assertions that follow are
    collected as usual.

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

    Polling itself is always strict - retrying requires hard failures - but the final timeout
    failure honors the builder's mode: inside `soft_assertions()` it is collected instead of
    raised, and under `assert_warn()` it is logged.

### Polling trace

Every poll is recorded, so a timeout failure diagnoses itself instead of just reporting that time ran
out. The message carries a one-line trend - `probe raised ConnectionError on all 12 polls`, `value
unchanged across 12 polls`, or `value changed 3 times; last change 0.4s before the deadline` - which
immediately separates "the service never came up" from "it converged to the wrong value" from "the
timeout is too short". The raised `AssertionFailure` carries the full timeline as `.trace` (a
[`PollTrace`][assertpy2.errors.PollTrace] of per-poll samples, identical consecutive polls collapsed),
the pytest report gets a `Polling Trace` section:

```text
polled 9 times over 5.0s; probe recovered after 2 raising polls; value then changed 1 time
  t=+0.0s error x2: ConnectionError('boot')
  t=+0.5s fail x2: Expected <{'status': 'PENDING'}> to be equal to <{'status': 'PAID'}>, but was not.
  t=+1.5s fail x5: Expected <{'status': 'SHIPPED'}> to be equal to <{'status': 'PAID'}>, but was not.
```

and Allure receives a typed `Polling Trace` JSON attachment including diffs between consecutive
distinct samples. Sample values are point-in-time snapshots (safe even when the probe mutates and
returns the same object), capped by the same limits as other attachments; long polls keep the first 5
and last 20 samples. In soft/warn modes the message keeps the trend line; the full trace object
travels only with the strict `AssertionFailure`.

## Snapshot testing

Capture a data structure to disk as JSON and compare against it on every run. Borrowed from
[Jest](https://jestjs.io/).

```python
assert_that({"a": 1, "b": 2, "c": 3}).snapshot()
```

On the first run the snapshot file is created, a `SnapshotCreatedWarning` is emitted, and the test
passes; on later runs the value is compared to the stored snapshot and the test fails on any mismatch.
Most Python structures are supported (`dict`, `list`, `set`, objects, numbers, `None`, complex). Commit
snapshot artifacts (the `__snapshots` folder) to source control.

!!! note
    The capture warning makes a first run visible - a wrong first capture would otherwise silently
    become the reference. Under `-W error` (or `filterwarnings = ["error"]`) a new capture fails
    explicitly, which is usually what you want in CI.

### Updating snapshots

Delete the snapshot files and re-run the suite to regenerate them.

### Parameters

Snapshots are keyed by test filename plus line number by default; override with `id` or `path`:

```python
assert_that({"a": 1}).snapshot(id="my-custom-id")
assert_that({"a": 1}).snapshot(path="my-custom-folder")
```

### Volatile fields and float noise

The comparison accepts the same selective options as `is_equal_to()` - `ignore`, `include`,
`tolerance`, and `comparators` - so timestamps, generated ids, or float jitter don't break snapshots.
The snapshot file always stores the full value; the options only shape the comparison:

```python
assert_that(api_response).snapshot(id="order", ignore=["created_at", ("user", "session_id")])
assert_that(metrics).snapshot(id="latency", tolerance=0.001)
assert_that(payload).snapshot(id="user", comparators={"name": lambda a, e: a.lower() == e.lower()})
```

### Known limitations

- **Tuples round-trip as lists** (JSON has no tuple), so a snapshot of `(1, 2)` compares as `[1, 2]`
  on the next run and fails. Convert tuples before snapshotting.
- **Supported types** are the JSON natives plus `set`, `complex`, `datetime.datetime` (including
  microseconds), and objects with a `__dict__`. `datetime.date`, `datetime.time`, `Decimal`, and
  `bytes` raise `TypeError` on capture.
- **Snapshot ids are case-insensitive**: filenames are lower-cased, so ids differing only by case
  collide in one file.
- **The write lock is not crash-safe**: a process killed mid-write leaves a stale `.lock` file next
  to the snapshot; delete it if snapshot writes start timing out.
