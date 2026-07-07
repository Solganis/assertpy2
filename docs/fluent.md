# Fluent API

## Chaining

Assertions chain into a single statement that reads like a sentence:

```python
assert_that("foo").is_length(3).starts_with("f").ends_with("oo")
assert_that([1, 2, 3]).is_type_of(list).contains(1, 2).does_not_contain(4, 5)
assert_that(fred).has_first_name("Fred").has_last_name("Smith").has_shoe_size(12)
assert_that(people).is_length(2).extracting("first_name").contains("Fred", "Joe")
```

## Universal negation

The `.not_` property inverts the next assertion in the chain, so there is no need for dedicated
`is_not_*` methods:

```python
assert_that(5).not_.is_none()
assert_that("abc123").not_.is_alpha()
assert_that([3, 1, 2]).not_.is_sorted()
assert_that(42).not_.is_in(1, 2, 3)
assert_that("hello").not_.is_instance_of(int)
```

Chaining continues normally after a negated assertion:

```python
assert_that(5).not_.is_none().is_positive()
assert_that("hello").not_.is_empty().is_length(5).is_alpha()
```

`.not_` works with descriptions, soft assertions, warn mode, and matchers:

```python
assert_that(5).described_as("my check").not_.is_positive()
# AssertionError: [my check] Expected <5> to NOT satisfy: is_positive()

with soft_assertions():
    assert_that(5).not_.is_positive()    # collected, not raised

assert_warn("hello").not_.is_alpha()     # logs a warning

assert_that(-5).not_.satisfies(match.is_positive())
assert_that([1, -2, 3]).not_.each(match.is_positive())
```

!!! note
    Only assertions can be negated. Chain steps that configure or transform instead of asserting -
    `described_as()`, `extracting()`, the collection pipeline (`filtered_on()`, `mapped()`,
    `first()`, ...), `decoded_as()`, `at_json_path()`, `eventually()`, `eventually_sync()` - raise
    a `TypeError` under `.not_`; place them before `.not_` (or negate the assertion that follows
    them) instead:

    ```python
    assert_that(1).described_as("desc").not_.is_none()          # description before not_
    assert_that(people).extracting("name").not_.contains("Zoe")  # negate after extracting
    ```

## Collection pipeline

Pipeline methods transform the value before asserting. Each returns a new builder, so the original
value is unchanged and steps chain freely.

### filtered_on(predicate)

Filter elements by a callable or matcher:

```python
assert_that([1, -2, 3, -4]).filtered_on(lambda x: x > 0).is_length(2)
assert_that(items).filtered_on(match.is_positive()).is_not_empty()
assert_that(users).filtered_on(match.has_property("active")).is_length(5)
```

### mapped(func)

Transform each element:

```python
assert_that(["a", "b", "c"]).mapped(str.upper).contains("A", "B")
assert_that(users).mapped(lambda u: u.name).contains("Alice", "Bob")
```

### flat_mapped(func)

Transform and flatten:

```python
assert_that(["ab", "cd"]).flat_mapped(list).contains("a", "b", "c", "d")
assert_that(users).flat_mapped(lambda u: u.tags).contains("admin", "user")
```

### first() / last() / element(index) / single()

Navigate to a specific element and assert on it:

```python
assert_that([10, 20, 30]).first().is_equal_to(10)
assert_that([10, 20, 30]).last().is_equal_to(30)
assert_that([10, 20, 30]).element(1).is_equal_to(20)
assert_that([42]).single().is_equal_to(42)
```

!!! warning
    `first()`, `last()`, and `single()` raise `ValueError` on an empty collection (`single()` also on
    more than one element); `element(index)` raises `IndexError` when the index is out of range.

### Chaining pipeline steps

Pipeline methods return a new builder, so they chain with each other and with any assertion:

```python
assert_that(orders).filtered_on(lambda o: o.status == "FAILED").mapped(lambda o: o.total).first().satisfies(match.is_positive())
assert_that(items).filtered_on(match.is_positive()).not_.is_empty()
```

!!! note
    Pipeline navigation (`first`/`last`/`element`/`single`/`mapped`/`flat_mapped`) keeps the
    collection's static type, so a type checker still offers iterable methods after it. End on a
    type-agnostic assertion (`satisfies`, `is_equal_to`, `is_not_none`, ...) rather than a
    type-specific one like `is_positive`.
