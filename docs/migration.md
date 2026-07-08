# Migration from assertpy

`assertpy2` is a drop-in replacement for the original
[assertpy](https://github.com/assertpy/assertpy), which has been inactive since 2020 (last release
`1.1`). It keeps the same `assert_that(...)` API and adds static typing, composable matchers,
structural matching, async assertions, and structured failures. For most projects the migration is a
one-line change with no behavioral surprises.

!!! success "TL;DR"
    On Python 3.10+, replace `from assertpy import ...` with `from assertpy2 import ...` and run your
    tests. The assertions you already use carry over unchanged.

## Before you start

- **Python 3.10+ is required.** The original assertpy ran on Python 2.7 and 3.x; assertpy2 targets
  3.10 through 3.15. If you are on an older interpreter, upgrade Python first - this is the only hard
  requirement of the migration.
- **No runtime dependencies on Python 3.11+.** On 3.10 a single tiny backport (`typing_extensions`) is
  pulled in automatically. The extras (`[json]`, `[data]`, `[allure]`, `[behave]`) stay opt-in.

## Switch the import

=== "Before"

    ```python
    from assertpy import assert_that, soft_assertions, fail
    ```

=== "After"

    ```python
    from assertpy2 import assert_that, soft_assertions, fail
    ```

If you import the module instead of its names, alias it so existing call sites keep working:

```python
import assertpy2 as assertpy  # `assertpy.assert_that(...)` call sites stay unchanged
```

A project-wide find-and-replace of `from assertpy import` to `from assertpy2 import` is usually the
entire migration.

??? tip "Automate it across a project"
    ```bash
    grep -rl --include="*.py" "assertpy" . \
      | xargs sed -i 's/from assertpy import/from assertpy2 import/g'
    ```
    Review the diff afterwards: the replacement only rewrites `from assertpy import` lines. For
    `import assertpy` usages, prefer the alias shown above.

## What stays the same

assertpy2 is a superset of the original, so the assertions you already use are present and produce the
same results:

- the `assert_that()` entry point and fluent (`return self`) chaining;
- strings, numbers, lists, tuples, dicts, sets, booleans, `None`, dates, files, and objects;
- dynamic `has_<name>()` assertions and `extracting()` with `filter` and `sort`;
- soft assertions, expected exceptions (`raises().when_called_with()`), `fail()`, `assert_warn()`,
  snapshot testing, and `add_extension()`;
- the existing failure messages.

!!! note "Backward-compatible failures"
    Failing assertions now raise `AssertionFailure`, a **subclass of `AssertionError`**. Existing
    `except AssertionError` handlers keep working unchanged; the subclass simply carries extra
    structured data.

## What improves automatically

You get these the moment you switch, without touching any test code:

- **Thread-safe and async-safe soft assertions.** State is isolated per thread and per `asyncio.Task`
  via `contextvars`, so soft assertions are safe under `pytest-xdist` and `asyncio`. The original's soft
  assertions were not thread-safe.
- **Structured failures and rich diffs.** Failures carry `.actual` / `.expected` / `.diff`, and the
  auto-registered pytest plugin renders recursive diffs for lists, dicts, dataclasses, namedtuples, and
  Pydantic models. Set `assertpy2_diff = "off"` if you prefer the plain message.
- **Static typing.** With `py.typed` and `@overload` protocols your editor filters autocomplete by the
  value's type, and a type checker flags misuse before the tests run - see [Type Safety](type-safety.md).

## What you can now adopt

New capabilities the original never had, ready whenever you want them:

- [Composable matchers](matchers.md) usable in `.satisfies()`, `.each()`, and plain `==`.
- [Structural matching](matchers.md#structural-matching) for API-response shapes.
- [Typed narrowing](type-safety.md#typed-narrowing-with-value) (`.value`) and [contract testing](type-safety.md#contract-narrowing-with-assert_conforms) (`assert_conforms()`) for typed API-response tests.
- [Exception cause chains and groups](errors.md#expected-exceptions) (`caused_by()`, `has_root_cause()`, `contains_error()`).
- The [collection pipeline](fluent.md#collection-pipeline) and [universal negation](fluent.md#universal-negation).
- [Async and blocking polling](testing.md#async-assertions) with `eventually()` / `eventually_sync()`.
- [JSON Path / Schema](data.md), [regex group extraction](data.md#regex-group-extraction), and
  [bytes assertions](assertions.md#bytes--bytearray).

See the [comparison](comparison.md) for the full feature delta.

## Steps

1. Ensure the project runs on Python 3.10+.
2. Swap the dependency: uninstall `assertpy`, install `assertpy2`, and update `requirements` or
   `pyproject`.
3. Find-and-replace the imports as shown above.
4. Run your test suite - it should pass unchanged.
