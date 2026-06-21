# Type Assertions

`assert_that()` returns a type-specific set of assertions. The sections below group them by value type.

## Strings

```python
assert_that("").is_empty().is_false().is_type_of(str)
assert_that("foo").is_length(3).is_not_empty().is_alpha().is_lower()
assert_that("123").is_digit()
assert_that("FOO").is_upper()
assert_that("foo").is_equal_to("foo").is_not_equal_to("bar")
assert_that("foo").is_equal_to_ignoring_case("FOO")
assert_that("foo123").is_alphanumeric()
assert_that("   ").is_whitespace()

assert_that("foo").contains("f", "oo")
assert_that("foo").contains_ignoring_case("F", "oO")
assert_that("foo").does_not_contain("x")
assert_that("foo").contains_only("f", "o")
assert_that("foo").contains_sequence("o", "o")
assert_that("foobar").contains_any_of("foo", "xyz")
assert_that("foobar").contains_none_of("xyz", "abc")
assert_that("foo").contains_duplicates()
assert_that("fox").does_not_contain_duplicates()

assert_that("foo").is_in("foo", "bar", "baz")
assert_that("foo").is_subset_of("abcdefghijklmnopqrstuvwxyz")
assert_that("foo").starts_with("f").ends_with("oo")

assert_that("foo").matches(r"\w")
assert_that("123-456-7890").matches(r"\d{3}-\d{3}-\d{4}")
assert_that("foo").does_not_match(r"\d+")
```

!!! note "Regex matching"
    Use raw strings (`r"..."`) for patterns. `matches()` passes on **partial** matches (like the
    underlying `re.match`); anchor the pattern (`^...$`) to match the whole string. Inline flags such as
    `(?m)` and `(?s)` work, even though `matches()` takes no flags argument.

    ```python
    assert_that("foo").matches(r"\w{2}")     # partial, passes
    assert_that("foo").matches(r"^\w{3}$")   # whole string, passes
    assert_that("foo").matches(r"^\w{2}$")   # fails
    ```

## Numbers

```python
assert_that(0).is_zero().is_false().is_type_of(int)
assert_that(1).is_not_zero().is_positive()
assert_that(-1).is_negative()
assert_that(4).is_even()
assert_that(3).is_odd()
assert_that(9).is_divisible_by(3)

assert_that(123).is_equal_to(123).is_not_equal_to(456)
assert_that(123).is_greater_than(100).is_greater_than_or_equal_to(123)
assert_that(123).is_less_than(200).is_less_than_or_equal_to(200)
assert_that(123).is_between(100, 200)
assert_that(123).is_close_to(100, 25)
assert_that(1).is_in(0, 1, 2, 3).is_not_in(-1, -2, -3)

# floats
assert_that(123.4).is_close_to(123, 0.5)
assert_that(123.4).is_between(100.1, 200.2)
assert_that(float("NaN")).is_nan()
assert_that(123.4).is_not_nan()
assert_that(float("Inf")).is_inf()
assert_that(123.4).is_not_inf()
```

!!! warning "Floats and equality"
    Avoid `is_equal_to()` with `float` values. Use `is_close_to()` or `is_between()` instead.

## Lists

```python
assert_that([]).is_empty().is_type_of(list).is_iterable()
assert_that(["a", "b"]).is_length(2).is_not_empty()
assert_that(["a", "b"]).is_equal_to(["a", "b"]).is_not_equal_to(["b", "a"])

assert_that(["a", "b"]).contains("b", "a")
assert_that(["a", "b"]).does_not_contain("x", "y")
assert_that(["a", "b"]).contains_only("a", "b")
assert_that(["a", "b", "c"]).contains_sequence("b", "c")
assert_that(["a", "b", "c"]).contains_exactly("a", "b", "c")
assert_that(["a", "x", "b", "y", "c"]).contains_in_order("a", "b", "c")
assert_that(["a", "b"]).is_subset_of(["a", "b", "c"])
assert_that(["a", "b", "c"]).is_sorted()
assert_that(["c", "b", "a"]).is_sorted(reverse=True)
assert_that(["a", "x", "x"]).contains_duplicates()
assert_that(["a", "b", "c"]).does_not_contain_duplicates()
assert_that(["a", "b", "c"]).starts_with("a").ends_with("c")

assert_that([1, -2, 3]).any_satisfy(lambda x: x < 0)
assert_that([1, 2, 3]).all_satisfy(lambda x: x > 0)
assert_that([1, 2, 3]).none_satisfy(lambda x: x < 0)
```

`any_satisfy`, `all_satisfy`, and `none_satisfy` accept both callables and [matchers](matchers.md).

