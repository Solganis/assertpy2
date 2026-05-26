<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/logo.svg">
    <img src="docs/logo.svg" alt="assertpy2" width="280">
  </picture>
</p>

<p align="center">
  <b>Fluent assertion library for Python with composable matchers, structural matching, and full type safety.</b><br>
  Maintained fork of <a href="https://github.com/assertpy/assertpy">assertpy</a>.
</p>

<p align="center">
  <a href="https://github.com/Solganis/assertpy2/actions/workflows/ci.yml"><img src="https://github.com/Solganis/assertpy2/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/assertpy2/"><img src="https://img.shields.io/pypi/v/assertpy2" alt="PyPI version"></a>
  <a href="https://pepy.tech/projects/assertpy2"><img src="https://static.pepy.tech/badge/assertpy2/month" alt="Downloads"></a>
  <a href="https://pypi.org/project/assertpy2/"><img src="https://img.shields.io/pypi/pyversions/assertpy2" alt="Python"></a>
  <a href="https://codecov.io/gh/Solganis/assertpy2"><img src="https://codecov.io/gh/Solganis/assertpy2/graph/badge.svg" alt="Coverage"></a>
  <a href="https://github.com/Solganis/assertpy2/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Solganis/assertpy2" alt="License"></a>
  <a href="https://docs.astral.sh/ruff/"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
</p>


## Quick start

```bash
pip install assertpy2
```

```py
from assertpy2 import assert_that

def test_user():
    user = {"name": "Alice", "age": 30, "roles": ["viewer", "editor"]}

    assert_that(user).contains_key("name", "age")
    assert_that(user["age"]).is_between(18, 120)
    assert_that(user["roles"]).contains("viewer").does_not_contain("admin")
    assert_that(user).has_name("Alice")
```

Composable matchers and structural matching:

```py
from assertpy2 import assert_that, match

# matchers with & | ~ operators
assert_that([3, 7, 12]).contains(match.greater_than(10))
assert_that(42).satisfies(match.greater_than(0) & match.less_than(100))

# validate dict structure declaratively
assert_that(api_response).matches_structure({
    "id": match.is_uuid(),
    "name": match.equal_to("Alice"),
    "status": match.is_non_empty_string(),
})
```

Structured errors with rich data:

```py
try:
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 99})
except AssertionError as e:
    e.actual    # {"a": 1, "b": 2}
    e.expected  # {"a": 1, "b": 99}
    e.diff      # DiffResult(kind='dict', entries=[DiffEntry(path='b', actual=2, expected=99)])
```

The pytest plugin auto-renders this as rich diff sections in failure reports:

```
FAILED test_example.py::test_comparison
--- AssertionFailure ---
  actual:   {'a': 1, 'b': 2}
  expected: {'a': 1, 'b': 99}
```


## Comparison

<div align="center">

|  | pytest assert | PyHamcrest | assertpy | **assertpy2** |
|---|:---:|:---:|:---:|:---:|
| **Type safety** | Partial (mypy plugin) | No | No | **py.typed, @overload, Self** |
| **IDE autocomplete** | Generic | Generic | Generic | **Type-specific per value** |
| **Fluent chaining** | No | No | Yes | **Yes** |
| **Composable matchers** | No | Yes (functions) | No | **Yes (`&` `\|` `~` operators)** |
| **Structural matching** | No | Flat (has_entries) | No | **Recursive with matchers** |
| **Async assertions** | No | No | No | **eventually() with polling** |
| **Soft assertions** | No | No | Yes (not thread-safe) | **Yes (thread-safe, async-safe)** |
| **Structured errors** | Rewrite only | Mismatch string | String only | **.actual .expected .diff** |
| **Maintained** | N/A | Minimal | Dead (2020) | **Active (2026)** |

</div>


## Why fluent assertions?

