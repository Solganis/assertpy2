# API Reference

Full API reference for assertpy2. For a quick overview, see the [README](../README.md).

## Migration from assertpy

assertpy2 is a drop-in replacement for Python 3.10+. Change the import, everything else works:

```py
# before
from assertpy import assert_that, soft_assertions

# after
from assertpy2 import assert_that, soft_assertions
```

## Comparison

|  | pytest assert | PyHamcrest | assertpy | **assertpy2** |
|---|:---:|:---:|:---:|:---:|
| **Type safety** | Partial (mypy plugin) | No | No | **py.typed, @overload, Self** |
| **IDE autocomplete** | Generic | Generic | Generic | **Filtered by type** |
| **Fluent chaining** | No | No | Yes | **Yes** |
| **Composable matchers** | No | Yes (functions) | No | **Yes (`&` `\|` `~` operators)** |
| **Structural matching** | No | Flat (has_entries) | No | **Recursive with matchers** |
| **Async assertions** | No | No | No | **eventually() with polling** |
| **Soft assertions** | No | No | Yes (not thread-safe) | **Yes (thread-safe, async-safe)** |
| **Structured errors** | Rewrite only | Mismatch string | String only | **.actual .expected .diff** |
| **Maintained** | Built-in | Minimal | 2020 | **Active** |

## Table of contents

**Built-in Types**

