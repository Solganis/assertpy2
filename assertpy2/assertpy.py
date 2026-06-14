"""Assertion library for python unit testing with a fluent API"""

from __future__ import annotations

import contextlib
import contextvars
import inspect
import logging
import os
import sys
import types
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, overload

if TYPE_CHECKING:
    import datetime
    import pathlib

    from typing_extensions import Self

    from ._typing import (
        _CallableAssertion,
        _DateAssertion,
        _DictAssertion,
        _IterableAssertion,
        _NumericAssertion,
        _PathAssertion,
        _StringAssertion,
    )

from .async_assertions import AsyncAssertionBuilder
from .base import BaseMixin
from .collection import CollectionMixin
from .contains import ContainsMixin
from .date import DateMixin
from .dict import DictMixin
from .dynamic import DynamicMixin
from .errors import AssertionFailure
from .exception import ExceptionMixin
from .extracting import ExtractingMixin
from .file import FileMixin
from .helpers import HelpersMixin
from .numeric import NumericMixin
from .snapshot import SnapshotMixin
from .string import StringMixin

__version__ = "2.3.6"

__tracebackhide__ = True  # clean tracebacks via py.test integration
contextlib.__tracebackhide__ = True  # ty: ignore[unresolved-attribute]  # pytest monkey-patch

# assertpy files
ASSERTPY_FILES = [
    os.path.join("assertpy2", file)
    for file in [
        "assertpy.py",
        "async_assertions.py",
        "base.py",
        "collection.py",
        "contains.py",
        "date.py",
        "dict.py",
        "dynamic.py",
        "errors.py",
        "exception.py",
        "extracting.py",
        "file.py",
        "helpers.py",
        "matchers.py",
        "numeric.py",
        "pytest_plugin.py",
        "snapshot.py",
        "string.py",
    ]
]

# soft assertions (contextvars for thread/async safety)
_soft_ctx: contextvars.ContextVar[int] = contextvars.ContextVar("assertpy2_soft_ctx", default=0)
_soft_err: contextvars.ContextVar[list[str]] = contextvars.ContextVar("assertpy2_soft_err")


@contextlib.contextmanager
def soft_assertions() -> Iterator[None]:
    """Create a soft assertion context.

    Normally, any assertion failure will halt test execution immediately by raising an error.
    Soft assertions are way to collect assertion failures (and failure messages) together, to be
    raised all at once at the end, without halting your test.

    Uses :mod:`contextvars` internally, so each thread and each ``asyncio`` task gets its own
    independent soft-assertion state.

    Examples:
        Create a soft assertion context, and some failing tests::

            from assertpy2 import assert_that, soft_assertions

            with soft_assertions():
                assert_that('foo').is_length(4)
                assert_that('foo').is_empty()
                assert_that('foo').is_false()
                assert_that('foo').is_digit()
                assert_that('123').is_alpha()

        When the context ends, any assertion failures are collected together and a single
        ``AssertionError`` is raised::

            AssertionError: soft assertion failures:
            1. Expected <foo> to be of length <4>, but was <3>.
            2. Expected <foo> to be empty string, but was not.
            3. Expected <False>, but was not.
            4. Expected <foo> to contain only digits, but did not.
            5. Expected <123> to contain only alphabetic chars, but did not.

    Note:
        The soft assertion context only collects *assertion* failures, other errors such as
        ``TypeError`` or ``ValueError`` are always raised immediately.  Triggering an explicit test
        failure with :meth:`fail` will similarly halt execution immediately.  If you need more
        forgiving behavior, use :meth:`soft_fail` to add a failure message without halting test
        execution.
    """
    ctx = _soft_ctx.get()
    if ctx == 0:
        _soft_err.set([])
    _soft_ctx.set(ctx + 1)

    try:
        yield
    finally:
        _soft_ctx.set(_soft_ctx.get() - 1)

    errs = _soft_err.get([])
    if errs and _soft_ctx.get() == 0:
        out = "soft assertion failures:\n" + "\n".join(f"{i + 1}. {msg}" for i, msg in enumerate(errs))
        _soft_err.set([])
        raise AssertionError(out)


# factory methods


@overload
def assert_that(val: str, description: str = "") -> _StringAssertion: ...


@overload
def assert_that(val: int | float | complex, description: str = "") -> _NumericAssertion: ...


@overload
def assert_that(val: dict, description: str = "") -> _DictAssertion: ...


@overload
def assert_that(val: list | tuple, description: str = "") -> _IterableAssertion: ...


@overload
def assert_that(val: set | frozenset, description: str = "") -> _IterableAssertion: ...


