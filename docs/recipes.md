# Patterns & recipes

Task-oriented recipes for common testing jobs. Each one is a small, copy-pasteable pattern; follow the
links into the guides and [API reference](reference/overview.md) for the full surface.

## Test an HTTP API response

Assert the status, then validate the body's *shape* so dynamic fields (ids, timestamps) never make the
test brittle. Use a [matcher](guides/matchers.md) per volatile field and a literal for the fixed ones:

<!-- docs-guard: skip -->
```python
resp = client.get("/orders/42")

assert_that(resp.status_code).is_equal_to(200)
assert_that(resp.json()).matches_structure({
    "id": match.is_positive(),
    "status": match.is_in("paid", "pending", "shipped"),
    "customer": {"name": match.is_non_empty_string()},
})
```

The body check itself is an ordinary value assertion, so it runs without a live server:

```python
body = {"id": 42, "status": "paid", "customer": {"name": "Alice"}}
assert_that(body).matches_structure({
    "id": match.is_positive(),
    "status": match.is_in("paid", "pending", "shipped"),
    "customer": {"name": match.is_non_empty_string()},
})
```

When you have an OpenAPI spec, assert the whole body against the operation's response schema with
[`conforms_to_openapi()`](guides/data.md#conforms_to_openapi); with a Pydantic model, reach for
[`assert_conforms()`](concepts/type-safety.md#contract-narrowing-with-assert_conforms), which also
narrows the chain to the model's type.

## Ignore volatile fields (ids, timestamps)

For a full-value comparison where a few fields change every run, name them with `placeholders`
(asserted separately by a matcher) or drop them with `ignore`:

```python
actual = {"id": "3f9a", "name": "Alice", "created_at": "2026-01-01T00:00:00Z"}

assert_that(actual).matches_structure({
    "id": match.matches_regex(r"[0-9a-f]+"),
    "name": "Alice",
    "created_at": match.is_non_empty_string(),
})
```

`is_equal_to(ignore=...)` does the same for object graphs (dataclasses, attrs, Pydantic models), by key,
nested path, regex, or type - see [Selective comparison](guides/assertions.md#selective-comparison-ignore--include).

## Choose a snapshot style

Store the expected value in a **file** with `snapshot()`, or **inline** in the test source with
`matches_inline()`. Record both the same way - run `pytest --assertpy2-snapshot-update` - and both honor
the same selective knobs and CI mode:

<!-- docs-guard: skip -->
```python
def test_report():
    # file snapshot -> __snapshots/snap-test_report.json
    assert_that(build_report()).snapshot()
    # inline snapshot -> the literal is written into this line
    assert_that(build_summary()).matches_inline()
```

Use inline for small, literal-able values you want to read next to the test; use file snapshots for
large payloads or values that need a custom serializer (`datetime`, `Decimal`, a domain object). Inline
snapshots need the `[inline]` extra (`pip install assertpy2[inline]`). See
[Snapshot testing](guides/testing.md#snapshot-testing).

## Assert on a filtered, mapped collection

Chain the collection pipeline to narrow a list before asserting, instead of writing a loop:

```python
orders = [
    {"id": 1, "total": 100, "status": "paid"},
    {"id": 2, "total": 50, "status": "pending"},
    {"id": 3, "total": 200, "status": "paid"},
]

assert_that(orders).filtered_on(lambda order: order["status"] == "paid").mapped(
    lambda order: order["total"]
).contains_only(100, 200)
```

`first()`, `last()`, `single()`, and `element(i)` pivot to one element; `flat_mapped()` flattens. See
[Collection pipeline](guides/fluent.md#collection-pipeline).

## Collect every failure in one run

A soft-assertion block reports all failures at once instead of stopping at the first, with a `file:line`
for each - ideal for validating many fields of one object:

```python
from assertpy2 import soft_assertions

user = {"name": "Alice", "age": 30, "email": "alice@example.com"}
with soft_assertions():
    assert_that(user["name"]).is_not_empty()
    assert_that(user["age"]).is_between(0, 120)
    assert_that(user["email"]).contains("@")
```

See [Soft assertions](guides/testing.md#soft-assertions).

## Test exceptions and their cause chain

Capture an exception with `raises().when_called_with()`, then keep asserting on it - the message, the
cause chain, or a member of an `ExceptionGroup`:

```python
def load(value):
    try:
        int(value)
    except ValueError as error:
        raise RuntimeError("load failed") from error

assert_that(load).raises(RuntimeError).when_called_with("x").caused_by(ValueError)
```

`raised()` pivots to the exception object, `has_root_cause()` walks the whole chain, and
`contains_error()` matches inside an `ExceptionGroup` - see
[Expected exceptions](guides/errors.md#expected-exceptions).

## Wait for eventual consistency

When a value settles asynchronously (a queue drains, a cache warms), poll with `eventually()` (async) or
`eventually_sync()` (blocking) instead of `sleep`; a timeout reports a convergence trace:

<!-- docs-guard: skip -->
```python
await assert_that(queue_depth).eventually().within(10).is_zero()
```

See [Polling assertions](guides/testing.md#async-assertions).

## Keep the value, statically narrowed

An assertion hands the value back, narrowed for the type checker, so you can assert and use it in one
step without a `cast` or a bare `assert`:

```python
value = assert_that("hello world").is_not_none().is_instance_of(str).value
assert_that(value.upper()).is_equal_to("HELLO WORLD")
```

`is_not_none()` strips `None`, `is_instance_of()` narrows to the class; the returned `.value` carries the
narrowed type. See [Typed narrowing](concepts/type-safety.md#typed-narrowing-with-value).

## Add a project-specific assertion

Register a reusable matcher for a domain rule once, then use it everywhere via `match.*` or `satisfies()`:

<!-- docs-guard: skip -->
```python
from assertpy2 import register_matcher

register_matcher(
    "is_valid_sku", lambda value: bool(re.fullmatch(r"[A-Z]{3}-\d{4}", value))
)

assert_that("ABC-1234").satisfies(match.is_valid_sku())
```

For a whole family of chainable assertions on your own type, use `add_extension` - see
[Custom assertions](extending/custom-assertions.md).

## When full structural comparison is too much

For a very large object, comparing the whole thing is slow and the diff is noisy. Extract just the parts
you care about and assert on those:

```python
response = {
    "id": "abc-123",
    "items": [{"sku": "A"}, {"sku": "B"}],
    "meta": {"total": 2, "page": 1},
}

assert_that(response["items"]).is_length(2)
assert_that(response).has_json_path("$.meta.total")
assert_that(response["meta"]["total"]).is_equal_to(2)
```

`extracting()` pulls a field or JSON path off every element of a collection; `has_json_path()` and
`at_json_path()` navigate into a nested payload. This keeps the failure focused on the field that broke.

## Migrate an assertion from plain `assert`

Replace a cluster of bare asserts with one fluent chain - fewer statements, a structured diff on failure,
and type-aware autocomplete:

```python
items = ["viewer", "editor", "admin"]

# before: three statements, no diff, no autocomplete
assert isinstance(items, list)
assert len(items) == 3
assert "admin" in items

# after: one chain
assert_that(items).is_instance_of(list).is_length(3).contains("admin")
```

More before/after pairs, including `unittest` and the original `assertpy`, are on the
[Migration page](getting-started/migration.md).
