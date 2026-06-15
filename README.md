<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/logo.svg">
    <img src="docs/logo.svg" alt="assertpy2" width="280">
  </picture>
</p>

<p align="center">
  <b>Fluent assertion library for Python with composable matchers, structural matching, and full type safety.</b><br>
  A modern, batteries-included fork of <a href="https://github.com/assertpy/assertpy">assertpy</a>.
</p>

<p align="center">
  <a href="https://github.com/Solganis/assertpy2/actions/workflows/ci.yml"><img src="https://github.com/Solganis/assertpy2/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/assertpy2/"><img src="https://img.shields.io/pypi/v/assertpy2" alt="PyPI version"></a>
  <a href="https://pepy.tech/projects/assertpy2"><img src="https://static.pepy.tech/badge/assertpy2/month" alt="Downloads"></a>
  <a href="https://pypi.org/project/assertpy2/"><img src="https://img.shields.io/pypi/pyversions/assertpy2" alt="Python"></a>
  <a href="https://codecov.io/gh/Solganis/assertpy2"><img src="https://codecov.io/gh/Solganis/assertpy2/graph/badge.svg" alt="Coverage"></a>
  <br>
  <a href="https://github.com/Solganis/assertpy2/blob/main/docs/api.md"><img src="https://img.shields.io/badge/Docs-Read%20The%20Docs-black" alt="Documentation"></a>
  <a href="https://docs.astral.sh/ruff/"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"></a>
  <a href="https://github.com/astral-sh/ty"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json" alt="ty"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/Solganis/assertpy2"><img src="https://api.scorecard.dev/projects/github.com/Solganis/assertpy2/badge" alt="OpenSSF Scorecard"></a>
  <a href="https://www.bestpractices.dev/projects/12990"><img src="https://www.bestpractices.dev/projects/12990/badge" alt="OpenSSF Best Practices"></a>
</p>

---

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

Structured errors with rich diffs:

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
--- Structured Diff ---
diff (dict):
  b:
    - 2
    + 99
