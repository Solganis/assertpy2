# Testing

## Soft assertions

By default a failure halts the test immediately. Soft assertions collect failures and raise them
together at the end, so one run reports every problem - and each collected failure carries its
`file:line`, so you can jump straight to the assertion that failed:

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
    1. Expected <foo> to be of length <4>, but was <3>.  [test_str.py:12]
    2. Expected <foo> to be empty string, but was not.  [test_str.py:13]
    3. Expected <foo> to be equal to <bar>, but was not.  [test_str.py:14]
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
        1. Expected <text/html> to be equal to <application/json>, but was not.  [test_api.py:37]
      [Body]
        2. Expected <error> to be equal to <ok>, but was not.  [test_api.py:39]
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

### Synchronous polling

`eventually_sync()` is the same polling assertion without asyncio: assertion methods block the
calling thread (via `time.sleep`) instead of returning coroutines, so it drops straight into plain
non-async tests:

```python
def test_status_converges():
    assert_that(get_status).eventually_sync(timeout=10, interval=0.2).is_equal_to("ready")

# within()/every()/ignoring() work the same way
assert_that(get_order).eventually_sync().within(10).ignoring(ConnectionError).has_status("PAID")
```

Retry rules, soft/warn behavior, and the polling trace are identical to `eventually()`. The one
difference: the probe must be a sync callable - a probe that returns an awaitable raises
`TypeError` (poll async probes with `eventually()` and `await`).

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

The recorder can be switched off per assertion with `trace=False` (on both `eventually()` and
`eventually_sync()`) for the rare case where a near-zero interval meets a heavy probed value and
even point-in-time snapshots cost too much; the timeout failure then reports just the last failure.

## Snapshot testing

Capture a data structure to disk as JSON and compare against it on every run.

```python
assert_that({"a": 1, "b": 2, "c": 3}).snapshot()
```

On the first run the snapshot file is created, a `SnapshotCreatedWarning` is emitted, and the test
passes; on later runs the value is compared to the stored snapshot and the test fails on any mismatch.
Most Python structures are supported (`dict`, `list`, `set`, objects, numbers, `None`, `complex`,
`datetime`/`date`/`time`, `Decimal`, `bytes`). Commit snapshot artifacts (the `__snapshots` folder)
to source control.

!!! note
    The capture warning makes a first run visible - a wrong first capture would otherwise silently
    become the reference. Under `-W error` (or `filterwarnings = ["error"]`) a new capture fails
    explicitly, which is usually what you want in CI.

### Updating snapshots

Run pytest with `--assertpy2-snapshot-update` and every failing snapshot comparison overwrites the
stored value instead of failing. Each overwrite emits a `SnapshotUpdatedWarning`, so the run reports
exactly which snapshots changed; matching snapshots are left untouched, and the comparison options
(`ignore`, `tolerance`, ...) are honored when deciding whether a snapshot is stale:

```bash
pytest --assertpy2-snapshot-update
```

For runners other than pytest, set the `ASSERTPY2_SNAPSHOT_UPDATE=1` environment variable instead.
Deleting the snapshot files and re-running the suite still works too - each fresh capture emits a
`SnapshotCreatedWarning`.

### CI mode

A first run *creates* a missing snapshot and passes - handy locally, but in CI it means a snapshot test
whose golden was never committed creates it in the ephemeral workspace, passes, and silently disables
drift detection. Enable CI mode to make a missing snapshot a hard failure instead:

```bash
pytest --assertpy2-snapshot-ci
```

It is also auto-enabled when a `CI` environment variable is set (the near-universal CI marker), or via
`ASSERTPY2_SNAPSHOT_CI=1`. Disable the autodetection with `--assertpy2-snapshot-no-ci` or
`ASSERTPY2_SNAPSHOT_CI=0`. Local runs are unaffected.

### Obsolete snapshots

When a test is deleted its stored snapshot lingers on disk. At the end of a run assertpy2 reports
snapshots it did not touch:

```text
assertpy2 snapshots:
  obsolete snapshot (run --assertpy2-snapshot-update on a full run to remove): __snapshots/snap-test_orders.json::42
  obsolete snapshot file (delete manually if its test is gone): __snapshots/snap-test_legacy.json
```

Reporting is always safe. Removal is deliberately conservative: an obsolete sub-snapshot (a line-number
key in a file whose module still ran) is pruned only under update mode on a *full* run, so a run
narrowed by `-k`, `-m`, `--lf`, or `--ff` never deletes a snapshot that only looks unused because its
test was deselected. A whole obsolete file is only ever reported, never auto-deleted. Under
`pytest-xdist` the touched-snapshot sets from all workers are aggregated on the controller first, so a
snapshot exercised on another worker is never mistaken for an orphan.

### Inline snapshots

