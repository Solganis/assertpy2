# Extending

Add your own assertions to `assertpy2` with `add_extension()`.

## A custom assertion

```python
from assertpy2 import add_extension, assert_that

def is_5(self):
    if self.val != 5:
        return self.error(f"{self.val} is NOT 5!")
    return self

add_extension(is_5)

assert_that(5).is_5()
assert_that(6).is_5()  # fails!
```

`remove_extension()` takes the same function and unregisters it, so a temporary assertion does not
leak into other tests:

```python
from assertpy2 import remove_extension

remove_extension(is_5)
```

## Project-wide reuse

`is_5()` is only available in the file where `add_extension()` is called. To share extensions across
all test files, register them in a pytest fixture in `conftest.py`:

```python
import pytest
from assertpy2 import add_extension

def is_5(self):
    if self.val != 5:
        return self.error(f"{self.val} is NOT 5!")
    return self

@pytest.fixture(scope="module")
def my_extensions():
    add_extension(is_5)
```

Then request the fixture in any test that needs the extensions:

```python
from assertpy2 import assert_that

def test_foo(my_extensions):
    assert_that(5).is_5()
    assert_that(6).is_5()  # fails!
```

## Writing custom assertions

A few conventions keep custom assertions consistent with the built-ins:

1. Use `self` as the first parameter, as if the function were an instance method.
2. Read the actual value from `self.val`.
3. Test the negative case and fail if it holds.
4. Fail via `self.error(...)`, which raises `AssertionError` and prints your message.
5. Raise `TypeError`/`ValueError` for bad input (a programming error), not `self.error()`.
6. Always `return self` so the assertion chains.

```python
import numbers


def is_multiple_of(self, other):
    if isinstance(self.val, numbers.Integral) is False or self.val <= 0:
        raise TypeError("val must be a positive integer")
    if isinstance(other, numbers.Integral) is False or other <= 0:
        raise TypeError("given arg must be a positive integer")

    _, rem = divmod(self.val, other)
    if rem > 0:
        return self.error(f"Expected <{self.val}> to be multiple of <{other}>, but was not.")
    return self
```
