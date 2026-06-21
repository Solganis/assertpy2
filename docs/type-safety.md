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

[ty](https://github.com/astral-sh/ty), Pyright, and Mypy all report these in the editor and in CI, turning
a class of test bugs into errors you see while typing.

!!! note "Callables and captured values stay typed too"
    `assert_that(func).raises(...).when_called_with(...)` exposes string assertions on the captured
    message, and `returned()` pivots to the type-agnostic core assertions for the call's return value -
    never advertising methods that may not apply. See [Errors & Reporting](errors.md#expected-exceptions).

## py.typed and PEP 561

`assertpy2` ships a `py.typed` marker and is [PEP 561](https://peps.python.org/pep-0561/) compliant, so the
types are picked up automatically by any project that depends on it - no stub package, no extra config.

## Editor support

The overloads are plain typing with no runtime cost, so type-aware autocomplete works in PyCharm, VS Code
(Pylance), and any LSP-compatible editor out of the box.