```

## Type-aware autocomplete

`assert_that()` uses `@overload` to return type-specific Protocols.
Your IDE shows only methods relevant to the value you're testing, not all 100+:

- `assert_that("hello").` &rarr; string methods: `starts_with`, `matches`, `is_alpha`, ...
- `assert_that(42).` &rarr; numeric methods: `is_positive`, `is_between`, `is_close_to`, ...
- `assert_that(Path("/tmp")).` &rarr; path methods: `exists`, `is_file`, `is_readable`, ...
- `assert_that(my_dict).` &rarr; dict methods: `contains_key`, `contains_entry`, `has_json_path`, ...
- `assert_that(b"\x89PNG").` &rarr; bytes methods: `starts_with_bytes`, `is_valid_utf8`, `decoded_as`, ...

9 type-specific Protocols instead of one `Any`. Works in PyCharm, VS Code, and any LSP-compatible editor.

---

## Comparison

<div align="center">

|  | pytest assert | PyHamcrest | assertpy | **assertpy2** |
|---|:---:|:---:|:---:|:---:|
| **Type safety** | Partial (mypy plugin) | No | No | **py.typed, @overload, Self** |
| **IDE autocomplete** | Generic | Generic | Generic | **[Filtered by type](#type-aware-autocomplete)** |
| **Fluent chaining** | No | No | Yes | **Yes** |
| **Composable matchers** | No | Yes (functions) | No | **Yes (`&` `\|` `~` operators)** |
| **Structural matching** | No | Flat (has_entries) | No | **Recursive with matchers** |
| **Async assertions** | No | No | No | **eventually() with polling** |
| **Soft assertions** | No | No | Yes (not thread-safe) | **Yes (thread-safe, async-safe)** |
| **Structured errors** | Rewrite only | Mismatch string | String only | **.actual .expected .diff** |
| **Maintained** | Built-in | Minimal | 2020 | **Active** |

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

---

## Features

**Fluent API**

- [**Composable matchers**](docs/api.md#composable-matchers): `match.greater_than(5)`, `match.is_uuid()`, combine with `&`, `|`, `~`. Also work with plain `assert ==`.
- [**Structural matching**](docs/api.md#structural-matching): `matches_structure()` for declarative dict/API response validation.
- [**Universal negation**](docs/api.md#universal-negation): `.not_` inverts any assertion without dedicated `is_not_*` methods.
- [**Collection pipeline**](docs/api.md#collection-pipeline): `filtered_on()`, `mapped()`, `flat_mapped()`, `first()`, `last()`, `element()`, `single()`.
- [**Fluent chaining**](docs/api.md#chaining): write assertions as readable one-liners that chain naturally.

**Built-in types**

- [Strings](docs/api.md#strings), [numbers](docs/api.md#numbers), [lists](docs/api.md#lists), [tuples](docs/api.md#tuples), [sets](docs/api.md#sets), [dicts](docs/api.md#dicts), [dates](docs/api.md#dates), [booleans](docs/api.md#booleans), [objects](docs/api.md#objects), [bytes](docs/api.md#bytes--bytearray-assertions), [files](docs/api.md#files), [exceptions](docs/api.md#failure).
- [**Bytes assertions**](docs/api.md#bytes--bytearray-assertions): `is_valid_utf8()`, `starts_with_bytes()`, `is_hex_equal_to()`, `decoded_as()` for `bytes`/`bytearray`.
- [**JSON assertions**](docs/api.md#json-path--schema-validation): JSONPath navigation and JSON Schema validation. `pip install assertpy2[json]`.
- [**Dynamic assertions**](docs/api.md#objects): `has_<name>()` for any attribute, property, or zero-argument method.
- [**Dict comparison**](docs/api.md#dicts): `is_equal_to()` with `ignore` and `include` for selective key matching.
- [**Extracting**](docs/api.md#objects): flatten collections on attributes with `filter` and `sort` support.

**Testing**

- [**Soft assertions**](docs/api.md#soft-assertions): thread-safe, async-safe via `contextvars`. Group errors with `sa.group()`, or use `assert_all()`.
- [**Async assertions**](docs/api.md#async-assertions): `eventually()` with polling/retry for eventual consistency.
- [**Structured errors**](docs/api.md#structured-errors): `AssertionFailure` with `.actual`, `.expected`, `.diff` attributes.
- [**Rich pytest diffs**](docs/api.md#rich-pytest-diffs): recursive structural diffs for lists, sets, strings, dicts, dataclasses, namedtuples.
- [**Snapshot testing**](docs/api.md#snapshot-testing): store and compare data structures in JSON format.

**Type safety**

- [**Type-aware autocomplete**](#type-aware-autocomplete): 9 Protocols, IDE shows only relevant methods per type.
- **py.typed**: `Self` return types, PEP 561 compliant ([PEP 561](https://peps.python.org/pep-0561/)).

**Extensibility**

- [**Custom matchers**](docs/api.md#custom-matchers---registering-domain-matchers): `register_matcher()` for domain-specific matchers, composable with `&`, `|`, `~`.
- [**Regex group extraction**](docs/api.md#regex-group-extraction): `extracting_group()` and `matches_with_groups()` for regex captures.
- [**Extensions**](docs/api.md#extension-system---adding-custom-assertions): `add_extension()` for custom assertion methods.

**Integrations**

- [**Allure**](docs/api.md#allure-integration): auto-attach structured diff and actual/expected data to reports. `pip install assertpy2[allure]`.
- [**Behave**](docs/api.md#behave-step-matchers): ready-made parameter types for step definitions. `pip install assertpy2[behave]`.

---

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

Matchers also support `==` directly, so you can use them with plain `assert` or mix into dicts and lists:

```py
from assertpy2 import match

assert 42 == match.is_positive()
assert {"id": 5, "name": "Alice"} == {"id": match.is_positive(), "name": match.is_non_empty_string()}
```

Available matchers: `equal_to`, `greater_than`, `greater_than_or_equal_to`, `less_than`, `less_than_or_equal_to`, `between`, `close_to`, `is_none`, `is_not_none`, `is_instance_of`, `has_length`, `is_empty`, `is_not_empty`, `is_positive`, `is_negative`, `is_zero`, `is_even`, `is_odd`, `is_divisible_by`, `is_callable`, `is_in`, `has_property`, `contains_string`, `matches_regex`, `is_uuid`, `is_non_empty_string`, `ignore`, `each_item`, `structure`.


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

---

## Fluent API

### Universal negation

Invert any assertion with `.not_`:

```py
assert_that(5).not_.is_none()
assert_that("abc123").not_.is_alpha()
assert_that([3, 1, 2]).not_.is_sorted()
assert_that(value).described_as("check").not_.is_none().is_positive()
```

Works with soft assertions and warn mode.

### Collection pipeline

Transform collections before asserting:

```py
orders = [Order("DONE", 100), Order("FAILED", 50), Order("DONE", 200)]

