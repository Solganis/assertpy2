# Type Safety

Static typing is the core advantage of `assertpy2` over `assertpy` and most alternatives. `assert_that()`
is overloaded so it returns a *type-specific* set of assertions: your editor offers only the methods that
fit the value, and a type checker rejects misuse before the test ever runs.

## Type-aware autocomplete

`assert_that()` is overloaded into nine typed results - eight type-specific Protocols plus an `object`
fallback - instead of a single `Any`. Your IDE then suggests only the methods relevant to the value you
are testing, not all 100+:

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
assert_that("foo").is_positive()        # type error: is_positive is not a string assertion
assert_that(42).is_instance_of("int")   # type error: expected `type`, got `str`
```

[ty](https://github.com/astral-sh/ty), [mypy `--strict`](https://github.com/python/mypy), and
[Pyright](https://github.com/microsoft/pyright) all report these in the editor and in CI, turning a class
of test bugs into errors you see while typing.

Every public `assert_that` overload is pinned by an `assert_type` check in
[`tests/test_typing.py`](https://github.com/Solganis/assertpy2/blob/main/tests/test_typing.py); CI runs all
three checkers against that file on every push, with **zero suppressions**, so a regression that broadens or
changes a return type fails the build. `ty` additionally type-checks the whole package.

!!! note "Callables and captured values stay typed too"
    `assert_that(func).raises(...).when_called_with(...)` exposes string assertions on the captured
    message, and `returned()` pivots to the type-agnostic core assertions for the call's return value -
    never advertising methods that may not apply. See [Errors & Reporting](errors.md#expected-exceptions).

## Typed narrowing with .value

Assertions don't just check a value - they can hand it back, typed. The `value` property ends a
chain by returning the checked value as-is, and for object- and union-typed values two assertions
refine its static type along the way: `is_not_none()` removes `None`, and `is_instance_of()`
narrows to the checked class. The usual `assert x is not None` / `cast()` dance to satisfy a type
checker disappears:

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

Java's AssertJ approximates this with `asInstanceOf(InstanceOfAssertFactories...)` at runtime;
here the narrowing is purely static - checked by ty, mypy, and Pyright - with zero runtime cost
beyond returning the value.

!!! note "Narrowing assumes strict mode"
    The narrowing reflects the strict `assert_that` default, where a failed `is_not_none()` or
    `is_instance_of()` halts the chain before `.value` is reached, so the value really does match
    the narrowed type. Inside [`soft_assertions()`](testing.md#soft-assertions) or under
    `assert_warn()` a failed assertion does **not** halt, and extraction there is incoherent
    (extract-once-established versus continue-past-failure are opposite intents), so `.value` raises
    `TypeError` rather than hand back a value that could contradict its static type - read `.value`
    in strict mode, or after the soft block. Note too that the narrowed builder exposes the full
    assertion API rather than the type-filtered subset, since an arbitrary narrowed class has no
    per-type protocol.

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
paid.refund()  # statically typed as PaidOrder - narrowed by a domain predicate, not just a class
```

The runtime behavior of `satisfies()` is unchanged (it just runs the predicate); the narrowing is
purely static.

!!! warning "Checker support: not yet in PyCharm"
    This narrowing is solved by **ty, pyright, and mypy** today (so it works in VS Code / Pylance and
    in CI). **PyCharm does not yet solve type variables through `TypeIs`**, so there the result stays
    the un-narrowed type and accessing a narrowed-only member reports a false *Unresolved attribute
    reference*. This is tracked upstream in
    [JetBrains PY-89124](https://youtrack.jetbrains.com/issue/PY-89124); when it is fixed the narrowing
    lights up in PyCharm with no change here. Until then, on PyCharm prefer `is_instance_of()` for
    class narrowing (which PyCharm does narrow), and treat `satisfies()`-based refinement narrowing as
    advanced / checker-dependent. Do **not** disable PyCharm's *Unresolved attribute reference*
    inspection to work around it - it is a core check; scope any workaround to the specific line.

## py.typed and PEP 561

`assertpy2` ships a `py.typed` marker and is [PEP 561](https://peps.python.org/pep-0561/) compliant, so the
types are picked up automatically by any project that depends on it - no stub package, no extra config.

## Editor support

The overloads are plain typing with no runtime cost, so type-aware autocomplete works in PyCharm, VS Code
(Pylance), and any LSP-compatible editor out of the box.
