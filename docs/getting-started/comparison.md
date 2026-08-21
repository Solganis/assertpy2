# Comparison

Where this library sits next to the four common alternatives: pytest's bare `assert`, PyHamcrest, the
original assertpy, and dirty-equals.

The same check written each way, the same failure printed each way, and a rule for choosing at the end.

!!! success "In short"
    assertpy2 unifies the fluent, matcher, and `==` styles in one typed package, then adds thread-
    and async-safe soft assertions, async polling, structured failures, and rich pytest diffs.

    Two things none of the alternatives below offer: the value you pass decides which assertions a
    type checker will accept, and a run can be told to report fluent chains that were built and never
    checked anything.


## All three styles, one import

assertpy2's fluent, matcher, and `==` styles are not mutually exclusive. A single import gives you all
three, mixable in the same test suite:

```python
from assertpy2 import assert_that, match

# fluent chaining (the assertpy heritage)
assert_that(value).is_positive().is_less_than(100)

# matchers inside plain == (the dirty-equals style)
assert response == {"id": match.is_positive(), "name": match.is_non_empty_string()}

# composable matchers (the Hamcrest style)
assert_that(value).satisfies(match.greater_than(0) & match.less_than(100))
```

## The same check, five ways

That `id` is a positive number and `name` a non-empty string:

=== "assertpy2"

    A typed fluent chain, composable matchers, and the `==` form, from one import.

    ```python
    from assertpy2 import assert_that, match

    assert_that(response).matches_structure({
        "id": match.is_positive(),
        "name": match.is_non_empty_string(),
    })

    # the same matchers go straight into a literal, no wrapper
    assert response == {"id": match.is_positive(), "name": match.is_non_empty_string()}
    ```

=== "pytest assert"

    Plain statements, rewritten for introspection. No API to learn, no matcher abstraction.

    ```python
    assert response["id"] > 0
    assert isinstance(response["name"], str) and response["name"]
    ```

=== "PyHamcrest"

    A matcher framework, where the matcher is the central abstraction.

    <!-- docs-guard: skip -->
    ```python
    from hamcrest import (
        assert_that, has_entries, greater_than, instance_of, all_of, not_, empty,
    )

    assert_that(response, has_entries({
        "id": greater_than(0),
        "name": all_of(instance_of(str), not_(empty())),
    }))

    # inside a literal it needs an adapter
    assert response == {"id": match_equality(greater_than(0))}
    ```

=== "assertpy"

    The original fluent chain this project is built on. See [Migrating from assertpy](migration.md).

    <!-- docs-guard: skip -->
    ```python
    from assertpy import assert_that

    assert_that(response["id"]).is_positive()
    assert_that(response["name"]).is_not_empty()
    ```

=== "dirty-equals"

    `__eq__` put to work, so the spec lives inside the literal.

    <!-- docs-guard: skip -->
    ```python
    from dirty_equals import IsPositiveInt, IsStr

    assert response == {"id": IsPositiveInt, "name": IsStr(min_length=1)}
    ```

## When it fails

A nested response, after `role` comes back as `"superadmin"`. What each library prints on failure:

=== "assertpy2"

    ```text
    assert_that(response).matches_structure({...})
    --- Structured Diff ---
    diff (match):
      user.role: expected a value in <('admin', 'user')>, but was 'superadmin'
    ```

=== "pytest assert"

    ```text
    assert response == expected
    E   Differing items:
    E   {'user': {'name': 'Alice', 'role': 'superadmin', 'age': 30}} !=
    E   {'user': {'name': 'Alice', 'role': 'admin', 'age': 30}}
    ```

=== "PyHamcrest"

    ```text
    assert_that(response, has_entries(user=has_entries(role=is_in(["admin", "user"]))))
    E   AssertionError:
    E   Expected: a dictionary containing {'user': a dictionary containing
    E             {'role': one of ('admin', 'user')}}
    E        but: value for 'user' value for 'role' was 'superadmin'
    ```

=== "assertpy"

    ```text
    assert_that(response["user"]).has_role("admin")
    E   AssertionError: Expected <superadmin> to be equal to <admin>
    E                   on key <role>, but was not.
    ```

