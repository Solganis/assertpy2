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
  <a href="https://solganis.github.io/assertpy2/"><img src="https://img.shields.io/badge/Docs-online-black" alt="Documentation"></a>
  <a href="https://docs.astral.sh/ruff/"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"></a>
  <a href="https://github.com/astral-sh/ty"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json" alt="ty"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/Solganis/assertpy2"><img src="https://api.scorecard.dev/projects/github.com/Solganis/assertpy2/badge" alt="OpenSSF Scorecard"></a>
  <a href="https://www.bestpractices.dev/projects/12990"><img src="https://www.bestpractices.dev/projects/12990/badge" alt="OpenSSF Best Practices"></a>
  <br>
  <a href="https://solganis.github.io/assertpy2/type-safety/"><img src="https://img.shields.io/badge/type--checked-ty%20%7C%20mypy%20%7C%20pyright-2ea043" alt="public overloads type-checked by ty, mypy --strict, and pyright with zero suppressions"></a>
</p>

---

<h2 align="center"><a href="https://solganis.github.io/assertpy2/getting-started/">Quick start</a></h2>

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

Browse the [full documentation](https://solganis.github.io/assertpy2/) for every assertion, matcher, and integration.

<h2 align="center"><a href="https://solganis.github.io/assertpy2/comparison/">Why fluent assertions?</a></h2>

A fluent chain reads as one intent and replaces several bare asserts - and your IDE
offers only the [methods that fit the value's type](https://solganis.github.io/assertpy2/type-safety/):

```py
# bare - three statements, no autocomplete help
assert isinstance(items, list)
assert len(items) == 3
assert "admin" in items

# assertpy2 - one chain, type-aware autocomplete
assert_that(items).is_type_of(list).is_length(3).contains("admin")
```

The real difference shows up when a test fails. Here a nested response has two wrong
fields. Plain `assert` dumps both structures and leaves you to find them:

```text
assert response == expected
E   AssertionError: assert {'id': 1, ...} == {'id': 1, ...}
E     Omitting 1 identical items, use -vv to show
E     Differing items:
E     {'user': {'name': 'Alice', 'role': 'superadmin'}} != {'user': {'name': 'Alice', 'role': 'admin'}}
E     {'status': 'active'} != {'status': 'disabled'}
```

assertpy2 reports the [exact path to every difference](https://solganis.github.io/assertpy2/errors/#rich-pytest-diffs), in color:

```python
assert_that(response).is_equal_to(expected)
```

<p align="center">
  <img src="https://raw.githubusercontent.com/Solganis/assertpy2/main/docs/assets/diff-equal.png" width="300" alt="Structured diff in the terminal: user.role shown with its path, removal in red and addition in green">
</p>

Recursive diffs work for dicts, dataclasses, namedtuples, and Pydantic models.
For responses with dynamic fields (IDs, timestamps), validate a subset with
[`matches_structure()`](https://solganis.github.io/assertpy2/matchers/#structural-matching) instead of exact equality.

The same path-level treatment for dicts, lists, sets, and matcher predicates:

<p align="center">
  <img src="https://raw.githubusercontent.com/Solganis/assertpy2/main/docs/assets/diff-gallery.png" width="640" alt="Structured diffs in the terminal: dict path, list element, set extra/missing, and structural-matcher predicate diffs, side by side">
</p>

<h2 align="center"><a href="https://solganis.github.io/assertpy2/type-safety/">Type-aware autocomplete</a></h2>

`assert_that()` uses `@overload` to return type-specific Protocols.
Your IDE shows only methods relevant to the value you're testing, not all 100+:

- `assert_that("hello").` &rarr; string methods: `starts_with`, `matches`, `is_alpha`, ...
- `assert_that(42).` &rarr; numeric methods: `is_positive`, `is_between`, `is_close_to`, ...
- `assert_that(Path("/tmp")).` &rarr; path methods: `exists`, `is_file`, `is_readable`, ...
- `assert_that(my_dict).` &rarr; dict methods: `contains_key`, `contains_entry`, `has_json_path`, ...
- `assert_that(b"\x89PNG").` &rarr; bytes methods: `starts_with_bytes`, `is_valid_utf8`, `decoded_as`, ...

9 type-specific Protocols instead of one `Any`. Works in PyCharm, VS Code, and any LSP-compatible editor.

See the [**Type Safety**](https://solganis.github.io/assertpy2/type-safety/) guide for the full walkthrough.

<h2 align="center">Features</h2>

**Fluent API**

- [**Composable matchers**](https://solganis.github.io/assertpy2/matchers/): `match.greater_than(5)`, `match.is_uuid()`, combine with `&`, `|`, `~`. Also work with plain `assert ==`.
- [**Structural matching**](https://solganis.github.io/assertpy2/matchers/#structural-matching): `matches_structure()` for declarative dict/API response validation, reporting the exact path to each mismatch on failure.
- [**Recursive field assertions**](https://solganis.github.io/assertpy2/assertions/#recursive-field-assertions): `all_fields_satisfy()` / `has_no_none_fields()` apply a predicate to every leaf of an object graph, reporting the exact path.
- [**Universal negation**](https://solganis.github.io/assertpy2/fluent/#universal-negation): `.not_` inverts any assertion without dedicated `is_not_*` methods.
- [**Collection pipeline**](https://solganis.github.io/assertpy2/fluent/#collection-pipeline): `filtered_on()`, `mapped()`, `flat_mapped()`, `first()`, `last()`, `element()`, `single()`.
- [**Positional & pairwise checks**](https://solganis.github.io/assertpy2/assertions/#lists): `satisfies_exactly()`, `zip_satisfies()`, `contains_only_once()`, `has_same_size_as()`, plus `*_in_any_order` variants.
- [**Fluent chaining**](https://solganis.github.io/assertpy2/fluent/#chaining): write assertions as readable one-liners that chain naturally.

**Built-in types**

- [Strings](https://solganis.github.io/assertpy2/assertions/#strings), [numbers](https://solganis.github.io/assertpy2/assertions/#numbers), [lists](https://solganis.github.io/assertpy2/assertions/#lists), [tuples](https://solganis.github.io/assertpy2/assertions/#tuples), [sets](https://solganis.github.io/assertpy2/assertions/#sets), [dicts](https://solganis.github.io/assertpy2/assertions/#dicts), [dates](https://solganis.github.io/assertpy2/assertions/#dates), [booleans](https://solganis.github.io/assertpy2/assertions/#booleans), [objects](https://solganis.github.io/assertpy2/assertions/#objects), [bytes](https://solganis.github.io/assertpy2/assertions/#bytes--bytearray), [files](https://solganis.github.io/assertpy2/assertions/#files), [exceptions](https://solganis.github.io/assertpy2/errors/#expected-exceptions).
- [**Bytes assertions**](https://solganis.github.io/assertpy2/assertions/#bytes--bytearray): `is_valid_utf8()`, `starts_with_bytes()`, `is_hex_equal_to()`, `decoded_as()` for `bytes`/`bytearray`.
- [**Dynamic assertions**](https://solganis.github.io/assertpy2/assertions/#dynamic-assertions-on-objects): `has_<name>()` for any attribute, property, or zero-argument method.
- [**Dict comparison**](https://solganis.github.io/assertpy2/assertions/#selective-comparison-ignore--include): `is_equal_to()` with `ignore` and `include` for selective key/field matching (dicts, dataclasses, namedtuples, Pydantic models, attrs, plain objects), including by regex or type.
- [**Recursive comparison**](https://solganis.github.io/assertpy2/assertions/#recursive-comparison-tolerance--custom-comparators): `is_equal_to()` with `tolerance` (absolute float tolerance at any depth) or `comparators` (per-type / per-field predicates) for nested structures.
- [**Extracting**](https://solganis.github.io/assertpy2/assertions/#extracting-attributes-from-objects): flatten collections on attributes with `filter` and `sort` support.

**Testing**

- [**Soft assertions**](https://solganis.github.io/assertpy2/testing/#soft-assertions): thread-safe, async-safe via `contextvars`. Group errors with `sa.group()`, or use `assert_all()`.
- [**Polling assertions**](https://solganis.github.io/assertpy2/testing/#async-assertions): `eventually()` (async) / `eventually_sync()` (blocking) with retry for eventual consistency.
- [**Structured errors**](https://solganis.github.io/assertpy2/errors/#structured-errors): `AssertionFailure` with `.actual`, `.expected`, `.diff` attributes.
- [**Rich pytest diffs**](https://solganis.github.io/assertpy2/errors/#rich-pytest-diffs): recursive structural diffs for lists, sets, strings, dicts, dataclasses, namedtuples, Pydantic models, and matcher-based assertions (`matches_structure()`, `satisfies()`, `each()`). Circular reference protection.
- [**Snapshot testing**](https://solganis.github.io/assertpy2/testing/#snapshot-testing): store and compare data structures in JSON format; update via `--assertpy2-snapshot-update`.

**Type safety**

- [**Type-aware autocomplete**](https://solganis.github.io/assertpy2/type-safety/): 9 Protocols, IDE shows only relevant methods per type.
- [**Typed narrowing**](https://solganis.github.io/assertpy2/type-safety/#typed-narrowing-with-value): `.value` hands the checked value back; `is_not_none()` / `is_instance_of()` narrow its static type - no casts.
- **py.typed**: `Self` return types, PEP 561 compliant ([PEP 561](https://peps.python.org/pep-0561/)).

**Extensibility**

- [**Custom matchers**](https://solganis.github.io/assertpy2/matchers/#custom-matchers): `register_matcher()` for domain-specific matchers, composable with `&`, `|`, `~`.
- [**Regex group extraction**](https://solganis.github.io/assertpy2/data/#regex-group-extraction): `extracting_group()` and `matches_with_groups()` for regex captures.
- [**Extensions**](https://solganis.github.io/assertpy2/extending/): `add_extension()` for custom assertion methods.

See the [full documentation](https://solganis.github.io/assertpy2/) for all assertion methods, examples, and advanced features.

<h2 align="center"><a href="https://solganis.github.io/assertpy2/integrations/">Integrations</a></h2>

Optional adapters, each its own extra; full configuration and examples are in the
[Integrations guide](https://solganis.github.io/assertpy2/integrations/).

- [**Allure**](https://solganis.github.io/assertpy2/integrations/#allure) (`pip install assertpy2[allure]`): the pytest plugin auto-attaches structured diff and actual/expected data to Allure reports, in three configurable modes.
- [**Behave**](https://solganis.github.io/assertpy2/integrations/#behave) (`pip install assertpy2[behave]`): ready-made parameter types (`PositiveInt`, `NonEmptyString`, ...) for step definitions like `{age:PositiveInt}`.
- [**JSON**](https://solganis.github.io/assertpy2/data/#json-path--schema) (`pip install assertpy2[json]`): JSONPath navigation (`at_json_path()`, `has_json_path()`) and JSON Schema validation (`matches_json_schema()`).
- [**Data frames**](https://solganis.github.io/assertpy2/integrations/#data-frames-and-arrays) (`pip install assertpy2[pandas]` / `[polars]` / `[numpy]`): fluent equality for pandas/polars frames and numpy arrays, carrying each library's own diff.

---

<p align="center">
  <a href="https://github.com/Solganis/assertpy2/blob/main/LICENSE">BSD 3-Clause License</a>
</p>
