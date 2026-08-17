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
assert_that("foo bar").is_equal_to_ignoring_whitespace("foobar")
assert_that("foo").is_length_between(1, 5)
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
assert_that("FooBar").starts_with_ignoring_case("foo").ends_with_ignoring_case("BAR")

assert_that("foo").matches(r"\w")
assert_that("123-456-7890").matches(r"\d{3}-\d{3}-\d{4}")
assert_that("foo").does_not_match(r"\d+")
```

!!! note "An empty prefix or suffix is refused"
    This one does not follow from Python, where `"foo".startswith("")` is `True`. An empty prefix holds
    for every value, so the assertion cannot fail and checks nothing. `starts_with()`, `ends_with()`,
    their `_ignoring_case` spellings and `starts_with_bytes()` raise `ValueError` rather than pass.

    <!-- docs-guard: raises -->
    ```python
    assert_that("foo").starts_with("")   # ValueError: given prefix arg must not be empty
    ```

    An empty **value** is refused the same way when the subject is a non-string iterable, since there is
    no first element to compare against.

!!! note "Regex matching"
    Use raw strings (`r"..."`) for patterns. `matches()` passes on **partial** matches (like the
    underlying `re.match`). Anchor the pattern (`^...$`) to match the whole string. Inline flags such as
    `(?m)` and `(?s)` work, even though `matches()` takes no flags argument.

    <!-- docs-guard: skip -->
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
assert_that([1, 2, 3]).does_not_contain(match.greater_than(99))   # matchers, same as contains
assert_that(["a", "b"]).contains_only("a", "b")
assert_that(["a", "b", "c"]).contains_sequence("b", "c")
assert_that(["a", "b", "c"]).contains_exactly("a", "b", "c")
assert_that(["c", "a", "b"]).contains_exactly_in_any_order("a", "b", "c")
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

assert_that([2, 4, 6]).satisfies_exactly(
    lambda x: x == 2, lambda x: x == 4, lambda x: x == 6
)
assert_that([4, 2]).satisfies_exactly_in_any_order(lambda x: x == 2, lambda x: x == 4)
assert_that([1, 2, 3]).zip_satisfies([2, 4, 6], lambda actual, other: other == actual * 2)
assert_that([1, 2, 3]).contains_only_once(1, 3)
assert_that([1, 2, 3]).has_same_size_as(("a", "b", "c"))
assert_that([1, 2, 3]).has_size_greater_than(2).has_size_less_than(4).has_size_between(
    1, 5
)
```

`any_satisfy`, `all_satisfy`, and `none_satisfy` accept both callables and [matchers](matchers.md).

#### Assertions that checked nothing

`all_satisfy` over an empty collection passes, the way `all([])` is true: no item failed.

That is the correct answer to the question asked. It is also the most common silent false pass in a
suite, because a query that returned no rows leaves the assertion with nothing to examine.

Turn the guard on and those cases say so:

```bash
pytest --assertpy2-vacuous
```

```text
VacuousAssertionWarning: all_satisfy() passed over an empty value, so nothing
was checked. Pass allow_empty=True if that is intended.
```

The warning points at your line, not at library code. To escalate or relocate it:

- `-W error::assertpy2.VacuousAssertionWarning` turns it into a failure
- `ASSERTPY2_VACUOUS=1` enables it for runners other than pytest

It is off by default for two reasons. A suite running `filterwarnings = ["error"]` would start failing
on upgrade, and a property-based test generates empty collections as a matter of course.

When emptiness is the point of the test, say so per call and the guard stays quiet:

```python
archived_orders = []  # a fixture that yields nothing on a clean database

assert_that(archived_orders).all_satisfy(lambda o: o["closed"], allow_empty=True)
```

`allow_empty` is accepted by the universal assertions:

- `each`, `all_satisfy`, `all_fields_satisfy`, `has_no_none_fields`
- `zip_satisfies`, `is_sorted`, `is_subset_of`

The negative ones never warn. For `none_satisfy`, `does_not_contain` and
`does_not_contain_duplicates` an empty subject is the expected pass, since "no errors were logged" is
exactly what such a test wanted to hear.

