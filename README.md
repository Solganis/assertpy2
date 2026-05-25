<p align="center">
  <img src="docs/logo.svg" alt="assertpy2" width="280">
</p>

<p align="center">
  <b>Fluent assertion library for Python with full type safety and soft assertions.</b><br>
  Maintained fork of <a href="https://github.com/assertpy/assertpy">assertpy</a>.
</p>

<p align="center">
  <a href="https://github.com/Solganis/assertpy2/actions/workflows/ci.yml"><img src="https://github.com/Solganis/assertpy2/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/assertpy2/"><img src="https://img.shields.io/pypi/v/assertpy2" alt="PyPI version"></a>
  <a href="https://pepy.tech/projects/assertpy2"><img src="https://static.pepy.tech/badge/assertpy2/month" alt="Downloads"></a>
  <a href="https://pypi.org/project/assertpy2/"><img src="https://img.shields.io/pypi/pyversions/assertpy2" alt="Python"></a>
  <a href="https://github.com/Solganis/assertpy2"><img src="https://img.shields.io/badge/coverage-100%25-brightgreen" alt="Coverage"></a>
  <a href="https://github.com/Solganis/assertpy2/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Solganis/assertpy2" alt="License"></a>
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

When an assertion fails, the error message tells you exactly what went wrong:

```py
assert_that(user["age"]).is_between(50, 120)
# AssertionError: Expected <30> to be between <50> and <120>, but was not.

assert_that(user["roles"]).contains("admin")
# AssertionError: Expected <['viewer', 'editor']> to contain <admin>, but did not.
```


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

- **Type safety**: `Self` return types, `py.typed` ([PEP 561](https://peps.python.org/pep-0561/)).
- **IDE support**: full autocomplete and chaining inference out of the box.
- **Soft assertions**: collect all failures with `soft_assertions()`, plus `soft_fail()` for non-halting explicit failures.
- **Fluent chaining**: write assertions as readable one-liners that chain naturally.
- **Dynamic assertions**: `has_<name>()` for any attribute, property, or zero-argument method on objects and dicts.
- **Dict comparison**: `is_equal_to()` with `ignore` and `include` for selective key matching.
- **Extracting**: flatten collections on attributes with `filter` and `sort` support.
- **File assertions**: `exists()`, `is_file()`, `is_readable()`, `is_writable()`, `is_executable()` with `pathlib.Path` support.
- **Snapshot testing**: store and compare data structures in JSON format, inspired by Jest.
- **Extensions**: add custom assertions via `add_extension()`.
- Strings, numbers, lists, tuples, sets, dicts, dates, booleans, objects, exceptions.


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


## API highlights

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

### Snapshot testing

```py
assert_that({"a": 1, "b": 2, "c": 3}).snapshot()
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
| Maintained | Last release 2020 | Active |
| Python | 2.7+ | 3.10-3.14 |
| Type safety | No annotations | `Self` return types, `py.typed` (PEP 561) |
| IDE support | No type info | Full autocomplete and chaining inference |
| Soft assertions | Basic | Stable, with `soft_fail()` support |
| Security | [CVE in snapshots](https://github.com/assertpy/assertpy/issues/156) | Fixed |
| Open bugs | 15+ unresolved | All resolved |

</div>


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