@overload
def assert_that(val: datetime.date, description: str = "") -> _DateAssertion: ...


@overload
def assert_that(val: pathlib.Path, description: str = "") -> _PathAssertion: ...


@overload
def assert_that(val: Callable[..., object], description: str = "") -> _CallableAssertion: ...


@overload
def assert_that(val: object, description: str = "") -> AssertionBuilder: ...


def assert_that(val, description=""):
    """Set the value to be tested, plus an optional description, and allow assertions to be called.

    This is a factory method for the :class:`AssertionBuilder`, and the single most important
    method in all of assertpy.

    Args:
        val: the value to be tested (aka the actual value)
        description (str, optional): the extra error message description. Defaults to ``''``
            (aka empty string)

    Examples:
        Just import it once at the top of your test file, and away you go...::

            from assertpy2 import assert_that

            def test_something():
                assert_that(1 + 2).is_equal_to(3)
                assert_that('foobar').is_length(6).starts_with('foo').ends_with('bar')
                assert_that(['a', 'b', 'c']).contains('a').does_not_contain('x')
    """
    if _soft_ctx.get():
        return _builder(val, description, "soft")
    return _builder(val, description)


def assert_warn(val, description="", logger=None):
    """Set the value to be tested, and optional description and logger, and allow assertions to be
    called, but never fail, only log warnings.

    This is a factory method for the :class:`AssertionBuilder`, but unlike :meth:`assert_that` an
    `AssertionError` is never raised, and execution is never halted.  Instead, any assertion failures
    results in a warning message being logged. Uses the given logger, or defaults to a simple logger
    that prints warnings to ``stdout``.


    Args:
        val: the value to be tested (aka the actual value)
        description (str, optional): the extra error message description. Defaults to ``''``
            (aka empty string)
        logger (Logger, optional): the logger for warning message on assertion failure. Defaults to ``None``
            (aka use the default simple logger that prints warnings to ``stdout``)

    Examples:
        Usage::

            from assertpy2 import assert_warn

            assert_warn('foo').is_length(4)
            assert_warn('foo').is_empty()
            assert_warn('foo').is_false()
            assert_warn('foo').is_digit()
            assert_warn('123').is_alpha()

        Even though all of the above assertions fail, ``AssertionError`` is never raised and
        test execution is never halted.  Instead, the failed assertions merely log the following
        warning messages to ``stdout``::

            2019-10-27 20:00:35 WARNING [test_foo.py:23]: Expected <foo> to be of length <4>, but was <3>.
            2019-10-27 20:00:35 WARNING [test_foo.py:24]: Expected <foo> to be empty string, but was not.
            2019-10-27 20:00:35 WARNING [test_foo.py:25]: Expected <False>, but was not.
            2019-10-27 20:00:35 WARNING [test_foo.py:26]: Expected <foo> to contain only digits, but did not.
            2019-10-27 20:00:35 WARNING [test_foo.py:27]: Expected <123> to contain only alphabetic chars, but did not.

    Tip:
        Use :meth:`assert_warn` if and only if you have a *really* good reason to log assertion
        failures instead of failing.
    """
    return _builder(val, description, "warn", logger=logger)


def fail(msg=""):
    """Force immediate test failure with the given message.

    Args:
        msg (str, optional): the failure message.  Defaults to ``''``

    Examples:
        Fail a test::

            from assertpy2 import assert_that, fail

            def test_fail():
                fail('forced fail!')

        If you wanted to test for a known failure, here is a useful pattern::

            import operator

            def test_adder_bad_arg():
                try:
                    operator.add(1, 'bad arg')
                    fail('should have raised error')
                except TypeError as e:
                    assert_that(str(e)).contains('unsupported operand')
    """
    raise AssertionError(f"Fail: {msg}!" if msg else "Fail!")


def soft_fail(msg=""):
    """Within a :meth:`soft_assertions` context, append the failure message to the soft error list,
    but do not halt test execution.

    Otherwise, outside the context, acts identical to :meth:`fail` and forces immediate test
    failure with the given message.

    Args:
        msg (str, optional): the failure message.  Defaults to ``''``

    Examples:
        Failing soft assertions::

            from assertpy2 import assert_that, soft_assertions, soft_fail

            with soft_assertions():
                assert_that(1).is_equal_to(2)
                soft_fail('my message')
                assert_that('foo').is_equal_to('bar')

        Fails, and outputs the following soft error list::

            AssertionError: soft assertion failures:
            1. Expected <1> to be equal to <2>, but was not.
            2. Fail: my message!
            3. Expected <foo> to be equal to <bar>, but was not.

    """
    if _soft_ctx.get():
        _soft_err.get().append(f"Fail: {msg}!" if msg else "Fail!")
        return
    fail(msg)