- [Strings](#strings)
- [Numbers](#numbers)
- [Lists](#lists)
- [Tuples](#tuples)
- [Dicts](#dicts)
- [Sets](#sets)
- [Booleans](#booleans)
- [None](#none)
- [Dates](#dates)
- [Files](#files)
- [Bytes / Bytearray](#bytes--bytearray-assertions)
- [Objects](#objects), [Extracting](#extracting-attributes-from-objects), [Dynamic](#dynamic-assertions-on-objects)

**Fluent API**

- [Chaining](#chaining)
- [Universal Negation](#universal-negation)
- [Collection Pipeline](#collection-pipeline)

**Matchers**

- [Composable Matchers](#composable-matchers)
- [Structural Matching](#structural-matching)
- [Custom Matchers](#custom-matchers---registering-domain-matchers)

**Data Navigation**

- [JSON Path / Schema Validation](#json-path--schema-validation)
- [Regex Group Extraction](#regex-group-extraction)

**Testing**

- [Soft Assertions](#soft-assertions)
- [Grouped Soft Assertions](#grouped-soft-assertions)
- [Async Assertions](#async-assertions)
- [Structured Errors](#structured-errors)
- [Rich Pytest Diffs](#rich-pytest-diffs)
- [Snapshot Testing](#snapshot-testing)

**Error Handling**

- [Failure](#failure), [Expected Exceptions](#expected-exceptions), [Custom Error Messages](#custom-error-messages), [Warnings](#just-a-warning)

**Extensibility**

- [Extension System](#extension-system---adding-custom-assertions)

**Integrations**

- [Allure Integration](#allure-integration)
- [Behave Step Matchers](#behave-step-matchers)


[Back to top](#table-of-contents)

## Strings

Matching strings:

```py
assert_that('').is_not_none()
assert_that('').is_empty()
assert_that('').is_false()
assert_that('').is_type_of(str)
assert_that('').is_instance_of(str)

assert_that('foo').is_length(3)
assert_that('foo').is_not_empty()
assert_that('foo').is_true()
assert_that('foo').is_alpha()
assert_that('123').is_digit()
assert_that('foo').is_lower()
assert_that('FOO').is_upper()
assert_that('foo').is_iterable()
assert_that('foo').is_equal_to('foo')
assert_that('foo').is_not_equal_to('bar')
assert_that('foo').is_equal_to_ignoring_case('FOO')

assert_that('foo').is_unicode()
assert_that('foo123').is_alphanumeric()
assert_that('   ').is_whitespace()

assert_that('foo').contains('f')
assert_that('foo').contains('f','oo')
assert_that('foo').contains_ignoring_case('F','oO')
assert_that('foo').does_not_contain('x')
assert_that('foo').contains_only('f','o')
assert_that('foo').contains_sequence('o','o')
assert_that('foobar').contains_any_of('foo', 'xyz')
assert_that('foobar').contains_none_of('xyz', 'abc')

assert_that('foo').contains_duplicates()
assert_that('fox').does_not_contain_duplicates()

assert_that('foo').is_in('foo','bar','baz')
assert_that('foo').is_not_in('boo','bar','baz')
assert_that('foo').is_subset_of('abcdefghijklmnopqrstuvwxyz')

assert_that('foo').starts_with('f')
assert_that('foo').ends_with('oo')

assert_that('foo').matches(r'\w')
assert_that('123-456-7890').matches(r'\d{3}-\d{3}-\d{4}')
assert_that('foo').does_not_match(r'\d+')
```

Regular expressions can be tricky.  Be sure to use raw strings (prefix the pattern string with `r`) for the regex pattern to be matched.  Also, note that the `matches()` function passes for partial matches (as does the [re.match](https://docs.python.org/3/library/re.html#re.match) function that underlies it). If you want to match the entire string, just include anchors in the regex pattern.

```py
# partial matches, these all pass
assert_that('foo').matches(r'\w')
assert_that('foo').matches(r'oo')
assert_that('foo').matches(r'\w{2}')

# match the entire string with an anchored regex pattern, passes
assert_that('foo').matches(r'^\w{3}$')

# fails
assert_that('foo').matches(r'^\w{2}$')
```

Additionally, while `assertpy2` `matches()` assertion does not have support for [re.match](https://docs.python.org/3/library/re.html#re.match) flags such as `re.MULTILINE` or `re.DOTALL`, it works as expected with _inline flags_ in the pattern.

```py
s = """bar
foo
baz"""

# use multiline inline flag (?m)
assert_that(s).matches(r'(?m)^foo$')

# use dotall inline flag (?s)
assert_that(s).matches(r'(?s)b(.*)z')
```

[Back to top](#table-of-contents)

## Numbers

Matching integers:

```py
assert_that(0).is_not_none()
assert_that(0).is_false()
assert_that(0).is_type_of(int)
assert_that(0).is_instance_of(int)

assert_that(0).is_zero()
assert_that(1).is_not_zero()
assert_that(1).is_positive()
assert_that(-1).is_negative()
assert_that(4).is_even()
assert_that(3).is_odd()
assert_that(9).is_divisible_by(3)

assert_that(123).is_equal_to(123)
assert_that(123).is_not_equal_to(456)

assert_that(123).is_greater_than(100)
assert_that(123).is_greater_than_or_equal_to(123)
assert_that(123).is_less_than(200)
assert_that(123).is_less_than_or_equal_to(200)
assert_that(123).is_between(100, 200)
assert_that(123).is_close_to(100, 25)

assert_that(1).is_in(0,1,2,3)
assert_that(1).is_not_in(-1,-2,-3)
```

Matching floats:

```py
assert_that(0.0).is_not_none()
assert_that(0.0).is_false()
assert_that(0.0).is_type_of(float)
assert_that(0.0).is_instance_of(float)

assert_that(123.4).is_equal_to(123.4)
assert_that(123.4).is_not_equal_to(456.7)

assert_that(123.4).is_greater_than(100.1)
assert_that(123.4).is_greater_than_or_equal_to(123.4)
assert_that(123.4).is_less_than(200.2)
assert_that(123.4).is_less_than_or_equal_to(123.4)
assert_that(123.4).is_between(100.1, 200.2)
assert_that(123.4).is_close_to(123, 0.5)

assert_that(float('NaN')).is_nan()
assert_that(123.4).is_not_nan()
assert_that(float('Inf')).is_inf()
assert_that(123.4).is_not_inf()
```

Of course, using `is_equal_to()` with a `float` value is just asking for trouble. You'll always want to use the assertions methods like `is_close_to()` and `is_between()`.


[Back to top](#table-of-contents)

## Lists

Matching lists:

```py
assert_that([]).is_not_none()
assert_that([]).is_empty()
assert_that([]).is_false()
assert_that([]).is_type_of(list)
assert_that([]).is_instance_of(list)
assert_that([]).is_iterable()

assert_that(['a','b']).is_length(2)
assert_that(['a','b']).is_not_empty()
assert_that(['a','b']).is_equal_to(['a','b'])
assert_that(['a','b']).is_not_equal_to(['b','a'])

assert_that(['a','b']).contains('a')
assert_that(['a','b']).contains('b','a')
assert_that(['a','b']).does_not_contain('x','y')
assert_that(['a','b']).contains_only('a','b')
assert_that(['a','a']).contains_only('a')
assert_that(['a','b','c']).contains_sequence('b','c')
assert_that(['a','b','c']).contains_exactly('a','b','c')
assert_that(['a','x','b','y','c']).contains_in_order('a','b','c')
assert_that(['a','b']).is_subset_of(['a','b','c'])
assert_that(['a','b','c']).is_sorted()
assert_that(['c','b','a']).is_sorted(reverse=True)

assert_that(['a','x','x']).contains_duplicates()
assert_that(['a','b','c']).does_not_contain_duplicates()

assert_that(['a','b','c']).starts_with('a')
assert_that(['a','b','c']).ends_with('c')

assert_that([1, -2, 3]).any_satisfy(lambda x: x < 0)
assert_that([1, 2, 3]).all_satisfy(lambda x: x > 0)
assert_that([1, 2, 3]).none_satisfy(lambda x: x < 0)
```

`any_satisfy`, `all_satisfy`, and `none_satisfy` accept both callables and [composable matchers](#composable-matchers).

### List Flattening

Lists of lists can be flattened on any item (by index) using the `extracting` helper (see [dict flattening](#dict-flattening)):

```py
people = [['Fred', 'Smith'], ['Bob', 'Barr']]
assert_that(people).extracting(0).is_equal_to(['Fred','Bob'])
assert_that(people).extracting(-1).is_equal_to(['Smith','Barr'])
```

[Back to top](#table-of-contents)

## Tuples

Matching tuples:

```py
assert_that(()).is_not_none()
assert_that(()).is_empty()
assert_that(()).is_false()
assert_that(()).is_type_of(tuple)
assert_that(()).is_instance_of(tuple)
assert_that(()).is_iterable()

assert_that((1,2,3)).is_length(3)
assert_that((1,2,3)).is_not_empty()
assert_that((1,2,3)).is_equal_to((1,2,3))
assert_that((1,2,3)).is_not_equal_to((1,2,4))

assert_that((1,2,3)).contains(1)
assert_that((1,2,3)).contains(3,2,1)
assert_that((1,2,3)).does_not_contain(4,5,6)
assert_that((1,2,3)).contains_only(1,2,3)
assert_that((1,1,1)).contains_only(1)
assert_that((1,2,3)).contains_sequence(2,3)
assert_that((1,2,3)).contains_exactly(1,2,3)
assert_that((1,5,2,8,3)).contains_in_order(1,2,3)
assert_that((1,2,3)).is_subset_of((1,2,3,4))
assert_that((1,2,3)).is_sorted()
assert_that((3,2,1)).is_sorted(reverse=True)

assert_that((1,2,2)).contains_duplicates()
assert_that((1,2,3)).does_not_contain_duplicates()

assert_that((1,2,3)).starts_with(1)
assert_that((1,2,3)).ends_with(3)
```

### Tuple Flattening

Tuples of tuples can be flattened on any item (by index) using the `extracting` helper (see [dict flattening](#dict-flattening)):

```py
points = ((1,2,3),(4,5,6))
assert_that(points).extracting(0).is_equal_to([1, 4])
assert_that(points).extracting(-1).is_equal_to([3, 6])
```

[Back to top](#table-of-contents)

## Dicts

Matching dicts:

```py
assert_that({}).is_not_none()
assert_that({}).is_empty()
assert_that({}).is_false()
assert_that({}).is_type_of(dict)
assert_that({}).is_instance_of(dict)

assert_that({'a':1,'b':2}).is_length(2)
assert_that({'a':1,'b':2}).is_not_empty()
assert_that({'a':1,'b':2}).is_equal_to({'a':1,'b':2})
assert_that({'a':1,'b':2}).is_equal_to({'b':2,'a':1})
assert_that({'a':1,'b':2}).is_not_equal_to({'a':1,'b':3})

assert_that({'a':1,'b':2}).contains('a')
assert_that({'a':1,'b':2}).contains('b','a')
assert_that({'a':1,'b':2}).does_not_contain('x')
assert_that({'a':1,'b':2}).does_not_contain('x','y')
assert_that({'a':1,'b':2}).contains_only('a','b')
assert_that({'a':1,'b':2}).is_subset_of({'a':1,'b':2,'c':3})

# contains_key() is just an alias for contains()
assert_that({'a':1,'b':2}).contains_key('a')
assert_that({'a':1,'b':2}).contains_key('b','a')

# does_not_contain_key() is just an alias for does_not_contain()
assert_that({'a':1,'b':2}).does_not_contain_key('x')
assert_that({'a':1,'b':2}).does_not_contain_key('x','y')

assert_that({'a':1,'b':2}).contains_value(1)
assert_that({'a':1,'b':2}).contains_value(2,1)
assert_that({'a':1,'b':2}).does_not_contain_value(3)
assert_that({'a':1,'b':2}).does_not_contain_value(3,4)

assert_that({'a':1,'b':2}).contains_entry({'a':1})
assert_that({'a':1,'b':2}).contains_entry({'a':1},{'b':2})
assert_that({'a':1,'b':2}).does_not_contain_entry({'a':2})
assert_that({'a':1,'b':2}).does_not_contain_entry({'a':2},{'b':1})
```

### Comparison with ignore/include

Keys or fields can optionally be ignored or included when using the `is_equal_to()` assertion. This works with dicts, dataclasses, namedtuples, Pydantic models, attrs, and plain objects. For sequences, each element is compared pairwise with the same filters applied.

Ignore keys or fields with the `ignore` keyword argument:

```py
# ignore a single key
assert_that({'a':1,'b':2}).is_equal_to({'a':1}, ignore='b')

# ignore multiple keys using a list
assert_that({'a':1,'b':2,'c':3}).is_equal_to({'a':1}, ignore=['b','c'])

# ignore nested keys using a tuple
assert_that({'a':1,'b':{'c':2,'d':3}}).is_equal_to({'a':1,'b':{'c':2}}, ignore=('b','d'))
```

Or include specific keys or fields with the `include` keyword argument:

```py
# include a single key
assert_that({'a':1,'b':2}).is_equal_to({'a':1}, include='a')

# include multiple keys using a list
assert_that({'a':1,'b':2,'c':3}).is_equal_to({'a':1,'b':2}, include=['a','b'])

# include nested keys using a tuple
assert_that({'a':1,'b':{'c':2,'d':3}}).is_equal_to({'b':{'d':3}}, include=('b','d'))
```

Or do both:

```py
assert_that({'a':1,'b':{'c':2,'d':3,'e':4,'f':5}}).is_equal_to(
    {'b':{'d':3,'f':5}},
    ignore=[('b','c'),('b','e')],
    include='b'
)
```

Works with dataclasses, Pydantic models, and any object with introspectable fields:

```py
@dataclass
class User:
    id: int
    name: str
    email: str

# ignore a field
assert_that(User(1, "Alice", "a@x.com")).is_equal_to(User(99, "Alice", "a@x.com"), ignore="id")

# compare lists of objects pairwise
actual = [User(1, "Alice", "a@x.com"), User(2, "Bob", "b@x.com")]
expected = [User(99, "Alice", "a@x.com"), User(99, "Bob", "b@x.com")]
assert_that(actual).is_equal_to(expected, ignore="id")
```

### Dict Flattening

Lists of dicts can be flattened on key using the `extracting` helper (see [extracting attributes](#extracting-attributes-from-objects)):

```py
fred = {'first_name': 'Fred', 'last_name': 'Smith'}
bob = {'first_name': 'Bob', 'last_name': 'Barr'}
people = [fred, bob]

assert_that(people).extracting('first_name').is_equal_to(['Fred','Bob'])
assert_that(people).extracting('first_name').contains('Fred','Bob')
```

### Dict Key Assertions

Fluent assertions against the value of a given key can be done by prepending `has_` to the key name (see [dynamic assertions](#dynamic-assertions-on-objects)):

```py
fred = {'first_name': 'Fred', 'last_name': 'Smith', 'shoe_size': 12}

assert_that(fred).has_first_name('Fred')
assert_that(fred).has_last_name('Smith')
assert_that(fred).has_shoe_size(12)
```


[Back to top](#table-of-contents)

## Sets

Matching sets:

```py
assert_that(set([])).is_not_none()
assert_that(set([])).is_empty()
assert_that(set([])).is_false()
assert_that(set([])).is_type_of(set)
assert_that(set([])).is_instance_of(set)

assert_that(set(['a','b'])).is_length(2)
assert_that(set(['a','b'])).is_not_empty()
assert_that(set(['a','b'])).is_equal_to(set(['a','b']))
assert_that(set(['a','b'])).is_equal_to(set(['b','a']))
assert_that(set(['a','b'])).is_not_equal_to(set(['a','x']))

assert_that(set(['a','b'])).contains('a')
assert_that(set(['a','b'])).contains('b','a')
assert_that(set(['a','b'])).does_not_contain('x','y')
assert_that(set(['a','b'])).contains_only('a','b')
assert_that(set(['a','b'])).is_subset_of(set(['a','b','c']))
assert_that(set(['a','b'])).is_subset_of(set(['a']), set(['b']))
```


[Back to top](#table-of-contents)

## Booleans

Matching booleans:

```py
assert_that(True).is_true()
assert_that(False).is_false()
assert_that(True).is_type_of(bool)
```


[Back to top](#table-of-contents)

## None

Matching `None`:

```py
assert_that(None).is_none()
assert_that('').is_not_none()
assert_that(None).is_type_of(type(None))
```


[Back to top](#table-of-contents)

## Dates

Matching dates:

```py
import datetime

today = datetime.datetime.today()
yesterday = today - datetime.timedelta(days=1)

assert_that(yesterday).is_before(today)
assert_that(today).is_after(yesterday)
assert_that(yesterday).is_before_or_equal_to(today)
assert_that(today).is_before_or_equal_to(today)
assert_that(today).is_after_or_equal_to(yesterday)
assert_that(today).is_after_or_equal_to(today)
```

You can also make assertions about date equality (ignoring various units of time) like this:

```py
today_0us = today - datetime.timedelta(microseconds=today.microsecond)
today_0s = today - datetime.timedelta(seconds=today.second)
today_0h = today - datetime.timedelta(hours=today.hour)

assert_that(today).is_equal_to_ignoring_milliseconds(today_0us)
assert_that(today).is_equal_to_ignoring_seconds(today_0s)
assert_that(today).is_equal_to_ignoring_time(today_0h)
assert_that(today).is_equal_to(today)
```

You can use these numeric assertions on dates:

```py
middle = today - datetime.timedelta(hours=12)
hours_24 = datetime.timedelta(hours=24)

assert_that(today).is_greater_than(yesterday)
assert_that(yesterday).is_less_than(today)
assert_that(middle).is_between(yesterday, today)

#note that the tolerance must be a datetime.timedelta object
assert_that(yesterday).is_close_to(today, hours_24)
```

Lastly, because datetime is an object we can easily test the properties of a given date by prepending `has_` to the property name (see [dynamic assertions](#dynamic-assertions-on-objects)):

```py
# 1980-01-02 03:04:05.000006
x = datetime.datetime(1980, 1, 2, 3, 4, 5, 6)

assert_that(x).has_year(1980)
assert_that(x).has_month(1)
assert_that(x).has_day(2)
assert_that(x).has_hour(3)
assert_that(x).has_minute(4)
assert_that(x).has_second(5)
assert_that(x).has_microsecond(6)
```

Currently, `assertpy2` only supports dates via the `datetime` type.


[Back to top](#table-of-contents)

## Files

Matching files:

```py
assert_that('foo.txt').exists()
assert_that('missing.txt').does_not_exist()
assert_that('foo.txt').is_file()

assert_that('mydir').exists()
assert_that('missing_dir').does_not_exist()
assert_that('mydir').is_directory()

assert_that('foo.txt').is_named('foo.txt')
assert_that('foo.txt').is_child_of('mydir')

assert_that('foo.txt').is_readable()
assert_that('foo.txt').is_writable()
assert_that('/usr/bin/python').is_executable()
```

Matching file contents is done using the `contents_of()` helper to read the file into a string with the given encoding (if no encoding is given it defaults to `utf-8`).  Once the file is read into a string, you can make quick work of it using the `assertpy2` string assertions like this:

```py
from assertpy2 import assert_that, contents_of

contents = contents_of('foo.txt', 'ascii')
assert_that(contents).starts_with('foo').ends_with('bar').contains('oob')
```


[Back to top](#table-of-contents)

## Bytes / Bytearray Assertions

Assertions for `bytes` and `bytearray` values. The `assert_that()` overload returns a type-specific protocol with these methods.

### is_valid_utf8

Assert that the value is valid UTF-8:

```py
assert_that(b"hello world").is_valid_utf8()
assert_that(b"\xff\xfe").is_valid_utf8()  # fails
```

### is_valid_encoding

Assert that the value is valid in the given encoding:

```py
assert_that(b"hello").is_valid_encoding("ascii")
assert_that("привет".encode()).is_valid_encoding("utf-8")
assert_that(b"\x80\x81").is_valid_encoding("ascii")  # fails
```

### starts_with_bytes

Assert that the value starts with the given byte prefix:

```py
assert_that(b"\x89PNG\r\n\x1a\n...").starts_with_bytes(b"\x89PNG")
```

### contains_bytes

Assert that the value contains the given byte subsequence:

```py
assert_that(b"hello world").contains_bytes(b"world")
assert_that(b"\x00\x01\x02\x03").contains_bytes(b"\x01\x02")
```

### has_byte_at

Assert that the byte at the given index equals the expected value:

```py
assert_that(b"\x89PNG").has_byte_at(0, 0x89)
assert_that(b"\x89PNG").has_byte_at(1, ord("P"))
```

Raises `IndexError` if the index is out of range.

### is_hex_equal_to

Assert that the value equals the given hex string:

```py
assert_that(b"\xab\xcd\xef").is_hex_equal_to("abcdef")
assert_that(b"\x00\x01").is_hex_equal_to("0001")
```

### decoded_as

Decode the value and return a new builder with the decoded string, allowing string assertions to continue:

```py
assert_that(b"hello").decoded_as("utf-8").starts_with("hel").is_length(5)
assert_that(b"hello").decoded_as().is_equal_to("hello")  # default encoding is utf-8
```

Raises `UnicodeDecodeError` if decoding fails.

All bytes assertions work with soft assertions, warn mode, and `.not_` negation:

```py
with soft_assertions():
    assert_that(data).is_valid_utf8()
    assert_that(data).starts_with_bytes(b"\x89PNG")

assert_that(b"\xff\xfe").not_.is_valid_utf8()
```

[Back to top](#table-of-contents)

## Objects

Matching an object:

```py
fred = Person('Fred','Smith')

assert_that(fred).is_not_none()
assert_that(fred).is_true()
assert_that(fred).is_type_of(Person)
assert_that(fred).is_instance_of(object)
assert_that(fred).is_same_as(fred)
assert_that(fred.say_hello).is_callable()
assert_that(fred.first_name).is_not_callable()
```

Matching an attribute, a property, and a method:

```py
assert_that(fred.first_name).is_equal_to('Fred')
assert_that(fred.name).is_equal_to('Fred Smith')
assert_that(fred.say_hello()).is_equal_to('Hello, Fred!')
```

Given `fred` is an instance of the following `Person` class:

```py
class Person(object):
    def __init__(self, first_name, last_name):
        self.first_name = first_name
        self.last_name = last_name

    @property
    def name(self):
        return f'{self.first_name} {self.last_name}'

    def say_hello(self):
        return f'Hello, {self.first_name}!'
```


### Extracting Attributes from Objects

It is frequently necessary to test collections of objects.  The `assertpy2` library includes an `extracting` helper to flatten the collection on a given attribute, like this:

```py
fred = Person('Fred','Smith')
bob = Person('Bob','Barr')
people = [fred, bob]

assert_that(people).extracting('first_name').is_equal_to(['Fred','Bob'])
assert_that(people).extracting('first_name').contains('Fred','Bob')
assert_that(people).extracting('first_name').does_not_contain('Charlie')
```

Of course `extracting` works with subclasses too...suppose we create a simple class hierarchy by creating a `Developer` subclass of `Person`, like this:

```py
class Developer(Person):
    def say_hello(self):
        return f'{self.first_name} writes code.'
```

Testing a mixed collection of parent and child objects works as expected:

```py
fred = Person('Fred','Smith')
joe = Developer('Joe','Coder')
people = [fred, joe]

assert_that(people).extracting('first_name').contains('Fred','Joe')
```

Additionally, the `extracting` helper can accept a list of attributes to be extracted, and will flatten them into a list of tuples:

```py
assert_that(people).extracting('first_name', 'last_name').contains(('Fred','Smith'), ('Joe','Coder'))
```

Lastly, `extracting` works on not just class attributes, but also properties, and even zero-argument methods:

```py
assert_that(people).extracting('name').contains('Fred Smith', 'Joe Coder')
assert_that(people).extracting('say_hello').contains('Hello, Fred!', 'Joe writes code.')
```

As noted above, the `extracting` helper also works on a collection of dicts:

```py
fred = {'first_name': 'Fred', 'last_name': 'Smith'}
bob = {'first_name': 'Bob', 'last_name': 'Barr'}
people = [fred, bob]

assert_that(people).extracting('first_name').contains('Fred','Bob')
```

#### Extracting and Filtering

The `extracting` helper can include a `filter` to keep only those items for which the given `filter` is truthy.  For example, suppose we have the following list of dicts we wish to test:

```py
users = [
    {'user': 'Fred', 'age': 36, 'active': True},
    {'user': 'Bob', 'age': 40, 'active': False},
    {'user': 'Johnny', 'age': 13, 'active': True}
]
```

The `filter` can be the name of a key (or attribute, or property, or zero-argument method) and the extracted items are kept if the corresponding value is truthy:

```py
assert_that(users).extracting('user', filter='active')\
    .is_equal_to(['Fred','Johnny'])
```

The `filter` can be a `dict`-like object and the extracted items are kept if *all* corresponding key-value pairs are equal:

```py
assert_that(users).extracting('user', filter={'active': False})\
    .is_equal_to(['Bob'])
assert_that(users).extracting('user', filter={'age': 36, 'active': True})\
    .is_equal_to(['Fred'])
```

The `filter` can be any function (including an in-line `lambda`) that accepts as its single argument each item in the collection and the extracted items are kept if the function evaluates to `True`:

```py
assert_that(users).extracting('user', filter=lambda x: x['age'] > 20)\
    .is_equal_to(['Fred', 'Bob'])
```

#### Extracting and Sorting

The `extracting` helper can include a `sort` to enforce order on the extracted items.

The `sort` can be the name of a key (or attribute, or property, or zero-argument method) and the extracted items are ordered by the corresponding values:

```py
assert_that(users).extracting('user', sort='age').is_equal_to(['Johnny','Fred','Bob'])
```

The `sort` can be an `iterable` of names and the extracted items are ordered by corresponding value of the first name, ties are broken by the corresponding values of the second name, and so on:

```py
assert_that(users).extracting('user', sort=['active','age']).is_equal_to(['Bob','Johnny','Fred'])
```

The `sort` can be any function (including an in-line `lambda`) that accepts as its single argument each item in the collection and the extracted items are ordered by the corresponding function return values:

```py
assert_that(users).extracting('user', sort=lambda x: -x['age'])\
    .is_equal_to(['Bob','Fred','Johnny'])
```

### Dynamic Assertions on Objects

When testing attributes of an object, the basic `assertpy2` assertions can get a little verbose like this:

```py
fred = Person('Fred','Smith')

assert_that(fred.first_name).is_equal_to('Fred')
assert_that(fred.name).is_equal_to('Fred Smith')
assert_that(fred.say_hello()).is_equal_to('Hello, Fred!')
```

So, `assertpy2` takes advantage of the awesome dyanmism in the Python runtime to provide dynamic assertions in the form of `has_<name>()` where `<name>` is the name of any attribute, property, or zero-argument method on the given object.

Using dynamic assertions, we can rewrite the above assertions in a more compact and readable way like this:

```py
assert_that(fred).has_first_name('Fred')
assert_that(fred).has_name('Fred Smith')
assert_that(fred).has_say_hello('Hello, Fred!')
```

Since `fred` has the attribute `first_name`, the dynamic assertion method `has_first_name()` is available.
Similarly, the property `name` can be tested via `has_name()` and the zero-argument method `say_hello()` via
the `has_say_hello()` assertion.

As noted above, dynamic assertions also work on dicts:

```py
fred = {'first_name': 'Fred', 'last_name': 'Smith'}

assert_that(fred).has_first_name('Fred')
assert_that(fred).has_last_name('Smith')
```

[Back to top](#table-of-contents)

---

## Chaining

One of the nicest aspects of any fluent API is the ability to chain methods together.  In the case of `assertpy2`, chaining
allows you to write assertions as a single statement that reads like a sentence and is easy to understand.

Here are just a few examples:

```py
assert_that('foo').is_length(3).starts_with('f').ends_with('oo')

assert_that([1,2,3]).is_type_of(list).contains(1,2).does_not_contain(4,5)

assert_that(fred).has_first_name('Fred').has_last_name('Smith').has_shoe_size(12)

assert_that(people).is_length(2).extracting('first_name').contains('Fred','Joe')
```

[Back to top](#table-of-contents)

## Universal Negation

The `.not_` property inverts the next assertion in the chain. Instead of writing separate `is_not_*` methods, use `.not_` with any existing assertion:

```py
assert_that(5).not_.is_none()
assert_that("abc123").not_.is_alpha()
assert_that([3, 1, 2]).not_.is_sorted()
assert_that(42).not_.is_in(1, 2, 3)
assert_that("hello").not_.is_instance_of(int)
```

Chaining continues normally after a negated assertion:

```py
assert_that(5).not_.is_none().is_positive()
assert_that("hello").not_.is_empty().is_length(5).is_alpha()
```

Works with `described_as()`, the description is included in the error message:

```py
assert_that(5).described_as("my check").not_.is_positive()
# AssertionError: [my check] Expected <5> to NOT satisfy: is_positive()
```

Works with soft assertions, collecting errors instead of raising:

```py
with soft_assertions():
    assert_that(5).not_.is_positive()    # collected, not raised
    assert_that(None).not_.is_none()     # collected, not raised
```

Works with warn mode, logging instead of raising:

```py
assert_warn("hello").not_.is_alpha()  # logs warning
```

Works with matchers:

```py
assert_that(-5).not_.satisfies(match.is_positive())
assert_that([1, -2, 3]).not_.each(match.is_positive())
```

[Back to top](#table-of-contents)

## Collection Pipeline

Pipeline methods transform the value before asserting. Each returns a new builder, so the original value is unchanged.

### `filtered_on(predicate)`

Filter elements by a callable or Matcher:

```py
assert_that([1, -2, 3, -4]).filtered_on(lambda x: x > 0).is_length(2)
assert_that(items).filtered_on(match.is_positive()).is_not_empty()
assert_that(users).filtered_on(match.has_property("active")).is_length(5)
```

### `mapped(func)`

Transform each element:

```py
assert_that(["a", "b", "c"]).mapped(str.upper).contains("A", "B")
assert_that(users).mapped(lambda u: u.name).contains("Alice", "Bob")
```

### `flat_mapped(func)`

Transform and flatten:

```py
assert_that(["ab", "cd"]).flat_mapped(list).contains("a", "b", "c", "d")
assert_that(users).flat_mapped(lambda u: u.tags).contains("admin", "user")
```

### `first()` / `last()`

Navigate to first or last element:

```py
assert_that([10, 20, 30]).first().is_equal_to(10)
assert_that([10, 20, 30]).last().is_equal_to(30)
```

Raises `ValueError` if the collection is empty.

### `element(index)`

Navigate to element at a specific index:

```py
assert_that([10, 20, 30]).element(1).is_equal_to(20)
```

Raises `IndexError` if the index is out of range.

### `single()`

Assert exactly one element and navigate to it:

```py
assert_that([42]).single().is_equal_to(42)
```

Raises `ValueError` if the collection is empty or has more than one element.

### Chaining pipeline steps

Pipeline methods return a new builder, so they can be chained with each other and with any assertion:

```py
assert_that(orders).filtered_on(lambda o: o.status == "FAILED").mapped(lambda o: o.total).first().is_positive()
assert_that(items).filtered_on(match.is_positive()).not_.is_empty()
```

[Back to top](#table-of-contents)

---

## Composable Matchers

Matchers are reusable condition objects that can be composed with `&` (and), `|` (or), `~` (not) operators. Import the `match` namespace to access all built-in matchers:

```py
from assertpy2 import assert_that, match
```

### Using satisfies()

Test a value against a matcher or composed matcher:

```py
assert_that(42).satisfies(match.greater_than(0))
assert_that(42).satisfies(match.greater_than(0) & match.less_than(100))
assert_that("hello").satisfies(~match.equal_to("world"))
assert_that(150).satisfies(match.is_negative() | match.greater_than(100))
```

### Using each()

Check that every element in a collection satisfies a matcher:

```py
assert_that([18, 25, 30]).each(match.between(18, 120))
assert_that(["a", "bb", "ccc"]).each(match.is_instance_of(str))
```

`each()` also accepts a plain callable (predicate):

```py
assert_that([2, 4, 6]).each(lambda x: x % 2 == 0)
```

### Matchers inside contains()

When a `Matcher` object is passed to `contains()`, each element in the collection is tested against it:

```py
assert_that([3, 7, 12]).contains(match.greater_than(10))
assert_that(["foo", "bar"]).contains(match.matches_regex(r"^f"))
```

### Composing matchers

Matchers support Python operators for composition:

```py
# all conditions must match (AND)
positive_and_small = match.is_positive() & match.less_than(10)
assert_that(5).satisfies(positive_and_small)

# at least one condition must match (OR)
extreme = match.less_than(-100) | match.greater_than(100)
assert_that(200).satisfies(extreme)

# invert a condition (NOT)
not_empty = ~match.is_empty()
assert_that([1, 2]).satisfies(not_empty)

# nested composition
complex_check = (match.greater_than(0) & match.less_than(100)) | match.equal_to(-1)
assert_that(50).satisfies(complex_check)
assert_that(-1).satisfies(complex_check)
```

### Using matchers with `==`

Matchers implement `__eq__`, so they work with plain `assert` and pytest introspection. No `assert_that()` wrapper needed:

```py
from assertpy2 import match

# simple value check
assert 42 == match.is_positive()
assert "hello" == match.is_non_empty_string()

# dict comparison with matchers as expected values
assert {"id": 5, "name": "Alice"} == {
    "id": match.is_positive(),
    "name": match.is_non_empty_string(),
}

# list comparison
assert [1, 2, 3] == [match.is_positive(), match.is_positive(), match.is_positive()]

# composition works too
assert 42 == (match.is_positive() & match.less_than(100))
```

On failure, pytest shows the matcher description in the assertion message:

```
AssertionError: assert -5 == a positive value
```

This makes matchers a drop-in addition to existing test suites: add one import, use `match.*` in any `==` comparison, no rewrite required.

### Available matchers

| Matcher | Description |
|---|---|
| `match.equal_to(val)` | Equality check |
| `match.greater_than(val)` | Greater than |
| `match.greater_than_or_equal_to(val)` | Greater than or equal |
| `match.less_than(val)` | Less than |
| `match.less_than_or_equal_to(val)` | Less than or equal |
| `match.between(low, high)` | Inclusive range check |
| `match.close_to(val, tolerance)` | Within tolerance |
| `match.is_none()` | Is None |
| `match.is_not_none()` | Is not None |
| `match.is_instance_of(type)` | isinstance check |
| `match.has_length(n)` | Length check |
| `match.is_empty()` | Empty collection/string |
| `match.is_not_empty()` | Non-empty collection/string |
| `match.is_positive()` | Positive number |
| `match.is_negative()` | Negative number |
| `match.is_zero()` | Is zero |
| `match.is_even()` | Even integer |
| `match.is_odd()` | Odd integer |
| `match.is_divisible_by(n)` | Divisible by n |
| `match.is_callable()` | Is callable |
| `match.is_in(*values)` | Value in given set |
| `match.has_property(name, matcher?)` | Has attribute, optionally matching a nested matcher |
| `match.contains_string(sub)` | Substring check |
| `match.matches_regex(pattern)` | Regex match |
| `match.is_uuid()` | Valid UUID string |
| `match.is_non_empty_string()` | Non-empty string |
| `match.ignore()` | Always matches (for structural matching) |
| `match.each_item(matcher)` | Every item in iterable matches |
| `match.structure(spec)` | Recursive dict matching |

[Back to top](#table-of-contents)

## Structural Matching

Validate dict structure declaratively using matchers as value specifications. Useful for API response testing where some values are dynamic (IDs, timestamps):

```py
from assertpy2 import assert_that, match

response = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Alice",
    "age": 30,
    "active": True,
}

assert_that(response).matches_structure({
    "id": match.is_uuid(),
    "name": match.equal_to("Alice"),
    "age": match.between(18, 120),
    "active": match.equal_to(True),
})
```

### Nested structures

Use `match.structure()` for nested dicts:

```py
assert_that({
    "user": {"name": "Alice", "role": "admin"},
    "metadata": {"version": 2},
}).matches_structure({
    "user": match.structure({
        "name": match.is_non_empty_string(),
        "role": match.contains_string("admin"),
    }),
    "metadata": match.structure({
        "version": match.greater_than(0),
    }),
})
```

### Ignoring fields

Use `match.ignore()` to skip fields you don't care about:

```py
assert_that({"id": "abc-123", "data": [1, 2, 3]}).matches_structure({
    "id": match.ignore(),
    "data": match.has_length(3),
})
```

### Validating collections inside structures

Use `match.each_item()` to check every element in a nested collection:

```py
assert_that({"tags": ["python", "testing"]}).matches_structure({
    "tags": match.each_item(match.is_instance_of(str)),
})
```

[Back to top](#table-of-contents)

## Custom Matchers - registering domain matchers

The `register_matcher()` decorator lets you add custom matchers to the `match` namespace. Custom matchers support full composition with `&`, `|`, `~` and work everywhere matchers are accepted: `satisfies()`, `each()`, `matches_structure()`, `contains()`.

### Simple (no-argument) matchers

```py
from assertpy2 import assert_that, match, register_matcher

@register_matcher("is_valid_email")
def is_valid_email():
    return match.matches_regex(r"^[\w.-]+@[\w.-]+\.\w+$")

assert_that("alice@example.com").satisfies(match.is_valid_email())
assert_that(users).extracting("email").each(match.is_valid_email())
```

### Parametrised matchers

```py
@register_matcher("has_status")
def has_status(expected: str):
    return match.has_property("status", match.equal_to(expected))

assert_that(order).satisfies(match.has_status("active"))
```

### Composition

Custom matchers compose with built-in matchers using `&`, `|`, `~`:

```py
assert_that(email).satisfies(
    match.is_valid_email() & match.contains_string("@company.com")
)
assert_that(value).satisfies(~match.is_valid_email())
```

### In structural matching

```py
assert_that(response).matches_structure({
    "email": match.is_valid_email(),
    "status": match.has_status("active"),
    "name": match.is_non_empty_string(),
})
```

### Removing a custom matcher

```py
from assertpy2 import unregister_matcher

unregister_matcher("is_valid_email")
```

[Back to top](#table-of-contents)

---

## JSON Path / Schema Validation

Navigate JSON structures with JSONPath and validate against JSON Schema.

Requires optional dependencies:

```bash
pip install assertpy2[json]
```

### at_json_path

Navigate to a JSONPath and continue asserting on the extracted value:

```py
data = {"users": [{"name": "Alice"}, {"name": "Bob"}], "meta": {"total": 2}}

assert_that(data).at_json_path("$.meta.total").is_equal_to(2)
assert_that(data).at_json_path("$.users[0].name").is_equal_to("Alice")
assert_that(data).at_json_path("$.users[*].name").is_equal_to(["Alice", "Bob"])
```

Raises `ValueError` if the path does not exist.

### has_json_path / does_not_have_json_path

Assert that a JSONPath exists or does not exist:

```py
assert_that(data).has_json_path("$.meta.total")
assert_that(data).does_not_have_json_path("$.error")
```

### matches_json_schema

Validate against a JSON Schema dict:

```py
schema = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    "required": ["name"],
}

assert_that({"name": "Alice", "age": 30}).matches_json_schema(schema)
```

### matches_json_schema_from_file

Load the schema from a JSON file:

```py
assert_that(data).matches_json_schema_from_file("schemas/user.json")
```

All JSON assertions work with soft assertions and chaining:

```py
with soft_assertions():
    assert_that(response).has_json_path("$.data").at_json_path("$.data.id").is_positive()
```

[Back to top](#table-of-contents)

## Regex Group Extraction

Extract regex capture groups from strings and continue asserting on the extracted value.

### extracting_group()

Search val for a regex pattern and return a new builder whose val is the captured group:

```py
log = "2024-01-15 ERROR status=500 path=/api/users"

# extract by positional group index
assert_that(log).extracting_group(r"status=(\d+)", 1).is_equal_to("500")

# extract by named group
assert_that(log).extracting_group(r"(?P<level>\w+) status", "level").is_equal_to("ERROR")

# default group=0 extracts the entire match
assert_that("abc123").extracting_group(r"\d+").is_equal_to("123")

# chain further assertions on the extracted value
assert_that("count=42").extracting_group(r"count=(\d+)", 1).is_digit().is_length(2)
```

### matches_with_groups()

Search val for a pattern and return a new builder whose val is the tuple of all groups (or a dict for named groups):

```py
# positional groups return a tuple
assert_that("2024-01-15 ERROR").matches_with_groups(
    r"(\d{4}-\d{2}-\d{2}) (\w+)"
).is_equal_to(("2024-01-15", "ERROR"))

# named groups return a dict
assert_that("key=value").matches_with_groups(
    r"(?P<key>\w+)=(?P<val>\w+)"
).contains_entry({"key": "key"}).contains_entry({"val": "value"})
```

[Back to top](#table-of-contents)

---

## Soft Assertions

Normally, an assertion failure will halt test execution immediately by raising an error. Soft assertions are
way to collect assertion failures together, to be raise all at once at the end, without halting your test.  To use
soft assertions in `assertpy2`, just use the `with soft_assertions()` context manager, like this:

```py
from assertpy2 import assert_that, soft_assertions

with soft_assertions():
    assert_that('foo').is_length(4)
    assert_that('foo').is_empty()
    assert_that('foo').is_false()
    assert_that('foo').is_digit()
    assert_that('123').is_alpha()
    assert_that('foo').is_upper()
    assert_that('FOO').is_lower()
    assert_that('foo').is_equal_to('bar')
    assert_that('foo').is_not_equal_to('foo')
    assert_that('foo').is_equal_to_ignoring_case('BAR')
```

At the end of the block, all assertion failures are collected together and a single `AssertionError` is raised:

```
AssertionError: soft assertion failures:
1. Expected <foo> to be of length <4>, but was <3>.
2. Expected <foo> to be empty string, but was not.
3. Expected <False>, but was not.
4. Expected <foo> to contain only digits, but did not.
5. Expected <123> to contain only alphabetic chars, but did not.
6. Expected <foo> to contain only uppercase chars, but did not.
7. Expected <FOO> to contain only lowercase chars, but did not.
8. Expected <foo> to be equal to <bar>, but was not.
9. Expected <foo> to be not equal to <foo>, but was.
10. Expected <foo> to be case-insensitive equal to <BAR>, but was not.
```

Also, note that *only* assertion failures are collected, errors such as `TypeError` or `ValueError` are raised immediately.
Triggering an explicit test failure with `fail()` will similarly halt execution immediately.  If you need more
forgiving behavior, you can use `soft_fail()` which is collected like any other failing assertion within a soft assertions block.

Soft assertions are thread-safe and async-safe. Each thread and each `asyncio.Task` gets its own independent failure state via `contextvars`, so concurrent tests never interfere with each other.

[Back to top](#table-of-contents)

## Grouped Soft Assertions

Use `soft_assertions() as sa` to get a collector, then `sa.group(label)` to group errors by section:

```py
from assertpy2 import assert_that, soft_assertions

with soft_assertions() as sa:
    with sa.group("Headers"):
        assert_that(headers["Content-Type"]).is_equal_to("application/json")
        assert_that(headers["Accept"]).contains("json")
    with sa.group("Body"):
        assert_that(body["status"]).is_equal_to("ok")
        assert_that(body["items"]).is_not_empty()
```

Output with groups:

```
soft assertion failures:
  [Headers]
    1. Expected <text/html> to be equal to <application/json>, but was not.
  [Body]
    2. Expected <error> to be equal to <ok>, but was not.
```

Without `as sa` or without calling `sa.group()`, the behavior is unchanged (flat error list).

### assert_all

`assert_all()` is a convenience wrapper for inline soft assertions:

```py
from assertpy2 import assert_all, assert_that

assert_all(
    lambda: assert_that(x).is_positive(),
    lambda: assert_that(y).is_not_none(),
    lambda: assert_that(z).is_length(3),
)
```

Equivalent to wrapping all calls in `with soft_assertions():`.

[Back to top](#table-of-contents)

## Async Assertions

The `eventually()` method creates a polling assertion that retries until the condition is met or a timeout is reached. Useful for testing async operations, eventual consistency, and reactive systems:

```py
from assertpy2 import assert_that

async def test_status_converges():
    await assert_that(get_status).eventually().is_equal_to("ready")
```

### Configuring timeout and interval

By default, `eventually()` polls for 5 seconds with 0.5 second intervals. Use `within()` and `every()` to configure:

```py
# poll for up to 10 seconds, checking every 0.2 seconds
await assert_that(get_count).eventually().within(10).every(0.2).is_greater_than(100)
```

### Async callables

Both sync and async callables are supported:

```py
# sync callable
def get_status():
    return fetch_status_from_db()

await assert_that(get_status).eventually().is_equal_to("done")

# async callable
async def async_get_status():
    return await fetch_status_async()

await assert_that(async_get_status).eventually().is_equal_to("done")
```

### Any assertion method

Any assertion method available on `AssertionBuilder` can be used after `eventually()`:

```py
await assert_that(get_name).eventually().starts_with("Al")
await assert_that(get_items).eventually().contains("expected_item")
await assert_that(get_count).eventually().is_between(10, 20)
```

### Error handling

Only `AssertionError` is retried. Other exceptions (`TypeError`, `ValueError`, etc.) propagate immediately. On timeout, the last `AssertionError` is chained to provide context:

```
AssertionError: Expected condition not met after 5.0 seconds: ...

The above exception was the direct cause of the following exception:

AssertionError: Expected <pending> to be equal to <ready>, but was not.
```

[Back to top](#table-of-contents)

## Structured Errors

When an assertion fails, `assertpy2` raises `AssertionFailure` (a subclass of `AssertionError`) with structured data attached:

```py
from assertpy2 import assert_that

try:
    assert_that(1).is_equal_to(2)
except AssertionError as e:
    print(e.actual)     # 1
    print(e.expected)   # 2
```

For comparisons, a `DiffResult` with structural diff entries is available:

```py
try:
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 99})
except AssertionError as e:
    print(e.diff)
    # DiffResult(kind='dict', entries=[DiffEntry(path='b', actual=2, expected=99)])
```

`AssertionFailure` is a subclass of `AssertionError`, so all existing `except AssertionError` handlers continue to work.

### Pytest integration

When the `assertpy2` pytest plugin is active, `AssertionFailure` data is automatically rendered as extra sections in the test report:

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

The plugin is auto-registered via the `pytest11` entry point. No configuration needed. See [Rich Pytest Diffs](#rich-pytest-diffs) for details on supported types and configuration.

[Back to top](#table-of-contents)

## Rich Pytest Diffs

When `is_equal_to()` or `contains()`/`contains_exactly()` fail, the `AssertionFailure` exception carries a `DiffResult` with structured diff data. The pytest plugin renders this as colored diff sections in failure reports.

### Supported types

| Type | Diff kind | How it works |
|---|---|---|
| `list`, `tuple` | `sequence` | Element-by-element comparison with recursive descent into nested dicts/dataclasses/models |
| `set`, `frozenset` | `set` | Extra and missing items |
| `str` | `string` | Line-by-line comparison |
| `dict` | `dict` | Key-by-key comparison with recursive descent into nested dicts and lists |
| `dataclass` | `dataclass` | Field-by-field comparison, handles different dataclass types with overlapping fields |
| `namedtuple` | `namedtuple` | Field-by-field comparison |
| Pydantic model / `model_dump()` object | `model` | Field-by-field comparison via `model_dump()`, recursive descent into nested models |
| Other | `scalar` | Single entry with actual vs expected |
| `contains`/`contains_exactly` | `contains` | Missing and extra items |

### Example output

```
FAILED test_api.py::test_users
--- AssertionFailure ---
  actual:   [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
  expected: [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Robert'}]
--- Structured Diff ---
diff (sequence):
  [1].name:
    - 'Bob'
    + 'Robert'
```

For sets:

```
--- Structured Diff ---
diff (set):
  extra:   {1}
  missing: {3}
```

### Recursive descent

Nested structures are diffed recursively. For example, a list of dicts shows the exact path to the differing value:

```py
actual = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
expected = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Robert"}]
assert_that(actual).is_equal_to(expected)
# diff path: [1].name
```

This works with dicts, dataclasses, namedtuples, and Pydantic models nested inside lists/tuples. Circular references are detected and shown as `<circular ref>` instead of causing infinite recursion.

### Configuration

Configure via `pyproject.toml` or `pytest.ini`:

```toml
[tool.pytest.ini_options]
assertpy2_diff = "off"              # disable structured diff sections entirely
assertpy2_diff_max_entries = "100"  # max diff entries to show (default 50, 0 = unlimited)
```

When `--color=yes` is passed to pytest, diff output is colored: red for removals, green for additions, cyan for headers.

### Truncation

When a diff has more entries than `assertpy2_diff_max_entries`, excess entries are hidden with a summary line:

```
  ... and 47 more entries
```

Set `assertpy2_diff_max_entries = "0"` for unlimited output.

[Back to top](#table-of-contents)

## Snapshot Testing

Take a snapshot of a python data structure, store it on disk in JSON format, and automatically compare the latest data to the stored data on every test run.  The snapshot testing features of `assertpy2` are borrowed from [Jest](https://facebook.github.io/jest/), a well-known and powerful Javascript testing framework.

For example, snapshot the following dict:

```py
assert_that({'a':1,'b':2,'c':3}).snapshot()
```

Stored on disk as the following JSON:

```
{
  "a": 1,
  "b": 2,
  "c": 3
}
```

Additionally, the on-disk snapshot format supports most python data structures (dict, list, object, etc).  For example:

```py
assert_that(None).snapshot()
assert_that(True).snapshot()
assert_that(123).snapshot()
assert_that(-987.654).snapshot()
assert_that('foo').snapshot()
assert_that([1,2,3]).snapshot()
assert_that(set(['a','b','c'])).snapshot()
assert_that({'a':1,'b':2,'c':3}).snapshot()
assert_that(1 + 2j).snapshot()
assert_that(someobj).snapshot()
```

Snapshot artifacts (typically found in the `__snapshots` folder), should be committed to source control alongside any code changes.

On the first run (when the snapshot file doesn't yet exist), the snapshot is created, stored to disk, and the test is passed.  On all subsequent runs, the given data is compared to the on-disk snapshot, and the test fails if they don't match.  Failure means that some change occured, so either a bug or a known implementation changed.

### Updating Snapshots

It's easy to update your snapshots...just delete them all and re-run the test suite to regenerate all snapshots.

### Snapshot Parameters

By default, snapshots are identified by test filename plus line number.  Alternately, you can specify a custom identifier using the `id` keyword:

```py
assert_that({'a':1,'b':2,'c':3}).snapshot(id='my-custom-id')
```

By default, all snapshots (including those with custom identifiers) are stored in the `__snapshots` folder.  Alternately, you can specify a custom path using the `path` keyword:

```py
assert_that({'a':1,'b':2,'c':3}).snapshot(path='my-custom-folder')
```

### Snapshot Blackbox

Functional testing (which snapshot testing falls under) is very much blackbox testing.  When something goes wrong, it's hard to pinpoint the issue, because functional tests provide little *isolation*.  On the plus side, snapshots can provide enormous *leverage* as a few well-placed snapshot tests can strongly verify an application is working that would otherwise require dozens if not hundreds of unit tests.

[Back to top](#table-of-contents)

---

## Failure

The `assertpy2` library includes a `fail()` method to explicitly force a test failure.  It can be used like this:

```py
from assertpy2 import assert_that,fail

def test_fail():
    fail('forced failure')
```

A very useful test pattern that requires the `fail()` method is to verify the exact contents of an error message. For example:

```py
from assertpy2 import assert_that,fail

def test_error_msg():
    try:
        some_func('foo')
        fail('should have raised error')
    except RuntimeError as e:
        assert_that(str(e)).is_equal_to('some err')
```

In the above code, we invoke `some_func()` with a bad argument which raises an exception.  The exception is then handled by the `try..except` block and the exact contents of the error message are verified.  Lastly, if an exception is *not* thrown by `some_func()` as expected, we fail the test via `fail()`.

This pattern is only used when you need to verify the contents of the error message.  If you only wish to check for an expected exception (and don't need to verify the contents of the error message itself), you're better off using [pytest.raises](http://pytest.org/latest/assert.html#assertions-about-expected-exceptions).


### Expected Exceptions

We recommend using pytest's [pytest.raises](http://pytest.org/latest/assert.html#assertions-about-expected-exceptions) context manager for expected exceptions.  In the special case of invoking a function, `assertpy2` provides its own expected exception handling via a simple fluent API.

Given a function `some_func()`:

```py
def some_func(arg):
    raise RuntimeError('some err')
```

We can expect a `RuntimeError` with:

```py
assert_that(some_func).raises(RuntimeError).when_called_with('foo')
```

Additionally, the error message contents are chained, and can be further verified:

```py
assert_that(some_func).raises(RuntimeError).when_called_with('foo')\
    .is_length(8).starts_with('some').is_equal_to('some err')
```

To verify that a function does **not** raise a specific exception:

```py
assert_that(safe_func).does_not_raise(ValueError).when_called_with('foo')
```

If `safe_func` raises `ValueError` (or a subclass), the assertion fails. Any other exception type propagates normally.


### Custom Error Messages

Sometimes you need a little more information in your failures.  For this case, `assertpy2` includes a `described_as()` helper that will add a custom message when a failure occurs.  For example, if we had these failing assertions:

```py
assert_that(1+2).is_equal_to(2)
assert_that(1+2).described_as('adding stuff').is_equal_to(2)
```

When run (separately, of course), they would produce these errors:

```
Expected <3> to be equal to <2>, but was not.
[adding stuff] Expected <3> to be equal to <2>, but was not.
```

The `described_as()` helper causes the custom message `adding stuff` to be prepended to the front of the second error.


### Just A Warning

There are times when you only want a warning message instead of a failing test. For example, if you are using `assertpy2`
to write defensive assertions in the normal flow of your application (not in a test).  In this case, just replace
`assert_that` with `assert_warn`.

```py
assert_warn('foo').is_length(4)
assert_warn('foo').is_empty()
assert_warn('foo').is_false()
assert_warn('foo').is_digit()
assert_warn('123').is_alpha()
assert_warn('foo').is_upper()
assert_warn('FOO').is_lower()
assert_warn('foo').is_equal_to('bar')
assert_warn('foo').is_not_equal_to('foo')
assert_warn('foo').is_equal_to_ignoring_case('BAR')
```

Even though all of the above assertions fail, an `AssertionError` is never raised and execution is
not halted.  Instead, the failed assertions merely log the following warning messages to `stdout`:

```
2019-10-27 20:00:35 WARNING [test_readme.py:423]: Expected <foo> to be of length <4>, but was <3>.
2019-10-27 20:00:35 WARNING [test_readme.py:424]: Expected <foo> to be empty string, but was not.
2019-10-27 20:00:35 WARNING [test_readme.py:425]: Expected <False>, but was not.
2019-10-27 20:00:35 WARNING [test_readme.py:426]: Expected <foo> to contain only digits, but did not.
2019-10-27 20:00:35 WARNING [test_readme.py:427]: Expected <123> to contain only alphabetic chars, but did not.
2019-10-27 20:00:35 WARNING [test_readme.py:428]: Expected <foo> to contain only uppercase chars, but did not.
2019-10-27 20:00:35 WARNING [test_readme.py:429]: Expected <FOO> to contain only lowercase chars, but did not.
2019-10-27 20:00:35 WARNING [test_readme.py:430]: Expected <foo> to be equal to <bar>, but was not.
2019-10-27 20:00:35 WARNING [test_readme.py:431]: Expected <foo> to be not equal to <foo>, but was.
2019-10-27 20:00:35 WARNING [test_readme.py:432]: Expected <foo> to be case-insensitive equal to <BAR>, but was not.
```

#### Custom Warning Logger

By default, warnings are written to `stdout` with a formatter that includes timestamp, log level `WARNING`, and message,
plus some stack frame magic to find the correct filename and line number where `assert_warn()` was called and failed.
For more control or better log formatting, you can pass in your own customer logger when you call `assert_warn()`.

```py
assert_warn('foo', logger=my_logger).is_length(4)
assert_warn('foo', logger=my_logger).is_equal_to_ignoring_case('BAR')
```

[Back to top](#table-of-contents)

---

## Extension System - adding custom assertions

Sometimes you want to add your own custom assertions to `assertpy2`.  This can be done using the `add_extension()` helper.

For example, we can write a custom `is_5()` assertion like this:

```py
from assertpy2 import add_extension

def is_5(self):
    if self.val != 5:
        return self.error(f'{self.val} is NOT 5!')
    return self

add_extension(is_5)
```

Once registered with `assertpy2`, we can use our new assertion as expected:

```py
assert_that(5).is_5()
assert_that(6).is_5()  # fails!
```

Of course, `is_5()` is only available in the test file where `add_extension()` is called.  If you want better control of scope of your custom extensions, such as writing extensions once and using them in any test file, you'll need to use the test setup functionality of your test runner.  With [pytest](http://pytest.org/latest/contents.html), you can just use a `conftest.py` file and a _fixture_.

For example, if your `conftest.py` is:

```py
import pytest
from assertpy2 import add_extension

def is_5(self):
    if self.val != 5:
        return self.error(f'{self.val} is NOT 5!')
    return self

@pytest.fixture(scope='module')
def my_extensions():
    add_extension(is_5)
```

Then in any test method in any test file (like `test_foo.py` for example), you just pass in the fixture and all of your extensions are available, like this:

```py
from assertpy2 import assert_that

def test_foo(my_extensions):
    assert_that(5).is_5()
    assert_that(6).is_5()  # fails!
```

where the `my_extensions` parameter must be the name of your fixture function in `conftest.py`.  See the [fixture docs](https://docs.pytest.org/en/latest/fixture.html) for details.

### Writing custom assertions

Here are some useful tips to help you write your own custom assertions:

1. Use `self` as first param (as if your function was an instance method).
2. Use `self.val` to get the _actual_ value to be tested.
3. It's better to test the negative, and then fail if true.
4. Fail by raising an `AssertionError` (the `self.error()` helper does this for you).
5. Always use the `self.error()` helper to fail (and print your failure message).
6. Always `return self` to allow for chaining.

Putting it all together, here is another custom assertion example, but annotated with comments:

```py
def is_multiple_of(self, other):
    # validate actual value - must be "integer" (aka int or long)
    if isinstance(self.val, numbers.Integral) is False or self.val <= 0:
        # bad input is error, not an assertion fail, so raise error
        raise TypeError('val must be a positive integer')

    # validate expected value
    if isinstance(other, numbers.Integral) is False or other <= 0:
        raise TypeError('given arg must be a positive integer')

    # calc remainder using divmod() built-in
    _, rem = divmod(self.val, other)

    # test the negative (is remainder non-zero?)
    if rem > 0:
        # non-zero remainder, so not multiple -> we fail!
        return self.error(f'Expected <{self.val}> to be multiple of <{other}>, but was not.')

    # success, and return self to allow chaining
    return self
```

[Back to top](#table-of-contents)

---

## Allure Integration

When `allure-pytest` is installed, the assertpy2 pytest plugin automatically attaches structured failure data to Allure reports as JSON attachments. No code changes needed, it works out of the box.

```bash
pip install assertpy2[allure]
```

### Attachment modes

Control what gets attached via the `assertpy2_allure` ini option:

| Mode | Structured Diff | Actual/Expected |
|---|:---:|:---:|
| `diff` (default) | Yes | No |
| `full` | Yes | Yes |
| `off` | No | No |

Configure in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
assertpy2_allure = "full"
```

Or via command line:

```bash
pytest -o "assertpy2_allure=full"
```

### What gets attached

**Structured Diff** (modes: `diff`, `full`) - a JSON attachment with path-level breakdown of dict/list differences:

```json
{
  "kind": "dict",
  "entries": [
    {"path": "user.settings.theme", "actual": "'dark'", "expected": "'light'"},
    {"path": "user.settings.lang", "actual": "'en'", "expected": "'ru'"}
  ]
}
```

**AssertionFailure** (mode: `full` only) - a JSON attachment with actual and expected values:

```json
{
  "actual": "{'name': 'Alice', 'age': 30}",
  "expected": "{'name': 'Alice', 'age': 25}"
}
```

### Pytest report sections

Regardless of Allure mode, the plugin always adds human-readable sections to the pytest terminal output:

```
--- AssertionFailure ---
  actual:   {'name': 'Alice', 'age': 30}
  expected: {'name': 'Alice', 'age': 25}
--- Structured Diff ---
diff (dict):
  at age: actual=<30>, expected=<25>
```

### Exception safety

If Allure is not installed or `allure.attach()` fails for any reason, the plugin silently continues. Test results are never affected by Allure errors.

### Invalid mode handling

An invalid mode value (e.g. a typo like `assertpy2_allure=diffs`) triggers a warning and falls back to `diff`.


[Back to top](#table-of-contents)

## Behave Step Matchers

assertpy2 provides ready-made parameter types for [Behave](https://behave.readthedocs.io/) step definitions. These types parse and validate step parameters automatically.

```bash
pip install assertpy2[behave]
```

### Registration

Call `register_assertpy_types()` once, typically in `environment.py` or a step file:

```py
from assertpy2.behave_matchers import register_assertpy_types

register_assertpy_types()
```

### Available types

| Type | Pattern | Description | Example input |
|---|---|---|---|
| `PositiveInt` | `\d+` | Integer > 0 | `1`, `42`, `100` |
| `NonNegativeInt` | `\d+` | Integer >= 0 | `0`, `1`, `42` |
| `PositiveFloat` | `\d+\.?\d*` | Float > 0 | `1.5`, `42`, `0.01` |
| `NonEmptyString` | `.+?` | Stripped non-blank string | `hello`, `foo bar` |
| `BoolLike` | `\w+` | Boolean from text | `true`, `yes`, `1`, `on`, `false`, `no`, `0`, `off` |

### Usage in step definitions

```py
@given('a user aged {age:PositiveInt}')
def step_user_aged(context, age):
    context.age = age  # int, guaranteed > 0

@given('the feature is {enabled:BoolLike}')
def step_feature_toggle(context, enabled):
    context.enabled = enabled  # bool

@when('the user searches for {query:NonEmptyString}')
def step_search(context, query):
    context.query = query  # str, stripped, non-blank
```

### Validation errors

Invalid values raise `ValueError` with descriptive messages:

```py
# step: "a user aged 0" -> ValueError: expected positive integer, got 0
# step: "the feature is maybe" -> ValueError: expected boolean-like value, got 'maybe'
# step: "the user searches for   " -> ValueError: expected non-empty string, got blank
```

### Using types directly

The `ASSERTPY_TYPES` dict is available for direct access without Behave:

```py
from assertpy2.behave_matchers import ASSERTPY_TYPES

parse_int = ASSERTPY_TYPES["PositiveInt"]
value = parse_int("42")  # 42
```


[Back to top](#table-of-contents)

---

<p align="center">
  <a href="https://github.com/Solganis/assertpy2/blob/main/LICENSE">BSD 3-Clause License</a>
</p>
