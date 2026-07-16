<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/logo.svg">
    <img src="docs/logo.svg" alt="assertpy2" width="280">
  </picture>
  <br>
  <b>The fully-typed fluent assertion library for Python</b><br>
  A modern, batteries-included fork of <a href="https://github.com/assertpy/assertpy">assertpy</a>
</p>

<p align="center">
  <a href="https://github.com/Solganis/assertpy2/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Solganis/assertpy2/ci.yml?branch=main&amp;label=CI" alt="CI"></a>
  <a href="https://codecov.io/gh/Solganis/assertpy2"><img src="https://codecov.io/gh/Solganis/assertpy2/graph/badge.svg" alt="Coverage"></a>
  <a href="https://pypi.org/project/assertpy2/"><img src="https://img.shields.io/pypi/v/assertpy2" alt="PyPI version"></a>
  <a href="https://pypi.org/project/assertpy2/"><img src="https://img.shields.io/pypi/pyversions/assertpy2" alt="Python"></a>
  <a href="https://pepy.tech/projects/assertpy2"><img src="https://static.pepy.tech/badge/assertpy2/month" alt="Downloads"></a>
  <br>
  <a href="https://solganis.github.io/assertpy2/concepts/type-safety/"><img src="https://img.shields.io/badge/type--checked-ty%20%7C%20mypy%20%7C%20pyright-2ea043" alt="public overloads type-checked by ty, mypy --strict, and pyright with zero suppressions"></a>
  <a href="https://solganis.github.io/assertpy2/"><img src="https://img.shields.io/badge/docs-online-black" alt="Documentation"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/Solganis/assertpy2"><img src="https://img.shields.io/ossf-scorecard/github.com/Solganis/assertpy2?label=OpenSSF%20Scorecard" alt="OpenSSF Scorecard"></a>
</p>

---

<h2 align="center"><a href="https://solganis.github.io/assertpy2/getting-started/quickstart/">Quick start</a></h2>

```bash
pip install assertpy2  # drop-in replacement for assertpy, just change the import
```

```python
from assertpy2 import assert_that

def test_user():
    user = {"name": "Alice", "age": 30, "roles": ["viewer", "editor"]}

    assert_that(user).contains_key("name", "age")
    assert_that(user["age"]).is_between(18, 120)
    assert_that(user["roles"]).contains("viewer").does_not_contain("admin")
    assert_that(user).has_name("Alice")
```