# assertion extensions
_extensions = {}


def add_extension(func):
    """Add a new user-defined custom assertion to assertpy.

    Once the assertion is registered with assertpy, use it like any other assertion.  Pass val to
    :meth:`assert_that`, and then call it.

    Args:
        func: the assertion function (to be added)

    Examples:
        Usage::

            from assertpy2 import add_extension

            def is_5(self):
                if self.val != 5:
                    return self.error(f'{self.val} is NOT 5!')
                return self

            add_extension(is_5)

            def test_5():
                assert_that(5).is_5()

            def test_6():
                assert_that(6).is_5()  # fails
                # 6 is NOT 5!
    """
    if not callable(func):
        raise TypeError("func must be callable")
    _extensions[func.__name__] = func


def remove_extension(func):
    """Remove a user-defined custom assertion.

    Args:
        func: the assertion function (to be removed)

    Examples:
        Usage::

            from assertpy2 import remove_extension

            remove_extension(is_5)
    """
    if not callable(func):
        raise TypeError("func must be callable")
    if func.__name__ in _extensions:
        del _extensions[func.__name__]


def _builder(val, description="", kind=None, expected=None, logger=None):
    """Internal helper to build a new :class:`AssertionBuilder` instance and glue on any extension methods."""
    ab = AssertionBuilder(val, description, kind, expected, logger)
    if _extensions:
        for name, func in _extensions.items():
            meth = types.MethodType(func, ab)
            setattr(ab, name, meth)
    return ab


# warnings
class WarningLoggingAdapter(logging.LoggerAdapter):
    """Logging adapter to unwind the stack to get the correct callee filename and line number."""

    def process(self, msg, kwargs):
        def _unwind(frame):
            frames = []
            while frame:
                frames.append((frame.f_code.co_filename, frame.f_lineno))
                frame = frame.f_back

            prev = None
            for frame in reversed(
                frames
            ):  # pragma: no branch - loop always finds an assertpy frame when called from error()
                for f in ASSERTPY_FILES:
                    if frame[0].endswith(f):
                        return prev
                prev = frame

        filename, lineno = _unwind(inspect.currentframe())
        return f"[{os.path.basename(filename)}:{lineno}]: {msg}", kwargs


_logger = logging.getLogger("assertpy2")
_handler = logging.StreamHandler(sys.stdout)
_handler.setLevel(logging.WARNING)
_format = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
_handler.setFormatter(_format)
_logger.addHandler(_handler)
_default_logger = WarningLoggingAdapter(_logger, None)


class NegatedBuilder:
    """Proxy that inverts the next assertion. Created by ``assert_that(val).not_``."""

    def __init__(self, builder: AssertionBuilder) -> None:
        self._builder = builder

    def __getattr__(self, name: str) -> object:
        attr = getattr(self._builder, name)
        if not callable(attr):
            return attr

        def _negated(*args: object, **kwargs: object) -> AssertionBuilder:
            if self._builder.kind == "soft":
                return self._negated_soft(name, attr, *args, **kwargs)
            if self._builder.kind == "warn":
                return self._negated_warn(name, attr, *args, **kwargs)
            return self._negated_strict(name, attr, *args, **kwargs)

        return _negated

    def _make_msg(self, name: str) -> str:
        desc = f"[{self._builder.description}] " if self._builder.description else ""
        return f"{desc}Expected <{self._builder.val}> to NOT satisfy: {name}()"

    def _negated_strict(
        self, name: str, attr: Callable[..., object], *args: object, **kwargs: object
    ) -> AssertionBuilder:
        try:
            attr(*args, **kwargs)
        except (AssertionError, AssertionFailure):
            return self._builder
        raise AssertionError(self._make_msg(name))

    def _negated_soft(
        self, name: str, attr: Callable[..., object], *args: object, **kwargs: object
    ) -> AssertionBuilder:
        err_list = _soft_err.get()
        before = len(err_list)
        attr(*args, **kwargs)
        if len(err_list) > before:
            del err_list[before:]
            return self._builder
        err_list.append(self._make_msg(name))
        return self._builder

    def _negated_warn(
        self, name: str, attr: Callable[..., object], *args: object, **kwargs: object
    ) -> AssertionBuilder:
        self._builder.kind = None
        try:
            attr(*args, **kwargs)
        except (AssertionError, AssertionFailure):
            return self._builder
        finally:
            self._builder.kind = "warn"
        self._builder.logger.warning(self._make_msg(name))
        return self._builder