assert_that(orders).filtered_on(lambda o: o.status == "FAILED").is_length(1)
assert_that(orders).mapped(lambda o: o.total).contains(100, 200)
assert_that(orders).first().has_status("DONE")
assert_that(orders).element(1).has_status("FAILED")
assert_that([42]).single().is_equal_to(42)

# chaining pipeline steps
assert_that(items).filtered_on(match.is_positive()).mapped(str).contains("1")
```

Available methods: `filtered_on()`, `mapped()`, `flat_mapped()`, `first()`, `last()`, `element()`, `single()`.

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

### Dynamic assertions

```py
fred = {"first_name": "Fred", "last_name": "Smith", "shoe_size": 12}

assert_that(fred).has_first_name("Fred")
assert_that(fred).has_last_name("Smith")
assert_that(fred).has_shoe_size(12)
```

### Expected exceptions

```py
assert_that(some_func).raises(RuntimeError).when_called_with("bad_arg")\
    .is_length(8).starts_with("some").is_equal_to("some err")
```

---

## Built-in types

### Bytes assertions

Assert on `bytes` and `bytearray` values:

```py
data = b"\x89PNG\r\n\x1a\n"

assert_that(data).starts_with_bytes(b"\x89PNG")
assert_that(data).has_byte_at(0, 0x89)
assert_that(data).is_hex_equal_to("89504e470d0a1a0a")
assert_that(b"hello").is_valid_utf8()
assert_that(b"hello").decoded_as("utf-8").starts_with("hel")
```

Available methods: `is_valid_utf8()`, `is_valid_encoding()`, `starts_with_bytes()`, `contains_bytes()`, `has_byte_at()`, `is_hex_equal_to()`, `decoded_as()`.

### JSON path and schema validation

Requires `pip install assertpy2[json]`.

```py
data = {"users": [{"name": "Alice"}, {"name": "Bob"}], "meta": {"total": 2}}

assert_that(data).at_json_path("$.users[0].name").is_equal_to("Alice")
assert_that(data).has_json_path("$.meta.total")
assert_that(data).does_not_have_json_path("$.error")
assert_that(data).matches_json_schema({"type": "object", "required": ["users"]})
```

### Snapshot testing

```py
assert_that({"a": 1, "b": 2, "c": 3}).snapshot()
```

---

## Testing

### Soft assertions

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

### Grouped soft assertions

```py
with soft_assertions() as sa:
    with sa.group("Headers"):
        assert_that(headers["Content-Type"]).is_equal_to("application/json")
    with sa.group("Body"):
        assert_that(body["status"]).is_equal_to("ok")
        assert_that(body["items"]).is_not_empty()

# or inline with assert_all
assert_all(
    lambda: assert_that(x).is_positive(),
    lambda: assert_that(y).is_not_none(),
)
```

### Async assertions

Poll a callable until the assertion passes or timeout is reached:

```py
from assertpy2 import assert_that

async def test_eventual_consistency():
    await assert_that(get_status).eventually().within(5).every(0.5).is_equal_to("ready")

    # works with async callables
    await assert_that(async_get_count).eventually().within(10).is_greater_than(100)
```

Any assertion method is available after `eventually()`. Only `AssertionError` is retried, other exceptions propagate immediately.

### Structured errors

When assertions fail, `AssertionFailure` carries structured data alongside the human-readable message:

```py
try:
    assert_that(1).is_equal_to(2)
except AssertionError as e:
    e.actual    # 1
    e.expected  # 2
```

For comparisons, a `DiffResult` with structural diff entries is available:

```py
try:
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 99})
except AssertionError as e:
    e.diff  # DiffResult(kind='dict', entries=[DiffEntry(path='b', actual=2, expected=99)])
