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

<!-- docs-guard: type-error -->
```python
# type error: is_positive is not a string assertion
assert_that("foo").is_positive()
# type error: expected `type`, got `str`
assert_that(42).is_instance_of("int")
```

The same holds for a relation between two values, not only for a method that does not apply. An
argument is bound to the type of the value under test, so a comparison that could never hold is an
error rather than a test that fails at runtime:

<!-- docs-guard: type-error -->
```python
assert_that([1, 2, 3]).contains("four")            # an item that cannot be in a list of int
assert_that({"id": 1}).contains_key(3.14)          # a key that cannot be in a dict[str, int]
assert_that(1).is_greater_than("wrong type")       # a number against text
assert_that(date.today()).is_before(5)             # a date against a number
assert_that(1).satisfies(match.starts_with("a"))   # a matcher built for another type
```

Where the ordering assertions stop is worth knowing before you rely on them. The line above catches a
number compared against text, because a numeric value reaches a numeric view whose operand is bound.
A value that reaches no view of its own is a different case: it keeps ordering with an operand of any
type, and nothing there is refused.

```python
def what_a_checker_allows(anything: object, someone: Person) -> None:
    assert_that(anything).is_greater_than("text")   # accepted: `object` claims no ordering of its own
    assert_that(someone).is_between(1, 10)          # accepted: so does a class with no view
```

Both run and both fail, with the message the value's own comparison produced. This is deliberate and
it is the second attempt: the first spelling bound the operand to a list of types and rejected
`numpy.int64`, which is a value this library documents support for. A capability covers what a list of
types cannot, and the capability an ordering has is one no annotation can name, so the choice was
between refusing correct comparisons and accepting incorrect ones. Refusing correct code is the worse
of the two, and `tests/typing_cases.py` holds the spellings that were tried.

