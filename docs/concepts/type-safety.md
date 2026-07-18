# Type Safety

Type safety is what sets `assertpy2` apart from `assertpy` and most alternatives. `assert_that()` is
overloaded, so the value you pass decides which assertions you get back - a *type-specific* set, not one
generic `Any`:

```python
assert_that("hello").starts_with("he")  # string assertions
assert_that(42).is_positive()           # numeric assertions
assert_that([1, 2, 3]).contains(2)      # collection assertions
```

Your editor offers only the methods that fit the value, and a type checker rejects misuse before the
test ever runs.

## Type-aware autocomplete

Each value type gets its own typed Protocol - string, numeric, collection, dict, date, path, bytes, and
callable - with a generic fallback for anything else. Your IDE then suggests only the methods relevant to
the value under test, not all 100+:

- `assert_that("hello").` → string methods: `starts_with`, `matches`, `is_alpha`, `is_lower`, ...
- `assert_that(42).` → numeric methods: `is_positive`, `is_between`, `is_close_to`, ...
- `assert_that(["a", "b"]).` → collection methods: `contains`, `contains_exactly`, `is_sorted`, `extracting`, ...
- `assert_that({"id": 1}).` → dict methods: `contains_key`, `contains_entry`, `has_json_path`, ...
- `assert_that(Path("/tmp")).` → path methods: `exists`, `is_file`, `is_directory`, `is_readable`, ...
- `assert_that(b"\x89PNG").` → bytes methods: `starts_with_bytes`, `is_valid_utf8`, `decoded_as`, ...

| Value type | Protocol returned |
|---|---|
| `str` | string assertions |
| `int` / `float` / `complex` | numeric assertions |
| `list` / `tuple` / `set` / `frozenset` | collection assertions |
| `dict` | dict assertions |
| `datetime.date` / `datetime.datetime` | date assertions |
| `pathlib.Path` | path assertions |
| `bytes` / `bytearray` | bytes assertions |
| any callable | callable assertions (`raises`, `warns`, `eventually`, ...) |
| anything else | the universal core assertions |

The precise type is preserved through the chain (every assertion returns `Self`), so the suggestions stay
relevant from the first call to the last.

## Misuse caught before the test runs

Because each overload is typed, a type checker flags an assertion that does not apply to the value, or an
argument of the wrong type, without running anything:

```python
# type error: is_positive is not a string assertion
assert_that("foo").is_positive()
# type error: expected `type`, got `str`
assert_that(42).is_instance_of("int")
```