The exact-pairing and multiset assertions:

- `satisfies_exactly` - pairs the i-th item with the i-th matcher (equal length required).
  `satisfies_exactly_in_any_order` - any one-to-one pairing instead.
- `zip_satisfies` - checks a two-arg predicate over items zipped with another iterable.
- `contains_only_once` - each given item must occur exactly once.
- `has_same_size_as` - compares lengths against another sized object.
- `contains_exactly_in_any_order` - multiset equality: exact items and counts, order ignored.

#### Assertions that never ran

The guard above catches an assertion that ran and examined nothing. The other half of the same problem
is an assertion that never ran at all:

<!-- docs-guard: skip -->
```python
async def test_the_user_is_active():
    assert_that(user)                              # builds a builder and asserts nothing
    assert_that(user.age).is_positive              # looked up, never called
    assert_that(probe).eventually().is_positive()  # never awaited, so it polls nothing
```

All three are green forever. None is possible with a bare `assert`, which is the price of a fluent
API, so the library owes you a way to find them. The second line is already reported by
[ruff's `B018`](https://docs.astral.sh/ruff/rules/useless-expression/). The other two are reported by
nothing, because a call may have side effects and no linter can know these do not.

```bash
pytest --assertpy2-dangling
```

```text
DanglingAssertionWarning: assert_that() builds a builder here and asserts nothing
```

For a project that wants it on every run, set it in the config instead. The flag still wins, so one
person can try it without editing a file the whole team shares:

```toml
[tool.pytest.ini_options]
assertpy2_dangling = "on"
```

The check reads your test files rather than running anything, so it costs nothing at runtime and
cannot move a stack frame.

**A warning on its own leaves the run green.** pytest exits zero with warnings, so a finding that
should stop a merge has to be promoted to an error. The finding is attached to the test containing the
line, so promoting it fails that test and nothing else:

```toml
[tool.pytest.ini_options]
filterwarnings = [
    "error::assertpy2.DanglingAssertionWarning",
]
```

Without that line the check is a report you have to go and read, which is a fair choice for a first
look and a poor one for CI.

When asserting nothing is the point - a benchmark measuring what building a builder costs, a test of
the assertion machinery itself - say so on the line and the check passes over it:

<!-- docs-guard: skip -->
```python
for index in range(1000):
    assert_that(index)  # assertpy2: allow-dangling
```

The marker is namespaced rather than borrowing ruff's, so a line silenced for one tool is not silently
silenced for the other. It covers the statement it sits on, and on a call broken over several lines the
closing line works.

Most suites of any size wrap `assert_that` in a helper of their own, and the check cannot see through
one it has never heard of. Name yours and it reads them the same way:

```toml
[tool.pytest.ini_options]
assertpy2_dangling_entries = "check verify"
```

Only list a wrapper that **builds** something to assert on, the way `assert_that` does. A helper that
asserts inside its own body is complete as a statement, and listing it would report working code. The
name has to arrive through `from ... import check`, aliases included. That import is the whole
difference between your wrapper and any other function in the world that happens to be called `check`,
so a helper reached as `helpers.check(...)` is out of scope.

Two limits worth knowing before you rely on it. A name this module binds itself is dropped for the
whole file, so one `assert_that = something` anywhere in it turns the check off for that name
everywhere in that file: the trade buys no false alarms at the cost of missed ones. And several
dangling statements in one test arrive as a single warning naming the extra lines, because under
`filterwarnings = ["error"]` the first one ends the test and a second warning would never be seen.

What it deliberately leaves alone:

- a builder bound to a name (`b = assert_that(x)`), because whether `b` is used later is a question
  about the rest of the function, not about that statement
- a chain ending on a pivot (`.described_as(...)`, `.extracting(...)`), since which names are
  assertions is a runtime property of the builder and hard-coding the list here would rot
- `assert_conforms()`, `fail()` and `soft_fail()`, which assert on their own, so a bare call is correct

One limit worth knowing before you count on it: the check reads the test modules pytest collected, and
nothing else. A project that keeps its assertion layer in a package of its own, `framework/asserts/`
rather than the test files, gets no coverage of that package from a pytest run, because pytest never
collects it. Nothing warns you about that, since from inside a run the two cases look identical.

Another cost: the check is static, and a
[dynamic assertion](#dynamic-assertions-on-objects) is resolved at runtime, so
`assert_that(fred).has_first_name` without its parentheses is caught by `B018` rather than here.

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

`is_equal_to()` can ignore or include specific keys or fields. It works across dicts, dataclasses,
namedtuples, Pydantic models, attrs classes, and plain objects. For a sequence, each element is
compared pairwise under the same filters.

The filter accepts a single key, a nested-path tuple, or a `list`/`set`/`frozenset` of those. Any other
iterable (a generator, an iterator, `dict.keys()`) raises `TypeError`.

<!-- docs-guard: skip -->
```python
# ignore keys (single, list/set/frozenset, or nested tuple)
assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, ignore="b")
assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, ignore={"b", "c"})
assert_that({"a": 1, "b": {"c": 2, "d": 3}}).is_equal_to(
    {"a": 1, "b": {"c": 2}}, ignore=("b", "d")
)

# include only specific keys
assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2}, include=["a", "b"])

# objects with introspectable fields
@dataclass
class User:
    id: int
    name: str
    email: str

assert_that(User(1, "Alice", "a@x.com")).is_equal_to(
    User(99, "Alice", "a@x.com"), ignore="id"
)

# attrs instances work the same, including nested paths
@attrs.define
class Account:
    id: int
    owner: str

assert_that(Account(1, "Alice")).is_equal_to(Account(99, "Alice"), ignore="id")
```

`ignore` and `include` also accept a `re.Pattern` (matched against field names) or a `type` (matched
against field values):

<!-- docs-guard: skip -->
```python
import re

# ignore private-ish keys (matched against field names)
assert_that(payload).is_equal_to(expected, ignore=re.compile(r"^_"))
# ignore all float fields
assert_that(payload).is_equal_to(expected, ignore=float)
```

### Recursive comparison (tolerance / custom comparators)

`is_equal_to()` can compare two concrete nested structures with a numeric tolerance or with custom
comparators, anywhere in the graph:

- `tolerance` - an absolute tolerance applied to every real-number leaf (`abs(actual - expected) <= tolerance`).
- `comparators` - maps a `type` or a field name to an `(actual, expected) -> bool` predicate (a
  field-name key wins over a type key).

Tolerated or comparator-equal leaves are reported in neither the message nor the diff.

<!-- docs-guard: skip -->
```python
# absolute float tolerance, at any depth
assert_that({"point": {"x": 1.0001, "y": 2.0}}).is_equal_to(
    {"point": {"x": 1.0, "y": 2.0}}, tolerance=0.001
)

# comparator by type, or by field name
assert_that(order).is_equal_to(
    expected, comparators={float: lambda a, e: round(a, 2) == round(e, 2)}
)
# case-insensitive comparator by field name
assert_that(order).is_equal_to(
    expected, comparators={"name": lambda a, e: a.lower() == e.lower()}
)
```

Use `comparators` to change *how* a field or type is compared. To drop a field from the comparison
entirely, use `ignore` (above) rather than an always-true comparator (`ignore` also handles fields missing
on one side or with incomparable types).

`ignore_null=True` skips any named field the **expected** side leaves `None`, at any depth - handy for a
partial expected/template. Only the expected side is skipped, so an unexpectedly `None` *actual* field is
still reported (never masked):

<!-- docs-guard: skip -->
```python
# compare only the fields the expected template sets;
# age and address, left None, are ignored
assert_that(user).is_equal_to(User(name="Alice"), ignore_null=True)
```

Sequence elements have no field name, so a `comparators` field-name key does not apply to them (use a type
key or `tolerance`). Sets compare by standard equality.

#### Requiring the same type

Python's `==` compares across types, and a payload keeps that property all the way down. A JSON `true`
read back as a `bool` equals `1`, a `Decimal` from a database column equals an `int`, and neither says a
word:

```python
from decimal import Decimal

assert_that({"active": True}).is_equal_to({"active": 1})  # passes
assert_that({"n": Decimal(1)}).is_equal_to({"n": 1})      # passes
assert_that({"a": {"b": [{"c": True}]}}).is_equal_to({"a": {"b": [{"c": 1}]}})  # passes, three levels down
```

`strict_types=True` requires both sides of every node to be the same type, at any depth:

<!-- docs-guard: skip -->
```python
assert_that({"active": True}).is_equal_to({"active": 1}, strict_types=True)  # fails
```

Because it is opt-in it can afford to be blunt, but the bluntness is worth knowing before you turn it
on. It also rejects pairs some callers read as equal: `IntEnum` against `int`, a `dict` subclass
against `dict`, `float` against `int`.

When several comparison options meet on one leaf, they resolve in a fixed order:

**`ignore_null` &rarr; `comparators` &rarr; identity &rarr; `strict_types` &rarr; `tolerance`.**

It reads as two groups. The first two decide whether the leaf is compared at all (`ignore_null`) and
whether your own code replaces the comparison (`comparators`). The rest then compute equality itself,
from the most decisive test to the most forgiving: the same object, then the same type, then a numeric
allowance. Two consequences follow that are worth saying out loud:

- `tolerance` and `strict_types` only ever combine within one type, `float` against `float`. The
  classic tolerance case, a `Decimal` from a database column against a `float` from JSON, fails on the
  type before the tolerance is consulted.
- a matcher on the expected side is exempt, so composed matchers keep working, and a spec that mixes
  literals with matchers gets strictness on its literal half only.

```python
assert_that({"id": 7}).is_equal_to({"id": match.greater_than(0)}, strict_types=True)
```

Identity sits in that chain because forcing the walk would otherwise take it away. A subnode shared by
both sides is matched by identity and not walked again, exactly as Python does inside a container, so
a config object placed in two expected blocks stays cheap and a container holding the same `NaN` on
both sides keeps comparing equal.

Two limits.

Anything matched **by hash** is outside it, which means dictionary keys and set elements. `1`, `1.0`
and `True` hash alike and compare equal, so the pair is found before anything looks at its type and
the walk never sees it. `{True: "a"}` against `{1: "a"}` and `{1}` against `{1.0}` both pass a strict
comparison. Values, list elements and object fields are all covered normally.

Strictness also turns off the fast path: a container's own `==` says nothing about the types inside
it, so every comparison walks the whole structure in Python. On a list of 20 000 dicts that is about
0.3 ms against 29 ms, which matters only if you are comparing large dumps in a loop.

Inside a [structural spec](matchers.md#structural-matching) the same relation is spelled
`match.equal_to(value, strict_types=True)`, one matcher covering value and type together:

```python
assert_that({"active": True}).matches_structure({"active": match.equal_to(True, strict_types=True)})
```

To assert the type alone, `match.is_type_of()` rejects a subclass where `match.is_instance_of()`
accepts one:

```python
assert_that({"n": 1}).matches_structure({"n": match.is_type_of(int)})         # passes
assert_that({"n": True}).matches_structure({"n": match.is_instance_of(int)})  # passes: bool is an int
```

To negate it, invert the whole assertion with `.not_` rather than looking for the flag on
`is_not_equal_to`, which takes no comparison options:

```python
assert_that({"active": True}).not_.is_equal_to({"active": 1}, strict_types=True)
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

<!-- docs-guard: untyped -->
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

Both operands must agree on awareness.

Comparing a timezone-naive datetime with an aware one raises a `TypeError` rather than answering. The
naive value carries no zone, so there is no instant to compare it by.

This holds for the `ignoring_*` assertions too. They would otherwise compare wall-clock fields and call
two moments hours apart equal.

<!-- docs-guard: skip -->
```python
naive = datetime.datetime(2020, 1, 2, 3, 4, 5)
aware = datetime.datetime(2020, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)

assert_that(naive).is_before(aware)                      # TypeError
assert_that(naive).is_equal_to_ignoring_seconds(aware)   # TypeError
```

Make both aware or both naive first, then the comparison is well defined.

Equality can ignore units of time, and the numeric comparisons work on dates too:

<!-- docs-guard: skip -->
```python
assert_that(today).is_equal_to_ignoring_milliseconds(today_0us)
assert_that(today).is_equal_to_ignoring_seconds(today_0s)
assert_that(today).is_equal_to_ignoring_time(today_0h)

assert_that(middle).is_between(yesterday, today)
# tolerance is a timedelta
assert_that(yesterday).is_close_to(today, datetime.timedelta(hours=24))
```

Date properties can be asserted dynamically with `has_<property>` (see
[dynamic assertions](#dynamic-assertions-on-objects)):

<!-- docs-guard: untyped -->
```python
x = datetime.datetime(1980, 1, 2, 3, 4, 5, 6)
assert_that(x).has_year(1980).has_month(1).has_day(2)
assert_that(x).has_hour(3).has_minute(4).has_second(5).has_microsecond(6)
```

## Files

<!-- docs-guard: skip -->
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

<!-- docs-guard: skip -->
```python
from assertpy2 import assert_that, contents_of

assert_that(contents_of("foo.txt", "ascii")).starts_with("foo").ends_with(
    "bar"
).contains("oob")
```

## Bytes / bytearray

Assertions for `bytes` and `bytearray` values:

```python
assert_that(b"hello world").is_valid_utf8()
assert_that(b"hello").is_valid_encoding("ascii")
assert_that(b"\x89PNG").has_byte_at(0, 0x89)            # IndexError if out of range
assert_that(b"\xab\xcd\xef").is_hex_equal_to("abcdef")
```

`starts_with()`, `ends_with()` and `contains()` handle byte strings themselves, so a prefix, a suffix
and a subsequence read the same way they do for text:

```python
assert_that(b"\x89PNG\r\n\x1a\n").starts_with(b"\x89PNG")
assert_that(b"hello world").ends_with(b"world")
assert_that(b"hello world").contains(b"world")
```

`starts_with_bytes()` and `contains_bytes()` are the bytes-only spellings of the first and the last, kept
for the code that already uses them. They delegate, so all four report the same way.

`decoded_as()` returns a new builder with the decoded string so string assertions can continue
(`UnicodeDecodeError` is raised if decoding fails):

```python
assert_that(b"hello").decoded_as("utf-8").starts_with("hel").is_length(5)
assert_that(b"hello").decoded_as().is_equal_to("hello")  # default encoding utf-8
```

All bytes assertions work with soft assertions, warn mode, and `.not_` negation.

## Objects

<!-- docs-guard: skip -->
```python
fred = Person("Fred", "Smith")

assert_that(fred).is_not_none().is_type_of(Person).is_instance_of(object)
assert_that(fred).is_instance_of_any(Person, dict)
assert_that(Person).is_subclass_of(object)
assert_that(fred).is_same_as(fred)
assert_that(fred.say_hello).is_callable()
assert_that(fred.first_name).is_not_callable()

assert_that(fred.first_name).is_equal_to("Fred")
assert_that(fred.name).is_equal_to("Fred Smith")          # property
assert_that(fred.say_hello()).is_equal_to("Hello, Fred!")  # method
```

### Recursive field assertions

`all_fields_satisfy` walks the whole object graph (mappings, dataclasses, namedtuples, attrs classes,
Pydantic models, lists, tuples) and applies one [matcher](matchers.md) or callable to every scalar leaf, reporting the path
of each leaf that does not satisfy it. `has_no_none_fields` is the common special case:

<!-- docs-guard: skip -->
```python
assert_that({"a": 1, "nested": {"b": 2}}).all_fields_satisfy(match.is_positive())
assert_that([1, [2, 3]]).all_fields_satisfy(lambda x: x > 0)
assert_that({"id": 1, "profile": {"name": "Alice"}}).has_no_none_fields()

assert_that({"a": 1, "b": {"c": -2}}).all_fields_satisfy(match.is_positive())  # fails
# Expected all fields to satisfy a positive value, but 1 field did not.
#   b.c: expected a positive value, but was -2
```

Scalars, strings and sets are treated as single leaves (use `each` / `all_satisfy` for element-wise set
checks), and circular references are reported once rather than recursed into.

### Extracting attributes from objects

Flatten a collection of objects on an attribute, property, or zero-argument method with `extracting`:

<!-- docs-guard: skip -->
```python
people = [Person("Fred", "Smith"), Person("Bob", "Barr")]

assert_that(people).extracting("first_name").contains("Fred", "Bob")
assert_that(people).extracting("first_name", "last_name").contains(
    ("Fred", "Smith"), ("Bob", "Barr")
)
# property
assert_that(people).extracting("name").contains("Fred Smith", "Bob Barr")
# zero-argument method
assert_that(people).extracting("say_hello").contains("Hello, Fred!", "Hello, Bob!")
```

It also works on collections of dicts (extracting by key), Pydantic models, and across subclasses in a mixed collection.

#### Filtering

`filter` keeps only items for which it is truthy. It may be a key/attribute name, a dict of
key-value pairs that must all match, or a predicate:

```python
users = [
    {"user": "Fred", "active": True, "age": 25},
    {"user": "Johnny", "active": True, "age": 18},
    {"user": "Bob", "active": False, "age": 30},
]

assert_that(users).extracting("user", filter="active").is_equal_to(["Fred", "Johnny"])
assert_that(users).extracting("user", filter={"active": False}).is_equal_to(["Bob"])
assert_that(users).extracting("user", filter=lambda x: x["age"] > 20).is_equal_to(
    ["Fred", "Bob"]
)
```

#### Sorting

`sort` orders the extracted items. It may be a key/attribute name, an iterable of names (tie-breaking
left to right), or a key function. `None` means no ordering. Anything else is a mistake and raises a
`TypeError`, rather than quietly handing back unsorted items for a later assertion to trip over:

<!-- docs-guard: skip -->
```python
assert_that(users).extracting("user", sort="age").is_equal_to(["Johnny", "Fred", "Bob"])
assert_that(users).extracting("user", sort=["active", "age"]).is_equal_to(
    ["Bob", "Johnny", "Fred"]
)
assert_that(users).extracting("user", sort=lambda x: -x["age"]).is_equal_to(
    ["Bob", "Fred", "Johnny"]
)
```

### Dynamic assertions on objects

`assertpy2` exposes `has_<name>()` for any attribute, property, or zero-argument method on the value,
so attribute checks stay compact:

<!-- docs-guard: skip -->
```python
fred = Person("Fred", "Smith")

assert_that(fred).has_first_name("Fred")     # attribute
assert_that(fred).has_name("Fred Smith")     # property
assert_that(fred).has_say_hello("Hello, Fred!")  # zero-arg method
```

Dynamic assertions also work on dicts, keyed by entry name:

<!-- docs-guard: untyped -->
```python
assert_that(
    {"first_name": "Fred", "last_name": "Smith"}
).has_first_name("Fred").has_last_name("Smith")
```

## Exceptions

Exception and warning assertions wrap a *callable* rather than a value: you assert on what calling the
function does, then chain assertions on the resulting message.

<!-- docs-guard: skip -->
```python
assert_that(some_func).raises(RuntimeError).when_called_with("foo")
assert_that(deprecated_func).warns(DeprecationWarning).when_called_with("foo")
```

See [Errors & Reporting](errors.md) for the full set:

- [expected exceptions](errors.md#expected-exceptions) and [warnings](errors.md#expected-warnings)
- the cause chain (`caused_by()`, `has_root_cause()`) and exception groups (`contains_error()`,
  `does_not_contain_error()`, `errors()`, `error_of()`)
- pivoting to the raised exception (`raised()`) or the call's return value (`returned()`).