```py
# bare assert - passes, but failure message is useless
assert user["age"] >= 18
# AssertionError

# assertpy2 - same check, clear failure message
assert_that(user["age"]).is_greater_than_or_equal_to(18)
# AssertionError: Expected <16> to be greater than or equal to <18>, but was not.

# bare assert - three separate statements
assert isinstance(items, list)
assert len(items) == 3
assert "admin" in items

# assertpy2 - one fluent chain
assert_that(items).is_type_of(list).is_length(3).contains("admin")
```


## Features

- **Composable matchers**: `match.greater_than(5)`, `match.is_uuid()`, combine with `&`, `|`, `~` operators.
- **Structural matching**: `matches_structure()` for declarative dict/API response validation.
- **Async assertions**: `eventually()` with polling/retry for async and eventual consistency testing.
- **Structured errors**: `AssertionFailure` with `.actual`, `.expected`, `.diff` attributes, pytest plugin with rich diff output.
- **Typed overloads**: `assert_that()` returns type-specific Protocols, IDE shows only relevant methods per type.
- **Type safety**: `Self` return types, `py.typed` ([PEP 561](https://peps.python.org/pep-0561/)).
- **Soft assertions**: thread-safe and async-safe via `contextvars`, collect all failures with `soft_assertions()`.
- **Fluent chaining**: write assertions as readable one-liners that chain naturally.
- **Dynamic assertions**: `has_<name>()` for any attribute, property, or zero-argument method on objects and dicts.
- **Dict comparison**: `is_equal_to()` with `ignore` and `include` for selective key matching.
- **Extracting**: flatten collections on attributes with `filter` and `sort` support.
- **File assertions**: `exists()`, `is_file()`, `is_readable()`, `is_writable()`, `is_executable()` with `pathlib.Path` support.
- **Snapshot testing**: store and compare data structures in JSON format, inspired by Jest.
- **Extensions**: add custom assertions via `add_extension()`.
- Strings, numbers, lists, tuples, sets, dicts, dates, booleans, objects, exceptions.


## Composable matchers

Matchers are objects that describe conditions. Combine them with `&` (and), `|` (or), `~` (not):

```py
from assertpy2 import assert_that, match

# check a value against a composed condition
assert_that(42).satisfies(match.greater_than(0) & match.less_than(100))

# matchers inside contains - find element by condition
assert_that([3, 7, 12]).contains(match.greater_than(10))

# check every element in a collection
assert_that([18, 25, 30]).each(match.between(18, 120))

# invert with ~
assert_that("hello").satisfies(~match.equal_to("world"))

# combine freely
assert_that(150).satisfies(match.is_negative() | match.greater_than(100))
```

Available matchers: `equal_to`, `greater_than`, `greater_than_or_equal_to`, `less_than`, `less_than_or_equal_to`, `between`, `close_to`, `is_none`, `is_not_none`, `is_instance_of`, `has_length`, `is_empty`, `is_not_empty`, `is_positive`, `is_negative`, `contains_string`, `matches_regex`, `is_uuid`, `is_non_empty_string`, `ignore`, `each_item`, `structure`.


## Structural matching

Validate dict structure declaratively, even when values are dynamic (UUIDs, timestamps):

```py
from assertpy2 import assert_that, match

assert_that(api_response).matches_structure({
    "id": match.is_uuid(),
    "name": match.equal_to("Alice"),
    "created_at": match.is_non_empty_string(),
    "metadata": match.structure({
        "version": match.greater_than(0),
        "tags": match.each_item(match.is_instance_of(str)),
    }),
    "debug_info": match.ignore(),
})
```


## Async assertions

Poll a callable until the assertion passes or timeout is reached:

```py
from assertpy2 import assert_that

async def test_eventual_consistency():
    await assert_that(get_status).eventually().within(5).every(0.5).is_equal_to("ready")

    # works with async callables
    await assert_that(async_get_count).eventually().within(10).is_greater_than(100)
```

Any assertion method is available after `eventually()`. Only `AssertionError` is retried, other exceptions propagate immediately.


## Soft assertions

Collect all failures instead of stopping at the first one:

```py
from assertpy2 import assert_that, soft_assertions

def test_user_profile():
    with soft_assertions():
        assert_that(user.name).is_equal_to("Alice")
        assert_that(user.age).is_greater_than(0)
        assert_that(user.email).contains("@")
```

All failures are reported at the end of the block:

```
AssertionError: soft assertion failures:
1. Expected <Bob> to be equal to <Alice>, but was not.
2. Expected <-1> to be greater than <0>, but was not.
3. Expected <invalid> to contain <@>, but did not.
```

Use `soft_fail("message")` inside the block for non-halting explicit failures (unlike `fail()`, which stops immediately).

Soft assertions are thread-safe and async-safe: each thread and each `asyncio` task gets independent state via `contextvars`.


## Structured errors

When assertions fail, `AssertionFailure` carries structured data alongside the human-readable message:

```py
try:
    assert_that(1).is_equal_to(2)
except AssertionError as e:
    e.actual    # 1
    e.expected  # 2
```

For dict comparisons, a `DiffResult` with per-key diff entries is available:

```py
try:
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 99})
except AssertionError as e:
    e.diff  # DiffResult(kind='dict', entries=[DiffEntry(path='b', actual=2, expected=99)])
```

`AssertionFailure` is a subclass of `AssertionError`, so all existing `except AssertionError` handlers work unchanged.

The pytest plugin (auto-registered, no configuration needed) renders structured data as extra sections in failure reports:

```
FAILED test_example.py::test_comparison
--- AssertionFailure ---
  actual:   {'a': 1, 'b': 2}
  expected: {'a': 1, 'b': 99}
--- Structured Diff ---
DiffResult(kind='dict', entries=[DiffEntry(path='b', actual=2, expected=99)])
```


## More features

### Dict comparison with ignore/include

```py
assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, ignore=["b", "c"])
assert_that({"a": 1, "b": {"c": 2, "d": 3}}).is_equal_to({"b": {"d": 3}}, include=("b", "d"))
```

### Extracting with filter and sort

```py
users = [
    {"user": "Fred", "age": 36, "active": True},
    {"user": "Bob", "age": 40, "active": False},
    {"user": "Johnny", "age": 13, "active": True},
]

assert_that(users).extracting("user", filter="active").is_equal_to(["Fred", "Johnny"])
assert_that(users).extracting("user", sort="age").is_equal_to(["Johnny", "Fred", "Bob"])
```

### Expected exceptions

```py
assert_that(some_func).raises(RuntimeError).when_called_with("bad_arg")\
    .is_length(8).starts_with("some").is_equal_to("some err")
```

### Dynamic assertions

```py
fred = {"first_name": "Fred", "last_name": "Smith", "shoe_size": 12}

assert_that(fred).has_first_name("Fred")
assert_that(fred).has_last_name("Smith")
assert_that(fred).has_shoe_size(12)
```

### Snapshot testing

```py
assert_that({"a": 1, "b": 2, "c": 3}).snapshot()
```

### Extensions

```py
from assertpy2 import add_extension

def is_even(self):
    if self.val % 2 != 0:
        return self.error(f'{self.val} is not even!')
    return self

add_extension(is_even)

assert_that(4).is_even()
```

See the [full API reference](docs/api.md) for all assertion methods, examples, and advanced features.


## Migration from assertpy

assertpy2 is a drop-in replacement for Python 3.10+. Change the import, everything else works:

```py
# before
from assertpy import assert_that, soft_assertions

# after
from assertpy2 import assert_that, soft_assertions
```

<div align="center">

|  | assertpy | assertpy2 |
|---|---|---|
| Python | 2.7+ | 3.10-3.15 |
| Security | [CVE in snapshots](https://github.com/assertpy/assertpy/issues/156) | Fixed |
| Open bugs | 15+ unresolved | All resolved |
| Last release | 2020 | Active (2026) |

</div>

See the [full comparison table](#comparison) at the top for feature differences with other libraries.


## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.


## License

All files are licensed under the BSD 3-Clause License as follows:

> Copyright (c) 2015-2019, Activision Publishing, Inc.
> All rights reserved.
>
> Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
>
> 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
>
> 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
>
> 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