An inline snapshot keeps the expected value **in the test source** instead of a separate file. Call
`matches_inline()` empty, record it once with `--assertpy2-snapshot-update`, and the literal is written
back into the call:

```python
# before recording
assert_that(client.get("/orders/1").json()).matches_inline()

# after `pytest --assertpy2-snapshot-update`
assert_that(client.get("/orders/1").json()).matches_inline({"id": 1, "status": "paid"})
```

Later runs compare against the literal, and update mode overwrites it on drift - just like `snapshot()`.
The same selective knobs apply, so volatile fields never make the snapshot brittle:

```python
assert_that(order).matches_inline(
    {"id": 0, "total": 42.0}, placeholders={"id": match.is_uuid()}, tolerance=0.01
)
```

A recorded literal holds the value captured on that run, so a placeholder field shows the captured `id`
rather than the `0` above - the placeholder governs the comparison, not what is written.

Recording needs the `[inline]` extra (`pip install assertpy2[inline]`); the **comparison** does not -
it is a plain equality check, so it runs under `pytest-xdist` and needs no source introspection or
assertion rewriting. Under xdist the recorded edits are shipped to the controller and applied once,
never written by workers in parallel.

Inline snapshots hold source **literals**, so only JSON-ish values work (a `dict`/`list`/`tuple`/`set`
of scalars). For a `datetime`, `Decimal`, `UUID`, or a custom object use `snapshot()` instead - the two
are complementary, sharing the same update flag, CI mode, selective comparison, and structured diff.

### Custom types

Beyond the built-in codec (`set`, `complex`, `datetime`/`date`/`time`, `Decimal`, `bytes`, `UUID`,
`Enum`), register a serializer for any other type so `snapshot()` stores and round-trips it instead of
raising:

```python
from assertpy2 import register_snapshot_serializer
import pathlib

register_snapshot_serializer(pathlib.PurePath, str, pathlib.PurePath)
```

Matching is by `isinstance` (subclasses included), the registry is consulted before the built-ins, and
a later registration wins. The `decode` half runs your own code on load, so it is a trusted, explicit
opt-in - unlike the automatic instance decode, which never imports.

### Contract snapshots

`snapshot()` compares exact values, so a response full of generated ids and timestamps needs `ignore`
or `placeholders` to stay stable. When you care about the response's *shape* rather than its values,
reach for `matches_contract_snapshot()`: it records the structure - paths and type categories, never
values - and on later runs fails only on **structural** drift (a field added, removed, or retyped).

```python
assert_that(response.json()).matches_contract_snapshot()
```

It is value-tolerant by construction, so dynamic ids, timestamps, and amounts (and `5` vs `5.0`) change
freely; a real contract change fails with the drifted paths:

```text
Expected <{...}> to match contract snapshot <...>, but the structure drifted:
  + promo_code
  ~ id number -> str
```

No hand-written model is needed - the contract is inferred from the first response, and it shares the
same storage, update mode, and CI mode as `snapshot()`. The model-driven counterpart is
[`assert_conforms(..., exact=True)`](../concepts/type-safety.md#contract-drift-with-exacttrue): reach for that when
you already have a pydantic model. Because a contract is inferred from a single observation it cannot
know which fields are optional, so a legitimately sometimes-absent field reads as `removed`; re-record
with update mode when the contract really changed.

### Shape placeholders

`comparators` and `ignore` make the *comparison* tolerate volatile fields, but the golden still stores
the arbitrary value captured on the first run. `placeholders` instead records a self-documenting shape
token in the golden and asserts the field's shape on every run:

```python
from assertpy2 import match

assert_that(response).snapshot(
    id="order", placeholders={"id": match.is_uuid(), "created_at": lambda ts: isinstance(ts, str)}
)
```

The golden reads `"id": {"__placeholder__": "a valid UUID string"}` instead of a specific id, and each
run asserts the actual field is present and satisfies the matcher (a `Matcher` or a callable predicate)
rather than comparing it for equality. Every other field is still compared exactly, so drift outside
the placeholders is caught. Placeholders apply to top-level keys of a *dict-like* value and combine
with `ignore`.

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
- **Supported types** are the JSON natives plus `set`, `complex`, `datetime.datetime` (microseconds
  and timezone-aware included), `datetime.date`, `datetime.time`, `Decimal`, `bytes`/`bytearray`
  (stored base64-encoded, compared as `bytes`), `uuid.UUID`, `Enum` members, and objects with a
  `__dict__`. Anything else can be handled with
  [`register_snapshot_serializer()`](#custom-types); an unregistered value without a JSON form (e.g.
  `frozenset`) raises `TypeError` on capture.
- **Snapshot ids are case-insensitive**: filenames are lower-cased, so ids differing only by case
  collide in one file.
- **The write lock is not crash-safe**: a process killed mid-write leaves a stale `.lock` file next
  to the snapshot; delete it if snapshot writes start timing out.
