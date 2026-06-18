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
pip install assertpy2  # drop-in replacement for assertpy, just change the import
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
- [**Dict comparison**](docs/api.md#dicts): `is_equal_to()` with `ignore` and `include` for selective key/field matching (dicts, dataclasses, namedtuples, Pydantic models, attrs, plain objects).
- [**Extracting**](docs/api.md#objects): flatten collections on attributes with `filter` and `sort` support.

**Testing**

- [**Soft assertions**](docs/api.md#soft-assertions): thread-safe, async-safe via `contextvars`. Group errors with `sa.group()`, or use `assert_all()`.
- [**Async assertions**](docs/api.md#async-assertions): `eventually()` with polling/retry for eventual consistency.
- [**Structured errors**](docs/api.md#structured-errors): `AssertionFailure` with `.actual`, `.expected`, `.diff` attributes.
- [**Rich pytest diffs**](docs/api.md#rich-pytest-diffs): recursive structural diffs for lists, sets, strings, dicts, dataclasses, namedtuples, Pydantic models. Circular reference protection.
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

<p align="center">
  <a href="https://github.com/Solganis/assertpy2/blob/main/LICENSE">BSD 3-Clause License</a>
</p>