class AssertionBuilder(
    StringMixin,
    SnapshotMixin,
    NumericMixin,
    HelpersMixin,
    FileMixin,
    ExtractingMixin,
    ExceptionMixin,
    DynamicMixin,
    DictMixin,
    DateMixin,
    ContainsMixin,
    CollectionMixin,
    BaseMixin,
):
    """The main assertion class.  Never call the constructor directly, always use the
    :meth:`assert_that` helper instead.  Or if you just want warning messages, use the
    :meth:`assert_warn` helper.

    Args:
        val: the value to be tested (aka the actual value)
        description (str, optional): the extra error message description.  Defaults to ``''``
            (aka empty string)
        kind (str, optional): the kind of assertions, one of ``None``, ``soft``, or ``warn``.
            Defaults to ``None``
        expected (Error, optional): the expected exception.  Defaults to ``None``
        logger (Logger, optional): the logger for warning messages.  Defaults to ``None``
    """

    def __init__(self, val, description="", kind=None, expected=None, logger=None):
        """Never call this constructor directly."""
        self.val = val
        self.description = description
        self.kind = kind
        self.expected = expected
        self.logger = logger if logger else _default_logger
        self._not_expected = False

    @property
    def not_(self) -> NegatedBuilder:
        """Invert the next assertion in the chain."""
        return NegatedBuilder(self)

    def builder(self, val, description="", kind=None, expected=None, logger=None):
        """Helper to build a new :class:`AssertionBuilder` instance. Use this only if not chaining to ``self``.

        Args:
            val: the value to be tested (aka the actual value)
            description (str, optional): the extra error message description.  Defaults to ``''``
                (aka empty string)
            kind (str, optional): the kind of assertions, one of ``None``, ``soft``, or ``warn``.
                Defaults to ``None``
            expected (Error, optional): the expected exception.  Defaults to ``None``
            logger (Logger, optional): the logger for warning messages.  Defaults to ``None``
        """
        return _builder(val, description, kind, expected, logger)

    def error(self, msg, *, actual=None, expected=None, diff=None) -> Self:
        """Helper to raise an ``AssertionError`` with the given message.

        If an error description is set by :meth:`~assertpy.base.BaseMixin.described_as`, then that
        description is prepended to the error message.

        When structured data (``actual``, ``expected``, or ``diff``) is provided, raises
        :class:`~assertpy2.errors.AssertionFailure` instead of plain ``AssertionError``.

        Args:
            msg: the error message
            actual: the actual value (for structured error reporting)
            expected: the expected value (for structured error reporting)
            diff: a :class:`~assertpy2.errors.DiffResult` instance (for structured error reporting)

        Raises:
            AssertionError: always raised unless ``kind`` is ``warn`` or ``soft``.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion, but only when
                ``AssertionError`` is not raised, as is the case when ``kind`` is ``warn`` or ``soft``.
        """
        out = f"{f'[{self.description}] ' if len(self.description) > 0 else ''}{msg}"
        if self.kind == "warn":
            self.logger.warning(out)
            return self
        elif self.kind == "soft":
            _soft_err.get().append(out)
            return self
        else:
            if expected is not None or diff is not None:
                raise AssertionFailure(out, actual=actual, expected=expected, diff=diff)
            raise AssertionError(out)

    def eventually(self, *, timeout: float = 5.0, interval: float = 0.5) -> AsyncAssertionBuilder:
        """Switch to async polling mode for eventual-consistency assertions.

        The current ``val`` must be a callable (sync or async).  Returns an
        :class:`~assertpy2.async_assertions.AsyncAssertionBuilder` whose assertion
        methods are coroutines that poll ``val()`` until the assertion passes or
        ``timeout`` expires.

        Args:
            timeout: maximum seconds to keep retrying (default ``5.0``)
            interval: seconds between retries (default ``0.5``)

        Examples:
            Usage::

                import asyncio
                from assertpy2 import assert_that

                counter = {"n": 0}

                def get_count():
                    counter["n"] += 1
                    return counter["n"]

                asyncio.run(
                    assert_that(get_count).eventually(timeout=2).is_equal_to(3)
                )

        Returns:
            AsyncAssertionBuilder: an async builder whose assertion methods are awaitable

        Raises:
            TypeError: if ``val`` is not callable
        """
        if not callable(self.val):
            raise TypeError("val must be callable when using eventually()")
        return AsyncAssertionBuilder(
            self.val,
            builder_func=_builder,
            description=self.description,
            timeout=timeout,
            interval=interval,
        )