The [full documentation](https://solganis.github.io/assertpy2/) covers every assertion, matcher, and integration.

<h2 align="center"><a href="https://solganis.github.io/assertpy2/getting-started/comparison/">Why fluent assertions?</a></h2>

A fluent chain reads as one intent and replaces several bare asserts -<br>
and your IDE offers only the [methods that fit the value's type](https://solganis.github.io/assertpy2/concepts/type-safety/):

```python
# bare - three statements, no autocomplete help
assert isinstance(items, list)
assert len(items) == 3
assert "admin" in items

# assertpy2 - one chain, type-aware autocomplete
assert_that(items).is_instance_of(list).is_length(3).contains("admin")
```

The real difference shows up when a test fails. Here a nested response has two wrong fields.<br>
Plain `assert` dumps both structures and leaves you to find them:

```text
assert response == expected
E   AssertionError: assert {'id': 1, ...} == {'id': 1, ...}
E     Omitting 1 identical items, use -vv to show
E     Differing items:
E     {'user': {'name': 'Alice', 'role': 'superadmin'}} != {'user': {'name': 'Alice', 'role': 'admin'}}
E     {'status': 'active'} != {'status': 'disabled'}
```

assertpy2 reports the [exact path to every difference](https://solganis.github.io/assertpy2/guides/errors/#rich-pytest-diffs), in color:

```python
assert_that(response).is_equal_to(expected)
```

<p align="center">
  <img src="https://raw.githubusercontent.com/Solganis/assertpy2/main/docs/assets/diff-equal.png" width="300" alt="Structured diff in the terminal: user.role shown with its path, removal in red and addition in green">
</p>

Recursive diffs cover dicts, dataclasses, namedtuples, attrs classes, and Pydantic models - and lists, sets, and matcher predicates get the same path-level treatment. For dynamic fields (IDs, timestamps), validate a subset with [`matches_structure()`](https://solganis.github.io/assertpy2/guides/matchers/#structural-matching).

<p align="center">
  <img src="https://raw.githubusercontent.com/Solganis/assertpy2/main/docs/assets/diff-gallery.png" width="640" alt="Structured diffs in the terminal: dict path, list element, set extra/missing, and structural-matcher predicate diffs, side by side">
</p>

<h2 align="center"><a href="https://solganis.github.io/assertpy2/concepts/type-safety/">Type-aware autocomplete</a></h2>

`assert_that()` uses `@overload` to return type-specific Protocols.<br>
Your IDE shows only methods relevant to the value you're testing, not all 100+:

- `assert_that("hello").` &rarr; string methods: `starts_with`, `matches`, `is_alpha`, ...
- `assert_that(42).` &rarr; numeric methods: `is_positive`, `is_between`, `is_close_to`, ...
- `assert_that(Path("/tmp")).` &rarr; path methods: `exists`, `is_file`, `is_readable`, ...
- `assert_that(my_dict).` &rarr; dict methods: `contains_key`, `contains_entry`, `has_json_path`, ...
- `assert_that(b"\x89PNG").` &rarr; bytes methods: `starts_with_bytes`, `is_valid_utf8`, `decoded_as`, ...

9 type-specific Protocols instead of one `Any`.<br>
Works in PyCharm, VS Code, and any LSP-compatible editor.

<h2 align="center"><a href="https://solganis.github.io/assertpy2/concepts/type-safety/#typed-narrowing-with-value">Typed narrowing</a></h2>

An assertion doesn't just check a value - it hands it back, statically narrowed. `is_not_none()` strips
`None`, `is_instance_of()` narrows to the class, and `.value` returns the result with no `cast` and no
bare `assert`:

```python
order = assert_that(repo.find(42)).is_not_none().is_instance_of(PaidOrder).value
order.refund()  # statically PaidOrder - verified by ty, mypy, and pyright
```

For API tests, [`assert_conforms()`](https://solganis.github.io/assertpy2/concepts/type-safety/#contract-narrowing-with-assert_conforms) validates a raw payload against a Pydantic model and narrows the chain to it,<br>
with `exact=True` catching silent contract drift:

```python
data = assert_conforms(response.json(), OrderModel).value  # data: OrderModel
```

Returning the value it verified, statically narrowed,<br>
lets you assert and use the result in a single step.

<h2 align="center">Features</h2>

**Fluent API**

- [**Composable matchers**](https://solganis.github.io/assertpy2/guides/matchers/): `match.greater_than(5)`, `match.is_uuid()`, combine with `&`, `|`, `~`. Also work with plain `assert ==`.
- [**Structural matching**](https://solganis.github.io/assertpy2/guides/matchers/#structural-matching): `matches_structure()` for declarative dict/API-response validation, reporting the exact path on failure.
- [**Recursive field assertions**](https://solganis.github.io/assertpy2/guides/assertions/#recursive-field-assertions): `all_fields_satisfy()` / `has_no_none_fields()` apply a predicate to every leaf of an object graph, reporting the exact path.
- [**Universal negation**](https://solganis.github.io/assertpy2/guides/fluent/#universal-negation): `.not_` inverts any assertion without dedicated `is_not_*` methods.
- [**Collection pipeline**](https://solganis.github.io/assertpy2/guides/fluent/#collection-pipeline): `filtered_on()`, `mapped()`, `flat_mapped()`, `first()`, `last()`, `element()`, `single()`.
- [**Positional & pairwise checks**](https://solganis.github.io/assertpy2/guides/assertions/#lists): `satisfies_exactly()`, `zip_satisfies()`, `contains_only_once()`, `has_same_size_as()`, plus `*_in_any_order` variants.
- [**Fluent chaining**](https://solganis.github.io/assertpy2/guides/fluent/#chaining): write assertions as readable one-liners that chain naturally.

**Type safety**

- [**Type-aware autocomplete**](https://solganis.github.io/assertpy2/concepts/type-safety/): 9 Protocols, IDE shows only relevant methods per type.
- [**Typed narrowing**](https://solganis.github.io/assertpy2/concepts/type-safety/#typed-narrowing-with-value): `.value` hands the checked value back; `is_not_none()`, `is_instance_of()`, and a [`satisfies()` `TypeIs` predicate](https://solganis.github.io/assertpy2/concepts/type-safety/#refinement-narrowing-with-a-typeis-predicate-advanced) narrow its static type - no casts.
- [**Contract testing**](https://solganis.github.io/assertpy2/concepts/type-safety/#contract-narrowing-with-assert_conforms): `assert_conforms()` validates a raw payload against a Pydantic model and narrows the chain to it - the capstone for API-response tests; [`exact=True`](https://solganis.github.io/assertpy2/concepts/type-safety/#contract-drift-with-exacttrue) catches silent contract drift (undeclared fields), `each=True` validates list endpoints.
- **py.typed**: `Self` return types, PEP 561 compliant ([PEP 561](https://peps.python.org/pep-0561/)).

**Built-in types**

- [Strings](https://solganis.github.io/assertpy2/guides/assertions/#strings), [numbers](https://solganis.github.io/assertpy2/guides/assertions/#numbers), [lists](https://solganis.github.io/assertpy2/guides/assertions/#lists), [tuples](https://solganis.github.io/assertpy2/guides/assertions/#tuples), [sets](https://solganis.github.io/assertpy2/guides/assertions/#sets), [dicts](https://solganis.github.io/assertpy2/guides/assertions/#dicts), [dates](https://solganis.github.io/assertpy2/guides/assertions/#dates), [booleans](https://solganis.github.io/assertpy2/guides/assertions/#booleans), [objects](https://solganis.github.io/assertpy2/guides/assertions/#objects), [bytes](https://solganis.github.io/assertpy2/guides/assertions/#bytes--bytearray), [files](https://solganis.github.io/assertpy2/guides/assertions/#files), [exceptions](https://solganis.github.io/assertpy2/guides/errors/#expected-exceptions).
- [**Bytes assertions**](https://solganis.github.io/assertpy2/guides/assertions/#bytes--bytearray): `is_valid_utf8()`, `starts_with_bytes()`, `is_hex_equal_to()`, `decoded_as()` for `bytes`/`bytearray`.
- [**Dynamic assertions**](https://solganis.github.io/assertpy2/guides/assertions/#dynamic-assertions-on-objects): `has_<name>()` for any attribute, property, or zero-argument method.
- [**Dict comparison**](https://solganis.github.io/assertpy2/guides/assertions/#selective-comparison-ignore--include): `is_equal_to(ignore=..., include=...)` for selective key/field matching across dicts, dataclasses, namedtuples, Pydantic models, attrs, and plain objects - by name, regex, or type.
- [**Recursive comparison**](https://solganis.github.io/assertpy2/guides/assertions/#recursive-comparison-tolerance--custom-comparators): `is_equal_to()` with `tolerance`, `comparators`, or `ignore_null` for nested structures.
- [**Extracting**](https://solganis.github.io/assertpy2/guides/assertions/#extracting-attributes-from-objects): flatten collections on attributes with `filter` and `sort` support.

**Testing**

- [**Soft assertions**](https://solganis.github.io/assertpy2/guides/testing/#soft-assertions): thread-safe, async-safe via `contextvars`; each collected failure is reported with its `file:line`. Group errors with `sa.group()`, or use `assert_all()`.
- [**Polling assertions**](https://solganis.github.io/assertpy2/guides/testing/#async-assertions): `eventually()` (async) / `eventually_sync()` (blocking) retry for eventual consistency, with a convergence trace pinpointing why a timeout never settled.
- [**Expected exceptions**](https://solganis.github.io/assertpy2/guides/errors/#expected-exceptions): `raises().when_called_with()` then assert on the message, walk the cause chain (`caused_by()`, `has_root_cause()`), match an `ExceptionGroup` (`contains_error()`), or pivot to the exception object (`raised()`).
- [**Structured errors**](https://solganis.github.io/assertpy2/guides/errors/#structured-errors): `AssertionFailure` with `.actual`, `.expected`, `.diff` attributes.
- [**Rich pytest diffs**](https://solganis.github.io/assertpy2/guides/errors/#rich-pytest-diffs): recursive structural diffs across lists, sets, dicts, dataclasses, namedtuples, attrs classes, Pydantic models, and matchers, with circular-reference protection.
- [**Snapshot testing**](https://solganis.github.io/assertpy2/guides/testing/#snapshot-testing): store and compare data structures in JSON format; update via `--assertpy2-snapshot-update`. [`matches_contract_snapshot()`](https://solganis.github.io/assertpy2/guides/testing/#contract-snapshots) catches structural regressions, value-tolerant.
- [**Inline snapshots**](https://solganis.github.io/assertpy2/guides/testing/#inline-snapshots): `matches_inline()` records the expected value straight into the test source with `--assertpy2-snapshot-update`; the comparison is a plain equality check, so it runs under `pytest-xdist` with no assertion rewriting.
- [**OpenAPI response contracts**](https://solganis.github.io/assertpy2/reference/json/#assertpy2.json_mixin.JsonMixin.conforms_to_openapi): `conforms_to_openapi(spec, path, method)` validates a JSON response body against an operation's response schema (OpenAPI 3.0/3.1, `$ref`, `oneOf`, `enum`, `format`), reporting every violation with its JSON path.

**Extensibility**

- [**Custom matchers**](https://solganis.github.io/assertpy2/guides/matchers/#custom-matchers): `register_matcher()` for domain-specific matchers, composable with `&`, `|`, `~`.
- [**Regex group extraction**](https://solganis.github.io/assertpy2/guides/data/#regex-group-extraction): `extracting_group()` and `matches_with_groups()` for regex captures.
- [**Extensions**](https://solganis.github.io/assertpy2/extending/custom-assertions/): `add_extension()` for custom assertion methods.

<h2 align="center"><a href="https://solganis.github.io/assertpy2/extending/integrations/">Integrations</a></h2>

- [**Allure**](https://solganis.github.io/assertpy2/extending/integrations/#allure) (`pip install assertpy2[allure]`): the pytest plugin auto-attaches structured diff and actual/expected data to Allure reports, in three configurable modes.
- [**Behave**](https://solganis.github.io/assertpy2/extending/integrations/#behave) (`pip install assertpy2[behave]`): ready-made parameter types (`PositiveInt`, `NonEmptyString`, ...) for step definitions like `{age:PositiveInt}`.
- [**JSON**](https://solganis.github.io/assertpy2/guides/data/#json-path--schema) (`pip install assertpy2[json]`): JSONPath navigation (`at_json_path()`, `has_json_path()`) and JSON Schema validation (`matches_json_schema()`).
- [**Data frames**](https://solganis.github.io/assertpy2/extending/integrations/#data-frames-and-arrays) (`pip install assertpy2[pandas]` / `[polars]` / `[numpy]`): fluent equality for pandas/polars frames and numpy arrays, carrying each library's own diff.

---

<p align="center">
  <a href="https://github.com/Solganis/assertpy2/blob/main/LICENSE">BSD 3-Clause License</a>
</p>