Comparing an `int` against a `float`, passing a matcher where an item is expected, and every other
ordinary combination keep working. Which relations are refused and which stay accepted is measured
rather than asserted: the file lives in
[`tests/typing_cases.py`](https://github.com/Solganis/assertpy2/blob/main/tests/typing_cases.py) and CI
compares all three checkers against a recorded baseline in both directions.

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

### Where the typed surface ends

A value the library cannot see a use for gets the core surface, not every assertion there is. So a
numeric assertion on a user class is a type error rather than a runtime one:

<!-- docs-guard: type-error -->
```python
assert_that(person).is_positive()   # type error: a plain class has no numeric assertions
```

"Cannot see a use for" is meant literally, and it is narrower than it sounds. Two kinds of value are
unaffected. One is the value with a type of its own, which reaches its own protocol as it always did.
The other is the value with no such type that still answers to something the library uses: an iterable
of your own, an HTTP response from any client, a pydantic-style model, a dataclass, a mapping that is
not a `dict`. Those keep the whole surface, and so does anything typed `Any`, which is what an
unannotated helper or a `json.loads()` result gives you.

What is left is the value annotated `object` and the class that answers to nothing, and for those the
shorter surface is the true one.

That second group is a compatibility trade rather than a clean line, and it is worth knowing which way
it errs. A class that happens to define `__iter__` for a reason of its own keeps all 152 assertion
names, numeric ones included, exactly as before. The rule is deliberately generous: a value the library
might be able to use keeps everything, and only a value it certainly cannot use is narrowed. Erring the
other way would reject calls that work, which is the worse failure of the two.

[Dynamic assertions](../guides/assertions.md#dynamic-assertions-on-objects) (`has_<attribute>()`) are
resolved at runtime from the value itself, so no overload can declare them ahead of time. They are
outside the typed surface by design, and a checker accepts them only where the value keeps the full
builder:

<!-- docs-guard: type-error -->
```python
assert_that(person).has_first_name("Fred")   # type error: a plain class has no dynamic assertions
```

The runtime accepts it either way, and only the checker differs. On a value with its own
overload the choice is between `# type: ignore[attr-defined]` and the typed equivalent, which for a
dict is [`contains_entry()`](../guides/assertions.md#dicts):

```python
assert_that({"first_name": "Fred"}).contains_entry({"first_name": "Fred"})
```

This is the deliberate cost of keeping the original assertpy API working unchanged. The two are not
mutually satisfiable: for a checker to accept `has_first_name` on a dict, `_DictAssertion` would need a
`__getattr__`, and that same declaration would stop it reporting `contins_key` as a typo.

[Custom assertions](../extending/custom-assertions.md) registered with `add_extension()` sit on the same
line, for the same reason. The name is attached at runtime, so it reaches a checker through that one
`__getattr__` and nowhere else:

<!-- docs-guard: type-error -->
```python
assert_that(order).is_paid()  # type error: a plain class has no dynamically attached names
assert_that(5).is_5()         # type error: _NumericAssertion has no attribute is_5
```

Both lines run. An extension needs `# type: ignore[attr-defined]` at each call site, and the return
type a checker infers for it is `Any` rather than whatever the extension actually returns. A checker
accepts the name only where the value keeps the full builder, which is narrower than either half of
the example above: not a `list` or a `dict`, which have overloads of their own, and not a plain class,
which has no capability. What is left is a value with a capability and no overload, such as an
iterable of your own or a mapping that is not a `dict`, and anything typed `Any`.

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

    (A refinement hands back the view `assert_that()` would have given for the refined type, so
    `is_not_none()` on a `str | None` continues as a string. Refining to a class the library does not
    name continues on the core surface instead, since there is no per-type protocol to hand back. Under
    `ty` the numeric and sequence refinements come back gradual rather than as their view, so the chain
    accepts everything from there on instead of narrowing.)

### Refinement narrowing with a TypeIs predicate (advanced)

`is_not_none()` and `is_instance_of()` are two built-in narrowers. `satisfies()` extends narrowing
to **your own** predicates: pass a predicate typed with [`TypeIs`](https://peps.python.org/pep-0742/)
and it narrows the chain to the guarded type. Unlike `is_instance_of()`, which narrows by class only,
a `TypeIs` predicate narrows by any runtime condition - a refinement type:

```python
from typing_extensions import TypeIs  # or `from typing import TypeIs` on Python 3.13+

def is_paid(order: Order) -> TypeIs[PaidOrder]:
    return isinstance(order, PaidOrder) and order.status == "PAID"

paid = assert_that(order).is_not_none().satisfies(is_paid).value
# statically typed as PaidOrder - narrowed by a domain predicate, not just a class
paid.refund()
```

The runtime behavior of `satisfies()` is unchanged (it just runs the predicate). The narrowing is
purely static.

`is_not_none()` in that example is part of the assertion, not a step needed to unlock narrowing. A
concretely typed value refines just as well, which is where a domain predicate is usually applied:

```python
def is_paid_order(payload: object) -> TypeIs[PaidOrder]:
    return isinstance(payload, PaidOrder)

order: dict[str, Any] = response.json()
paid = assert_that(order).satisfies(is_paid_order).value   # statically PaidOrder
```

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

<!-- docs-guard: skip -->
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

Under mypy, one setting decides whether any of this reaches your tests. mypy does not look inside a
function with no annotations at all, and a test written as `def test_orders():` is exactly that.

So the same three mistakes below are reported six times by Pyright and `ty` out of the box, three times
by mypy at its defaults, and six by mypy once it is told to read those bodies:

<!-- docs-guard: skip -->

```python
def test_unannotated():        # mypy default: not checked at all
    assert_that("abc").is_greater_than(3)

def test_annotated() -> None:  # mypy default: checked
    assert_that("abc").is_greater_than(3)
```

Either annotate every test with `-> None`, or set `check_untyped_defs = true`, which `strict = true`
already includes. Pyright and `ty` need neither.

Strict mode then surfaces the most - a wrong method called on a narrowed value, a missing return
annotation, a `.value` read where the type was never narrowed. Turn it on for your checker:

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