=== "dirty-equals"

    ```text
    assert response == {"user": {"role": IsOneOf("admin", "user"), ...}}
    E   Differing items:
    E   {'user': {'name': 'Alice', 'role': 'superadmin', 'age': 30}} !=
    E   {'user': {'name': IsStr, 'role': IsOneOf('admin', 'user'), 'age': IsInt}}
    ```

The split is two ways, not four. assertpy2 and PyHamcrest name the path and the predicate. The `==`
styles hand rendering to pytest, which dumps both containers whole.

Between the first two the difference is shape, not information: our diff is also readable as data, and
it comes off a fluent chain rather than a nested matcher expression.

### With a Pydantic model or attrs instance

A model goes in as it is. No `.model_dump()`, no `attrs.asdict()`, and the failure keeps its path:

=== "assertpy2"

    ```python
    assert_that(user).matches_structure({"role": match.is_in("admin", "user")})
    ```

    ```text
    diff (match):
      role: expected a value in <('admin', 'user')>, but was 'superadmin'
    ```

=== "dirty-equals"

    <!-- docs-guard: skip -->
    ```python
    # Pydantic's __eq__ only matches another model, so the dict has to be dumped first
    assert user.model_dump() == {
        "name": IsStr,
        "role": IsOneOf("admin", "user"),
        "age": IsInt,
    }
    ```

    ```text
    E   Differing items:
    E   {'name': 'Alice', 'role': 'superadmin', 'age': 30} !=
    E   {'name': IsStr, 'role': IsOneOf('admin', 'user'), 'age': IsInt}
    ```

## On snapshot testing, where assertpy2 does and does not lead

assertpy2 ships snapshot testing, and the dedicated tools do it better. Three styles, one API:

<!-- docs-guard: skip -->
```python
assert_that(report).snapshot("monthly")                  # external file, syrupy-family
assert_that(order).matches_inline({"id": 7, "total": 42.0})   # in-source literal
assert_that(payload).matches_contract_snapshot("orders")  # paths and types, not values
```

The third is the one with no equivalent elsewhere. It records the *shape* rather than the values, so a
changing total does not fail the test and a disappearing field does:

```text
Expected <{...}> to match the recorded contract, but 1 path changed
  order.total: recorded a number, got a string
```

If snapshots are the workflow, the specialists lead that niche:
[syrupy](https://github.com/syrupy-project/syrupy) for external files and
[inline-snapshot](https://15r10nk.github.io/inline-snapshot/) for in-source. Ours are not
category-leading engines and do not try to be, though `matches_inline()` does record correctly under
`pytest-xdist`, where inline-snapshot disables itself.

Two of the three need no extra dependency. Inline recording uses the optional `[inline]` extra.

## Which to reach for

Everything above answers "what does each one look like". This answers "what should you use", and the
honest answer is not always this library.

### Bare `assert`, when the condition is local

<!-- docs-guard: skip -->
```python
assert response.status_code == 200
```

Nothing to import, nothing to learn, and no way to write a chain that forgets to assert. For a suite of
straightforward checks this stays the right default, and adding a fluent library buys very little.

### A specialist, when one job is the point

<!-- docs-guard: skip -->
```python
# inline-snapshot, when snapshots are the workflow
assert result == snapshot()

# dirty-equals, when a literal spec is all you want
assert response == {"id": IsPositiveInt}
```

### assertpy2, when a suite keeps asking for the same things

```python
# a condition reused across tests
positive_id = match.is_positive() & match.is_instance_of(int)

# a failure that names the path inside a nested payload
assert_that(payload).matches_structure({"user": {"role": match.is_in("admin", "user")}})

# several checks reported together instead of stopping at the first
with soft_assertions():
    assert_that(order.total).is_greater_than(0)
    assert_that(order.items).is_not_empty()

# a value polled until it settles
assert_that(fetch_status).eventually_sync().is_equal_to("READY")

# a chain whose type a checker follows to the end
paid: PaidOrder = assert_that(order).is_not_none().is_instance_of(PaidOrder).value
```

None of the alternatives here covers that from one import.

### What it costs

An API to learn, a dependency to add, and a fluent surface where a chain can be written that never
asserts:

```python
assert_that(user.age).is_positive      # green forever, the parentheses are missing
```

That last one is why the [dangling detector](../guides/assertions.md#assertions-that-never-ran)
exists. It is off unless you turn it on.