[ty](https://github.com/astral-sh/ty), [mypy `--strict`](https://github.com/python/mypy), and
[Pyright](https://github.com/microsoft/pyright) all report these in the editor and in CI, turning a class
of test bugs into errors you see while typing.

Every public `assert_that` overload is pinned by an `assert_type` check in
[`tests/test_typing.py`](https://github.com/Solganis/assertpy2/blob/main/tests/test_typing.py). CI runs
all three checkers against that file on every push, with **zero suppressions**, so a regression that
broadens or changes a return type fails the build. `ty` additionally type-checks the whole package.

!!! note "Callables and captured values stay typed too"
    `assert_that(func).raises(...).when_called_with(...)` exposes string assertions on the captured
    message, and `returned()` pivots to the type-agnostic core assertions for the call's return value -
    never advertising methods that may not apply. See [Errors & Reporting](../guides/errors.md#expected-exceptions).

## Typed narrowing with .value

Assertions don't just check a value - they can hand it back, typed. The `value` property ends a chain
by returning the checked value as-is.

For object- and union-typed values, two assertions refine its static type along the way: `is_not_none()`
removes `None`, and `is_instance_of()` narrows to the checked class. The usual `assert x is not None` /
`cast()` dance to satisfy a type checker disappears:

```python
order: Order | None = repo.find_order(42)

paid = assert_that(order).is_not_none().is_instance_of(PaidOrder).value
paid.refund()  # statically typed as PaidOrder - no cast, no bare assert
```

On the per-type protocols `value` returns the family type (`str` for string assertions, `dict` for
dict assertions, ...), so extract-and-continue works after pivots too:

```python
name = assert_that(b"fred").decoded_as().is_length(4).value  # typed as str
```

Collection assertions are generic over the element type, so element-access pivots
(`first()`/`last()`/`element()`/`single()`) narrow the chain to the element - a list of models stays
typed all the way down:

```python
orders: list[Order] = repo.all_orders()
# first()/last()/element()/single(): Order
total = assert_that(orders).first().value.total
# re-typed to list[float]
mapped = assert_that(orders).mapped(lambda o: o.total).value
```

Java's AssertJ approximates this with `asInstanceOf(InstanceOfAssertFactories...)` at runtime.
Here the narrowing is purely static - checked by ty, mypy, and Pyright - with zero runtime cost
beyond returning the value.

!!! note "The narrowing is sound in every mode"
    `.value` never hands back a value that contradicts its narrowed type, and that guarantee holds in
    every mode - not just strict:

    - **Strict** (the `assert_that` default): a failed `is_not_none()` or `is_instance_of()` halts the
      chain before `.value` is reached, so the value genuinely matches the narrowed type.
    - **Soft / warn** (inside [`soft_assertions()`](../guides/testing.md#soft-assertions) or under
      `assert_warn()`): a failure is *collected* instead of halting, so reading `.value` would read past
      an unestablished fact. Rather than leak a value that could violate its static type, `.value`
      **raises** `TypeError` - and a pivot like `first()` or `extracting()` rejects the untrusted value
      on its own input check.

    Either way nothing unsound escapes: in soft mode you get an exception, never a wrong-typed value.
    Read `.value` in strict mode, or after the soft block has closed.

    (The narrowed builder also exposes the full assertion API rather than the type-filtered subset,
    since an arbitrary narrowed class has no per-type protocol.)

### Refinement narrowing with a TypeIs predicate (advanced)

`is_not_none()` and `is_instance_of()` are two built-in narrowers. `satisfies()` extends narrowing
to **your own** predicates: pass a predicate typed with [`TypeIs`](https://peps.python.org/pep-0742/)
and it narrows the chain to the guarded type. Unlike `is_instance_of()`, which narrows by class only,
a `TypeIs` predicate narrows by any runtime condition - a refinement type:

```python
from typing import TypeIs  # or `from typing_extensions import TypeIs` on Python < 3.13

def is_paid(order: Order) -> TypeIs[PaidOrder]:
    return isinstance(order, PaidOrder) and order.status == "PAID"

paid = assert_that(order).is_not_none().satisfies(is_paid).value
# statically typed as PaidOrder - narrowed by a domain predicate, not just a class
paid.refund()
```

The runtime behavior of `satisfies()` is unchanged (it just runs the predicate). The narrowing is
purely static.

!!! warning "Checker support: not yet in PyCharm"
    This narrowing is solved by **ty, Pyright, and mypy** today, so it works in VS Code / Pylance and in
    CI. **PyCharm does not yet solve type variables through `TypeIs`**: there the result stays the
    un-narrowed type, and accessing a narrowed-only member reports a false *Unresolved attribute
    reference*. It is tracked upstream in
    [JetBrains PY-89124](https://youtrack.jetbrains.com/issue/PY-89124). When that ships, the narrowing
    lights up in PyCharm with no change here.

    Until then, on PyCharm:

    - prefer `is_instance_of()` for class narrowing (which PyCharm *does* narrow)
    - treat `satisfies()`-based refinement narrowing as advanced / checker-dependent
    - don't disable the *Unresolved attribute reference* inspection to work around it - it is a core
      check. Scope any workaround to the specific line.

### Contract narrowing with assert_conforms

`is_instance_of()` narrows a value that is *already* an instance. `assert_conforms()` goes one step
further - it **validates a raw payload against a pydantic v2 model and continues over the validated
instance**, narrowing the chain to that model. It is the capstone for API-response testing: parse,
validate, and type in one step.

```python
from pydantic import BaseModel

from assertpy2 import assert_conforms, assert_that

class Order(BaseModel):
    id: int
    total: float

# .value: Order (validated and coerced)
order = assert_conforms(response.json(), Order).value
assert_that(order.total).is_greater_than(0)
```

`assert_conforms(payload, Order)` runs `Order.model_validate(payload)`: on failure the assertion fails
with pydantic's validation errors. On success it returns a builder over the validated, coerced
instance, so `.value` hands back a typed `Order`. It needs pydantic installed.

`assert_conforms` is a **function**, not a method on the builder, and that is deliberate. A method
(`assert_that(payload).conforms_to(Order)`) can only narrow when the payload's own static type is
narrowable - so the dominant case, the `Any` a `response.json()` decodes to, would stay `Any`, and an
explicitly `dict`-typed payload would stay `dict`.

Because `assert_conforms` drives its return type from the `model` argument instead of from the payload,
it narrows to `Order` for **every** input, `Any` included. And since it yields a class-narrowed builder
(the same mechanism as `is_instance_of()`), the narrowing lights up in PyCharm too, not only the CLI
checkers.

A **list endpoint** (a JSON array of objects) validates element-by-element with `each=True`, narrowing
the chain to `list[Order]`:

```python
orders = assert_conforms(response.json(), Order, each=True).value  # .value: list[Order]
assert_that(orders).extracting("total").contains(199.0)
```

`each=True` validates every item against `Order`, reporting `item [i]` on the first that fails, and
composes with `exact=True` for per-element drift (drift paths are prefixed with the element index, e.g.
`[3].promo_code`).

### Contract drift with `exact=True`

`model_validate` **silently drops** fields the model does not declare, so a stale model keeps passing
after the live API grows new fields - your test is green while the contract has drifted.

`exact=True` catches that: it fails when the payload carries any field the model does not declare,
recursively into nested sub-models and lists, reporting the exact paths.

```python
# response grew a `promo_code` field, and its nested customer grew `loyalty_tier`
assert_conforms(response.json(), OrderModel, exact=True)
```
```text
Expected <{...}> to conform exactly to <OrderModel>, but it carries 2 undeclared field(s)
the model does not declare: ['customer.loyalty_tier', 'promo_code']
```

A few refinements keep it precise:

- it is **alias-aware** - an aliased payload key is not mistaken for drift - and respects a model that
  opts into extras (`model_config = ConfigDict(extra="allow")`)
- it reports only **structural** drift (undeclared fields), not type coercions: a `datetime` field
  legitimately arrives as a JSON string, so flagging coercions would be noise
- it is stricter and more informative than pydantic's model-level `extra="forbid"` - per-call, and it
  names every drifted path.

## Set up your type checker

The narrowing works in any checker mode, but strict mode surfaces the most - a wrong method called on a
narrowed value, a missing return annotation, a `.value` read where the type was never narrowed. Turn it
on for your checker:

```toml
# pyproject.toml - mypy
[tool.mypy]
strict = true
```

```toml
# pyproject.toml - Pyright / Pylance  (or "typeCheckingMode": "strict" in pyrightconfig.json)
[tool.pyright]
typeCheckingMode = "strict"
```

`ty` needs no configuration - it reads the types out of the box. All three pick up `assertpy2`'s types
automatically via the `py.typed` marker below. There is no stub package to install.

## py.typed and PEP 561

`assertpy2` ships a `py.typed` marker and is [PEP 561](https://peps.python.org/pep-0561/) compliant, so the
types are picked up automatically by any project that depends on it - no stub package, no extra config.

## Editor support

The overloads are plain typing with no runtime cost, so type-aware autocomplete works in PyCharm, VS Code
(Pylance), and any LSP-compatible editor out of the box.