```

`AssertionFailure` is a subclass of `AssertionError`, so all existing `except AssertionError` handlers work unchanged.

### Rich pytest diffs

The pytest plugin (auto-registered, no configuration needed) renders structural diffs with recursive descent:

```
FAILED test_example.py::test_api
--- AssertionFailure ---
  actual:   [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
  expected: [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Robert'}]
--- Structured Diff ---
diff (sequence):
  [1].name:
    - 'Bob'
    + 'Robert'
```

Supported types: list/tuple, set/frozenset, str, dict, dataclass, namedtuple. Nested structures are diffed recursively. Colored output when `--color=yes`.

Configure via `pyproject.toml`:

```toml
[tool.pytest.ini_options]
assertpy2_diff = "off"              # disable diff sections
assertpy2_diff_max_entries = "100"  # max entries shown (default 50, 0 = unlimited)
```

---

## Extensibility

### Custom matchers

Register domain-specific matchers on the `match` namespace with `register_matcher()`:

```py
from assertpy2 import assert_that, match, register_matcher

@register_matcher("is_valid_email")
def is_valid_email():
    return match.matches_regex(r"^[\w.-]+@[\w.-]+\.\w+$")

# parametrised matchers
@register_matcher("has_status")
def has_status(expected: str):
    return match.has_property("status", match.equal_to(expected))

# use everywhere matchers are accepted
assert_that("alice@example.com").satisfies(match.is_valid_email())
assert_that(users).extracting("email").each(match.is_valid_email())
assert_that(data).matches_structure({"email": match.is_valid_email()})

# composition works automatically
assert_that(email).satisfies(match.is_valid_email() & match.contains_string("@company.com"))
```

Remove with `unregister_matcher("is_valid_email")`.

### Regex group extraction

Extract regex groups and continue the fluent chain:

```py
log = "2024-01-15 ERROR status=500 path=/api/users"

# extract a positional group
assert_that(log).extracting_group(r"status=(\d+)", 1).is_equal_to("500")

# extract a named group
assert_that(log).extracting_group(r"(?P<level>\w+) status", "level").is_equal_to("ERROR")

# get all groups as a tuple or dict (named groups)
assert_that("key=value").matches_with_groups(r"(?P<k>\w+)=(?P<v>\w+)") \
    .contains_entry({"k": "key"}).contains_entry({"v": "value"})
```

### Extensions

```py
from assertpy2 import add_extension

def is_5(self):
    if self.val != 5:
        return self.error(f'{self.val} is NOT 5!')
    return self

add_extension(is_5)

assert_that(5).is_5()
```

See the [full API reference](docs/api.md) for all assertion methods, examples, and advanced features.

---

## Integrations

### Allure

When `allure-pytest` is installed, the pytest plugin auto-attaches structured failure data to Allure reports as JSON attachments.

```bash
pip install assertpy2[allure]
```

Three modes controlled via `pytest.ini` (or `pyproject.toml`):

| Mode | What is attached |
|---|---|
| `diff` (default) | Structured Diff JSON (path-level breakdown) |
| `full` | Structured Diff + actual/expected JSON |
| `off` | Nothing |

```toml
# pyproject.toml
[tool.pytest.ini_options]
assertpy2_allure = "full"
```

### Behave

Ready-made parameter types for Behave step definitions:

```bash
pip install assertpy2[behave]
```

```py
# in environment.py or steps/conftest.py
from assertpy2.behave_matchers import register_assertpy_types
register_assertpy_types()
```

Then use in step definitions:

```py
@given('a user aged {age:PositiveInt}')
def step_impl(context, age):
    context.age = age  # already validated as int > 0
```

Available types: `PositiveInt`, `NonNegativeInt`, `PositiveFloat`, `NonEmptyString`, `BoolLike`.

---

## Migration from assertpy

assertpy2 is a drop-in replacement for Python 3.10+. Change the import, everything else works:

```py
# before
from assertpy import assert_that, soft_assertions

# after
from assertpy2 import assert_that, soft_assertions
```

See the [comparison table](#comparison) above for feature differences with other libraries.


---

<p align="center">
  <a href="https://github.com/Solganis/assertpy2/blob/main/LICENSE">BSD 3-Clause License</a>
</p>
