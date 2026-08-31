# Extending

Add your own assertions to `assertpy2` with `add_extension()`.

## A custom assertion

<!-- docs-guard: untyped -->

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

Both lines run, but a type checker rejects the first one, since `5` resolves to the numeric protocol
and that declares no `is_5`.

An extension is visible to a checker only where the value keeps the whole builder, which is a narrow
set: a value with a capability but no overload of its own, such as an iterable you wrote or a mapping
that is not a `dict`, plus anything typed `Any`. Everything else reaches either its own protocol or
the core surface. The reason and the ways round it are in
[Where the typed surface ends](../concepts/type-safety.md#where-the-typed-surface-ends).

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

<!-- docs-guard: untyped -->

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
5. Raise `TypeError`/`ValueError` for bad input (a programming error), not `self.error()`. The
   built-ins word every type refusal the same way, `<subject> must be <expectation>, but was
   <value> (<type>)`, so a custom assertion reads like one when it follows the same shape.
6. Always `return self` so the assertion chains.

```python
import numbers


def is_multiple_of(self, other):
    if isinstance(self.val, numbers.Integral) is False or self.val <= 0:
        raise TypeError(f"val must be a positive integer, but was <{self.val}> ({type(self.val).__name__})")
    if isinstance(other, numbers.Integral) is False or other <= 0:
        raise TypeError(
            f"given other arg must be a positive integer, but was <{other}> ({type(other).__name__})"
        )

    _, rem = divmod(self.val, other)
    if rem > 0:
        return self.error(
            f"Expected <{self.val}> to be multiple of <{other}>, but was not."
        )
    return self
```

### Wrapping a library that raises

When the assertion delegates to a library, the failure is usually caught and folded into the message.
Doing that inside `except` leaves the caught exception in the traceback, and the reader sees the same
diagnostic twice, once under "During handling of the above exception". Pass `suppress_context=True`
to drop it:

```python
def is_valid_config(self):
    try:
        some_library.validate(self.val)
    except some_library.ValidationError as exc:
        return self.error(
            f"Expected a valid config, but it was rejected:\n{exc}",
            suppress_context=True,
        )
    return self
```

Only pass it when the caught exception's text is already in your message, or carries nothing. Leave it
off when the caught exception is the caller's own, as in an assertion about a callable they gave you:
there its traceback is the point of the failure, not noise.