Lists of lists can be flattened by index with `extracting` (see [dict flattening](#dict-flattening)):

```python
people = [["Fred", "Smith"], ["Bob", "Barr"]]
assert_that(people).extracting(0).is_equal_to(["Fred", "Bob"])
assert_that(people).extracting(-1).is_equal_to(["Smith", "Barr"])
```

## Tuples

Tuples support the same membership, ordering, and duplicate assertions as lists:

```python
assert_that(()).is_empty().is_type_of(tuple).is_iterable()
assert_that((1, 2, 3)).is_length(3).is_equal_to((1, 2, 3))
assert_that((1, 2, 3)).contains(3, 2, 1).contains_only(1, 2, 3)
assert_that((1, 2, 3)).contains_sequence(2, 3).contains_exactly(1, 2, 3)
assert_that((1, 5, 2, 8, 3)).contains_in_order(1, 2, 3)
assert_that((1, 2, 3)).is_subset_of((1, 2, 3, 4)).is_sorted()
assert_that((1, 2, 2)).contains_duplicates()
assert_that((1, 2, 3)).starts_with(1).ends_with(3)
```

Tuples of tuples flatten by index with `extracting`:

```python
points = ((1, 2, 3), (4, 5, 6))
assert_that(points).extracting(0).is_equal_to([1, 4])
assert_that(points).extracting(-1).is_equal_to([3, 6])
```

## Dicts

```python
assert_that({}).is_empty().is_type_of(dict)
assert_that({"a": 1, "b": 2}).is_length(2).is_not_empty()
assert_that({"a": 1, "b": 2}).is_equal_to({"b": 2, "a": 1})

assert_that({"a": 1, "b": 2}).contains("b", "a")
assert_that({"a": 1, "b": 2}).does_not_contain("x", "y")
assert_that({"a": 1, "b": 2}).contains_only("a", "b")
assert_that({"a": 1, "b": 2}).is_subset_of({"a": 1, "b": 2, "c": 3})

# contains_key / does_not_contain_key are aliases of contains / does_not_contain
assert_that({"a": 1, "b": 2}).contains_key("b", "a")
assert_that({"a": 1, "b": 2}).does_not_contain_key("x", "y")

assert_that({"a": 1, "b": 2}).contains_value(2, 1)
assert_that({"a": 1, "b": 2}).does_not_contain_value(3, 4)

assert_that({"a": 1, "b": 2}).contains_entry({"a": 1}, {"b": 2})
assert_that({"a": 1, "b": 2}).does_not_contain_entry({"a": 2})
```

### Selective comparison (ignore / include)

`is_equal_to()` can ignore or include specific keys or fields. This works with dicts, dataclasses,
namedtuples, Pydantic models, attrs, and plain objects; for sequences each element is compared pairwise
with the same filters.

```python
# ignore keys (single, list, or nested tuple)
assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, ignore="b")
assert_that({"a": 1, "b": {"c": 2, "d": 3}}).is_equal_to({"a": 1, "b": {"c": 2}}, ignore=("b", "d"))

# include only specific keys
assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2}, include=["a", "b"])

# objects with introspectable fields
@dataclass
class User:
    id: int
    name: str
    email: str

assert_that(User(1, "Alice", "a@x.com")).is_equal_to(User(99, "Alice", "a@x.com"), ignore="id")
```

### Dict flattening

Lists of dicts can be flattened on a key with `extracting` (see
[extracting attributes](#extracting-attributes-from-objects)):

```python
people = [{"first_name": "Fred"}, {"first_name": "Bob"}]
assert_that(people).extracting("first_name").is_equal_to(["Fred", "Bob"])
```

### Dict key assertions

Assert against the value of a key by prepending `has_` to the key name (see
[dynamic assertions](#dynamic-assertions-on-objects)):

```python
fred = {"first_name": "Fred", "last_name": "Smith", "shoe_size": 12}
assert_that(fred).has_first_name("Fred").has_shoe_size(12)
```

## Sets

```python
assert_that(set()).is_empty().is_type_of(set)
assert_that({"a", "b"}).is_length(2).is_equal_to({"b", "a"})
assert_that({"a", "b"}).contains("b", "a").does_not_contain("x")
assert_that({"a", "b"}).contains_only("a", "b")
assert_that({"a", "b"}).is_subset_of({"a", "b", "c"})
assert_that({"a", "b"}).is_subset_of({"a"}, {"b"})
```

## Booleans

```python
assert_that(True).is_true()
assert_that(False).is_false()
assert_that(True).is_type_of(bool)
```

### None

```python
assert_that(None).is_none()
assert_that("").is_not_none()
assert_that(None).is_type_of(type(None))
```

## Dates

`assertpy2` supports dates via the `datetime` type.

```python
import datetime

today = datetime.datetime.today()
yesterday = today - datetime.timedelta(days=1)

assert_that(yesterday).is_before(today)
assert_that(today).is_after(yesterday)
assert_that(today).is_before_or_equal_to(today)
assert_that(today).is_after_or_equal_to(yesterday)
```

Equality can ignore units of time, and the numeric comparisons work on dates too:

```python
assert_that(today).is_equal_to_ignoring_milliseconds(today_0us)
assert_that(today).is_equal_to_ignoring_seconds(today_0s)
assert_that(today).is_equal_to_ignoring_time(today_0h)

assert_that(middle).is_between(yesterday, today)
assert_that(yesterday).is_close_to(today, datetime.timedelta(hours=24))  # tolerance is a timedelta
```

Date properties can be asserted dynamically with `has_<property>` (see
[dynamic assertions](#dynamic-assertions-on-objects)):

```python
x = datetime.datetime(1980, 1, 2, 3, 4, 5, 6)
assert_that(x).has_year(1980).has_month(1).has_day(2)
assert_that(x).has_hour(3).has_minute(4).has_second(5).has_microsecond(6)
```

## Files

```python
assert_that("foo.txt").exists().is_file()
assert_that("missing.txt").does_not_exist()
assert_that("mydir").is_directory()

assert_that("foo.txt").is_named("foo.txt").is_child_of("mydir")
assert_that("foo.txt").is_readable().is_writable()
assert_that("/usr/bin/python").is_executable()
```

Read a file into a string with `contents_of()` (default encoding `utf-8`) and continue with string
assertions:

```python
from assertpy2 import assert_that, contents_of

assert_that(contents_of("foo.txt", "ascii")).starts_with("foo").ends_with("bar").contains("oob")
```

## Bytes / bytearray

Assertions for `bytes` and `bytearray` values:

```python
assert_that(b"hello world").is_valid_utf8()
assert_that(b"hello").is_valid_encoding("ascii")
assert_that(b"\x89PNG\r\n\x1a\n...").starts_with_bytes(b"\x89PNG")
assert_that(b"hello world").contains_bytes(b"world")
assert_that(b"\x89PNG").has_byte_at(0, 0x89)            # IndexError if out of range
assert_that(b"\xab\xcd\xef").is_hex_equal_to("abcdef")
```

`decoded_as()` returns a new builder with the decoded string so string assertions can continue
(`UnicodeDecodeError` is raised if decoding fails):

```python
assert_that(b"hello").decoded_as("utf-8").starts_with("hel").is_length(5)
assert_that(b"hello").decoded_as().is_equal_to("hello")  # default encoding utf-8
```

All bytes assertions work with soft assertions, warn mode, and `.not_` negation.

## Objects

```python
fred = Person("Fred", "Smith")

assert_that(fred).is_not_none().is_type_of(Person).is_instance_of(object)
assert_that(fred).is_same_as(fred)
assert_that(fred.say_hello).is_callable()
assert_that(fred.first_name).is_not_callable()

assert_that(fred.first_name).is_equal_to("Fred")
assert_that(fred.name).is_equal_to("Fred Smith")          # property
assert_that(fred.say_hello()).is_equal_to("Hello, Fred!")  # method
```

### Extracting attributes from objects

Flatten a collection of objects on an attribute, property, or zero-argument method with `extracting`:

```python
people = [Person("Fred", "Smith"), Person("Bob", "Barr")]

assert_that(people).extracting("first_name").contains("Fred", "Bob")
assert_that(people).extracting("first_name", "last_name").contains(("Fred", "Smith"), ("Bob", "Barr"))
assert_that(people).extracting("name").contains("Fred Smith", "Bob Barr")          # property
assert_that(people).extracting("say_hello").contains("Hello, Fred!", "Hello, Bob!")  # method
```

It also works on collections of dicts (extracting by key) and across subclasses in a mixed collection.

#### Filtering

`filter` keeps only items for which it is truthy. It may be a key/attribute name, a dict of
key-value pairs that must all match, or a predicate:

```python
assert_that(users).extracting("user", filter="active").is_equal_to(["Fred", "Johnny"])
assert_that(users).extracting("user", filter={"active": False}).is_equal_to(["Bob"])
assert_that(users).extracting("user", filter=lambda x: x["age"] > 20).is_equal_to(["Fred", "Bob"])
```

#### Sorting

`sort` orders the extracted items. It may be a key/attribute name, an iterable of names (tie-breaking
left to right), or a key function:

```python
assert_that(users).extracting("user", sort="age").is_equal_to(["Johnny", "Fred", "Bob"])
assert_that(users).extracting("user", sort=["active", "age"]).is_equal_to(["Bob", "Johnny", "Fred"])
assert_that(users).extracting("user", sort=lambda x: -x["age"]).is_equal_to(["Bob", "Fred", "Johnny"])
```

### Dynamic assertions on objects

`assertpy2` exposes `has_<name>()` for any attribute, property, or zero-argument method on the value,
so attribute checks stay compact:

```python
fred = Person("Fred", "Smith")

assert_that(fred).has_first_name("Fred")     # attribute
assert_that(fred).has_name("Fred Smith")     # property
assert_that(fred).has_say_hello("Hello, Fred!")  # zero-arg method
```

Dynamic assertions also work on dicts, keyed by entry name:

```python
assert_that({"first_name": "Fred", "last_name": "Smith"}).has_first_name("Fred").has_last_name("Smith")
```

## Exceptions

Exception and warning assertions wrap a *callable* rather than a value: you assert on what calling the
function does, then chain assertions on the resulting message.

```python
assert_that(some_func).raises(RuntimeError).when_called_with("foo")
assert_that(deprecated_func).warns(DeprecationWarning).when_called_with("foo")
```

See [Errors & Reporting](errors.md) for the full set, including
[expected exceptions](errors.md#expected-exceptions), [expected warnings](errors.md#expected-warnings),
and inspecting the call's return value with `returned()`.
