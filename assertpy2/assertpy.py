"""Assertion library for python unit testing with a fluent API"""

from __future__ import annotations

import contextlib
import contextvars
import inspect
import logging
import os
import sys
import types
from typing import TYPE_CHECKING, Any, Final, Generic, TypeVar, overload

if TYPE_CHECKING:
    import datetime
    import pathlib
    from collections.abc import Callable, Iterator

    from typing_extensions import TypeIs

    from ._compat import Self
    from ._typing import (
        _BytesAssertion,
        _CallableAssertion,
        _CoreAssertion,
        _DateAssertion,
        _DictAssertion,
        _IterableAssertion,
        _NumericAssertion,
        _PathAssertion,
        _StringAssertion,
    )
    from .matchers import Matcher

from ._contract import contract_drift
from .async_assertions import AsyncAssertionBuilder, SyncAssertionBuilder, _normalize_ignoring
from .base import BaseMixin
from .bytes_mixin import BytesMixin
from .collection import CollectionMixin
from .contains import ContainsMixin
from .dataframe import DataFrameMixin
from .date import DateMixin
from .dict import DictMixin
from .dynamic import DynamicMixin
from .errors import AssertionFailure, _truncated
from .exception import _UNSET, ExceptionMixin
from .extracting import ExtractingMixin
from .file import FileMixin
from .helpers import HelpersMixin
from .json_mixin import JsonMixin
from .numeric import NumericMixin
from .snapshot import SnapshotMixin
from .string import StringMixin
from .warning import WarningMixin

__version__ = "2.15.0"

# the tracked value type of the generic AssertionBuilder fallback (_U appears only in narrowing stubs)
_T = TypeVar("_T")
if TYPE_CHECKING:
    _U = TypeVar("_U")
    _E = TypeVar("_E")  # element type of a collection, so first()/element()/... narrow to it

__tracebackhide__ = True  # clean tracebacks via py.test integration
contextlib.__tracebackhide__ = True  # ty: ignore[unresolved-attribute]  # pytest monkey-patch

# assertpy2 source files, used to strip internal frames when locating the caller for warn-mode messages.
# Derived from the package directory so new modules are covered automatically (no hand-maintained list).
ASSERTPY_FILES: Final = [
    os.path.join("assertpy2", name) for name in os.listdir(os.path.dirname(__file__)) if name.endswith(".py")
]

# soft assertions (contextvars for thread/async safety)
_soft_ctx: contextvars.ContextVar[int] = contextvars.ContextVar("assertpy2_soft_ctx", default=0)
_soft_err: contextvars.ContextVar[list[tuple[str | None, str]]] = contextvars.ContextVar("assertpy2_soft_err")
_soft_group: contextvars.ContextVar[str | None] = contextvars.ContextVar("assertpy2_soft_group", default=None)


class SoftAssertionCollector:
    """Collector returned by [`soft_assertions()`][assertpy2.assertpy.soft_assertions] for grouping
    errors hierarchically."""

    @contextlib.contextmanager
    def group(self, label: str) -> Iterator[None]:
        """Group subsequent assertion failures under *label*.

        Examples:
            Usage:

                with soft_assertions() as sa:
                    with sa.group("Headers"):
                        assert_that(headers).contains_key("Content-Type")
                    with sa.group("Body"):
                        assert_that(body["status"]).is_equal_to("ok")
        """
        token = _soft_group.set(label)
        try:
            yield
        finally:
            _soft_group.reset(token)


def _format_soft_errors(errs: list[tuple[str | None, str]]) -> str:
    has_groups = any(group is not None for group, _ in errs)
    if not has_groups:
        return "soft assertion failures:\n" + "\n".join(f"{i + 1}. {msg}" for i, (_, msg) in enumerate(errs))

    lines = ["soft assertion failures:"]
    current_group: str | None = object()  # ty: ignore[invalid-assignment]  # sentinel
    for counter, (group, msg) in enumerate(errs, 1):
        if group != current_group:
            current_group = group
            if group is not None:
                lines.append(f"  [{group}]")
        indent = "    " if group is not None else "  "
        lines.append(f"{indent}{counter}. {msg}")
    return "\n".join(lines)


@contextlib.contextmanager
def soft_assertions() -> Iterator[SoftAssertionCollector]:
    """Create a soft assertion context.

    Normally, any assertion failure will halt test execution immediately by raising an error.
    Soft assertions are way to collect assertion failures (and failure messages) together, to be
    raised all at once at the end, without halting your test.

    Uses `contextvars` internally, so each thread and each ``asyncio`` task gets its own
    independent soft-assertion state.

    Examples:
        Create a soft assertion context, and some failing tests:

            from assertpy2 import assert_that, soft_assertions

            with soft_assertions():
                assert_that('foo').is_length(4)
                assert_that('foo').is_empty()
                assert_that('foo').is_false()
                assert_that('foo').is_digit()
                assert_that('123').is_alpha()

        When the context ends, any assertion failures are collected together and a single
        ``AssertionError`` is raised:

            AssertionError: soft assertion failures:
            1. Expected <foo> to be of length <4>, but was <3>.
            2. Expected <foo> to be empty string, but was not.
            3. Expected <False>, but was not.
            4. Expected <foo> to contain only digits, but did not.
            5. Expected <123> to contain only alphabetic chars, but did not.

        Group errors by section:

            with soft_assertions() as sa:
                with sa.group("Headers"):
                    assert_that(headers["Content-Type"]).is_equal_to("application/json")
                with sa.group("Body"):
                    assert_that(body["status"]).is_equal_to("ok")

    Note:
        The soft assertion context only collects *assertion* failures, other errors such as
        ``TypeError`` or ``ValueError`` are always raised immediately.  Triggering an explicit test
        failure with [`fail()`][assertpy2.assertpy.fail] will similarly halt execution immediately.
        If you need more forgiving behavior, use [`soft_fail()`][assertpy2.assertpy.soft_fail] to add
        a failure message without halting test execution.
    """
    ctx = _soft_ctx.get()
    if ctx == 0:
        _soft_err.set([])
    _soft_ctx.set(ctx + 1)

    try:
        yield SoftAssertionCollector()
    finally:
        _soft_ctx.set(_soft_ctx.get() - 1)

    errs = _soft_err.get([])
    if errs and _soft_ctx.get() == 0:
        out = _format_soft_errors(errs)
        _soft_err.set([])
        raise AssertionError(out)


def assert_all(*callables: Callable[[], object]) -> None:
    """Run all callables inside a soft assertion context.

    A convenience wrapper around [`soft_assertions()`][assertpy2.assertpy.soft_assertions] for inline use.

    Examples:
        Usage:

            from assertpy2 import assert_all, assert_that

            assert_all(
                lambda: assert_that(x).is_positive(),
                lambda: assert_that(y).is_not_none(),
            )

    Raises:
        AssertionError: if any of the callables produce assertion failures
    """
    with soft_assertions():
        for fn in callables:
            fn()


# factory methods


@overload
def assert_that(val: str, description: str = "") -> _StringAssertion: ...


@overload
def assert_that(val: int, description: str = "") -> _NumericAssertion[int]: ...


@overload
def assert_that(val: float, description: str = "") -> _NumericAssertion[float]: ...


@overload
def assert_that(val: complex, description: str = "") -> _NumericAssertion[complex]: ...


@overload
def assert_that(val: dict, description: str = "") -> _DictAssertion: ...


@overload
def assert_that(val: list[_E] | tuple[_E, ...], description: str = "") -> _IterableAssertion[_E]: ...


@overload
def assert_that(val: set[_E] | frozenset[_E], description: str = "") -> _IterableAssertion[_E]: ...


@overload
def assert_that(val: datetime.date, description: str = "") -> _DateAssertion: ...


@overload
def assert_that(val: pathlib.Path, description: str = "") -> _PathAssertion: ...


@overload
def assert_that(val: bytes | bytearray, description: str = "") -> _BytesAssertion: ...


@overload
def assert_that(val: Callable[..., object], description: str = "") -> _CallableAssertion: ...


# Fallback returns the concrete AssertionBuilder so object- and union-typed values keep the full API.
# It is generic over the value type, so `.value` gives the input type back and the narrowing terminals
# (`is_not_none()`, `is_instance_of()`) refine it. The specific protocols are not assignable to
# AssertionBuilder, so mypy --strict reports overload-overlap for each specific overload and pyright one
# reportOverlappingOverload; ty (the gate) does not flag it. Kept intentionally - returning _CoreAssertion
# here would strip type-specific assertions from object/union values.
@overload
def assert_that(val: _T, description: str = "") -> AssertionBuilder[_T]: ...


# Return the common base protocol so each overload stays consistent with the impl (no reportInconsistentOverload).
def assert_that(val: object, description="") -> _CoreAssertion:
    """Set the value to be tested, plus an optional description, and allow assertions to be called.

    This is a factory method for the `AssertionBuilder`, and the single most important
    method in all of assertpy.

    Args:
        val: the value to be tested (aka the actual value)
        description (str, optional): the extra error message description. Defaults to ``''``
            (aka empty string)

    Examples:
        Just import it once at the top of your test file, and away you go...

            from assertpy2 import assert_that

            def test_something():
                assert_that(1 + 2).is_equal_to(3)
                assert_that('foobar').is_length(6).starts_with('foo').ends_with('bar')
                assert_that(['a', 'b', 'c']).contains('a').does_not_contain('x')
    """
    if _soft_ctx.get():
        return _builder(val, description, "soft")
    return _builder(val, description)


def assert_conforms(
    val: object, model: type[_U], description: str = "", *, exact: bool = False
) -> AssertionBuilder[_U]:
    """Validate ``val`` against a pydantic v2 ``model`` and continue over the validated instance.

    The narrowing-complete companion to [`assert_that()`][assertpy2.assertpy.assert_that] for
    contract testing.  Runs ``model.model_validate(val)``: on success the returned builder carries
    the validated, coerced model instance (so ``.value`` and ``extracting`` see typed fields); on
    failure it fails with pydantic's validation errors.  Because the return type is driven by
    ``model`` rather than by the type of ``val``, the chain narrows to ``model`` for **any** input,
    including the ``Any`` a decoded JSON payload carries - the typed capstone of the narrowing family.

    With ``exact=True`` it also asserts **contract drift**: the payload must not carry fields the model
    does not declare.  ``model_validate`` silently drops undeclared fields, so a stale model passes even
    after the live API grows new fields; ``exact`` catches that drift (recursively, into nested
    sub-models and lists), reporting the exact paths.  Alias-aware, and a model that opts into extras
    (``extra="allow"``) is respected.

    Args:
        val: the raw payload to validate (e.g. a decoded JSON response)
        model: a pydantic v2 model class (anything exposing ``model_validate``)
        description (str, optional): the extra error message description.  Defaults to ``''``
        exact (bool, optional): also fail if the payload carries fields ``model`` does not declare.
            Defaults to ``False``

    Examples:
        Usage:

            from assertpy2 import assert_conforms, assert_that

            order = assert_conforms(response.json(), OrderModel).value  # .value: OrderModel
            assert_that(order.total).is_greater_than(0)

            # catch silent API growth: fail if the response grew fields the model does not declare
            assert_conforms(response.json(), OrderModel, exact=True)

    Returns:
        AssertionBuilder: a builder over the validated model instance, statically typed as ``model``

    Raises:
        TypeError: if ``model`` is not a pydantic v2 model class
        AssertionError: if ``val`` does not validate against ``model``, or (with ``exact``) drifts from it
    """
    if not (isinstance(model, type) and hasattr(model, "model_validate")):
        raise TypeError("assert_conforms requires a pydantic v2 model class")
    kind = "soft" if _soft_ctx.get() else None
    builder = _builder(val, description, kind)
    pydantic = sys.modules.get("pydantic")  # loaded already, since model exposes model_validate
    catchable: tuple[type[BaseException], ...] = (pydantic.ValidationError,) if pydantic is not None else ()
    try:
        # duck-typed pydantic call, guarded by the hasattr check above
        validated = model.model_validate(val)  # ty: ignore[call-non-callable]  # model_validate is dynamic
    except catchable as exc:
        return builder.error(
            f"Expected <{_truncated(str(val))}> to conform to <{model.__name__}>, but it did not:\n{exc}",
            actual=val,
            expected=model,
        )
    if exact:
        drift = contract_drift(val, model)
        if drift:
            return builder.error(
                f"Expected <{_truncated(str(val))}> to conform exactly to <{model.__name__}>, but it carries"
                f" {len(drift)} undeclared field(s) the model does not declare: {sorted(drift)}",
                actual=val,
                expected=model,
            )
    return builder.builder(validated, description, kind)


def assert_warn(val: object, description="", logger=None):
    """Set the value to be tested, and optional description and logger, and allow assertions to be
    called, but never fail, only log warnings.

    This is a factory method for the `AssertionBuilder`, but unlike [`assert_that()`][assertpy2.assertpy.assert_that] an
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
        Usage:

            from assertpy2 import assert_warn

            assert_warn('foo').is_length(4)
            assert_warn('foo').is_empty()
            assert_warn('foo').is_false()
            assert_warn('foo').is_digit()
            assert_warn('123').is_alpha()

        Even though all of the above assertions fail, ``AssertionError`` is never raised and
        test execution is never halted.  Instead, the failed assertions merely log the following
        warning messages to ``stdout``:

            2019-10-27 20:00:35 WARNING [test_foo.py:23]: Expected <foo> to be of length <4>, but was <3>.
            2019-10-27 20:00:35 WARNING [test_foo.py:24]: Expected <foo> to be empty string, but was not.
            2019-10-27 20:00:35 WARNING [test_foo.py:25]: Expected <False>, but was not.
            2019-10-27 20:00:35 WARNING [test_foo.py:26]: Expected <foo> to contain only digits, but did not.
            2019-10-27 20:00:35 WARNING [test_foo.py:27]: Expected <123> to contain only alphabetic chars, but did not.

    Tip:
        Use `assert_warn()` if and only if you have a *really* good reason to log assertion
        failures instead of failing.
    """
    return _builder(val, description, "warn", logger=logger)


def fail(msg=""):
    """Force immediate test failure with the given message.

    Args:
        msg (str, optional): the failure message.  Defaults to ``''``

    Examples:
        Fail a test:

            from assertpy2 import assert_that, fail

            def test_fail():
                fail('forced fail!')

        If you wanted to test for a known failure, here is a useful pattern:

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
    """Within a [`soft_assertions()`][assertpy2.assertpy.soft_assertions] context, append the failure
    message to the soft error list, but do not halt test execution.

    Otherwise, outside the context, acts identical to [`fail()`][assertpy2.assertpy.fail] and forces immediate test
    failure with the given message.

    Args:
        msg (str, optional): the failure message.  Defaults to ``''``

    Examples:
        Failing soft assertions:

            from assertpy2 import assert_that, soft_assertions, soft_fail

            with soft_assertions():
                assert_that(1).is_equal_to(2)
                soft_fail('my message')
                assert_that('foo').is_equal_to('bar')

        Fails, and outputs the following soft error list:

            AssertionError: soft assertion failures:
            1. Expected <1> to be equal to <2>, but was not.
            2. Fail: my message!
            3. Expected <foo> to be equal to <bar>, but was not.

    """
    if _soft_ctx.get():
        _soft_err.get().append((_soft_group.get(), f"Fail: {msg}!" if msg else "Fail!"))
        return
    fail(msg)


# assertion extensions
_extensions = {}


def add_extension(func):
    """Add a new user-defined custom assertion to assertpy.

    Once the assertion is registered with assertpy, use it like any other assertion.  Pass val to
    [`assert_that()`][assertpy2.assertpy.assert_that], and then call it.

    Args:
        func (Callable): the assertion function (to be added)

    Examples:
        Usage:

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
    if isinstance(func, types.FunctionType):
        # plain functions bind once here via the descriptor protocol, keeping assert_that() free of
        # per-call grafting; the dedicated subclass keeps AssertionBuilder itself pristine on removal
        setattr(_ExtendedBuilder, func.__name__, func)
    else:
        _extensions[func.__name__] = func


def remove_extension(func):
    """Remove a user-defined custom assertion.

    Args:
        func (Callable): the assertion function (to be removed)

    Examples:
        Usage:

            from assertpy2 import remove_extension

            remove_extension(is_5)
    """
    if not callable(func):
        raise TypeError("func must be callable")
    if func.__name__ in vars(_ExtendedBuilder):
        delattr(_ExtendedBuilder, func.__name__)
    _extensions.pop(func.__name__, None)


def _builder(val, description="", kind=None, expected=None, logger=None):
    """Internal helper to build a new `AssertionBuilder` instance and glue on any extension methods.

    Function extensions already live on `_ExtendedBuilder`; only non-function callables (which the
    descriptor protocol cannot bind) still need per-instance grafting here.
    """
    ab = _ExtendedBuilder(val, description, kind, expected, logger)
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

            previous_frame = None
            for frame in reversed(frames):
                for assertpy_filename in ASSERTPY_FILES:
                    if frame[0].endswith(assertpy_filename):
                        return previous_frame
                previous_frame = frame
            return None  # pragma: no cover - error() is always reached through an assertpy frame

        # a user file living under a directory named "assertpy2" can shadow every frame, so the
        # location prefix is skipped rather than crashing the warning
        caller = _unwind(inspect.currentframe())
        if caller is None:
            return msg, kwargs
        filename, lineno = caller
        return f"[{os.path.basename(filename)}:{lineno}]: {msg}", kwargs


_logger = logging.getLogger("assertpy2")
_handler = logging.StreamHandler(sys.stdout)
_handler.setLevel(logging.WARNING)
_format = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
_handler.setFormatter(_format)
_logger.addHandler(_handler)
_default_logger = WarningLoggingAdapter(_logger, None)


# Chain steps that transform the value instead of asserting (their failures are never AssertionError,
# so negating them can only produce a misleading "Expected ... to NOT satisfy" message).  Hybrids that
# both assert and pivot (extracting_group, matches_with_groups, when_called_with) stay negatable.
_TRANSFORMER_STEPS: Final = frozenset(
    {
        "extracting",
        "filtered_on",
        "mapped",
        "flat_mapped",
        "first",
        "last",
        "element",
        "single",
        "decoded_as",
        "at_json_path",
    }
)

# Chain steps that configure or transform instead of asserting: "inverting" them is meaningless and
# would otherwise fail later with a misleading "Expected ... to NOT satisfy" message.
_NON_NEGATABLE: Final = {
    "eventually": "eventually() cannot be negated with not_; assert the inverted condition instead",
    "eventually_sync": "eventually_sync() cannot be negated with not_; assert the inverted condition instead",
    "described_as": (
        "described_as() only sets the failure description and cannot be negated with not_;"
        " call described_as() before not_ instead"
    ),
    **{
        name: (
            f"{name}() transforms the value instead of asserting, so it cannot be negated with not_;"
            f" negate the assertion after {name}() instead"
        )
        for name in _TRANSFORMER_STEPS
    },
}


class NegatedBuilder:
    """Proxy that inverts the next assertion. Created by ``assert_that(val).not_``."""

    def __init__(self, builder: AssertionBuilder) -> None:
        self._builder = builder

    def __getattr__(self, name: str) -> object:
        if name in _NON_NEGATABLE:
            raise TypeError(_NON_NEGATABLE[name])
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
        err_list.append((_soft_group.get(), self._make_msg(name)))
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
    JsonMixin,
    HelpersMixin,
    FileMixin,
    ExtractingMixin,
    ExceptionMixin,
    WarningMixin,
    DynamicMixin,
    DictMixin,
    DateMixin,
    ContainsMixin,
    CollectionMixin,
    BytesMixin,
    DataFrameMixin,
    BaseMixin,
    Generic[_T],
):
    """The main assertion class.  Never call the constructor directly, always use the
    [`assert_that()`][assertpy2.assertpy.assert_that] helper instead.  Or if you just want warning messages, use the
    `assert_warn()` helper.

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
        self._expected_warning = None
        self._return_value = _UNSET
        # holds the failure message when an assertion on this builder collects/logs a failure under
        # soft/warn mode (first failure wins = the root cause, not its consequences); makes `.value`
        # refuse to hand back an unverified value and surface that root failure instead of silently
        # breaking its narrowed type
        self._value_taint_reason: str | None = None

    @property
    def not_(self) -> NegatedBuilder:
        """Invert the next assertion in the chain."""
        return NegatedBuilder(self)

    @property
    def value(self) -> _T:
        """The value under test, returned as-is for typed extract-and-continue.

        Ends a chain by handing the checked value back, so a test can keep using it after the
        assertions passed.  For object- and union-typed values the static type is the input type,
        refined by the narrowing assertions:
        [`is_not_none()`][assertpy2.base.BaseMixin.is_not_none] removes ``None`` from the type, and
        [`is_instance_of()`][assertpy2.base.BaseMixin.is_instance_of] narrows to the checked class -
        no ``cast()`` or bare ``assert`` needed to satisfy a type checker.

        ``value`` is a strict-mode extraction.  If an assertion on the current value failed under
        [`soft_assertions()`][assertpy2.assertpy.soft_assertions] or
        [`assert_warn()`][assertpy2.assertpy.assert_warn] - where a failure is collected or logged
        instead of halting - reading ``value`` raises ``TypeError`` rather than handing back an
        unverified value.  This guard is deliberate and **not** narrowing-specific: ``value`` hands
        back the value only when *every* assertion on it passed, so a failed ``is_equal_to`` taints it
        exactly as a failed ``is_not_none`` does (the contract is "extract only what was fully
        established").

        The taint is per-value, not for the whole chain: a value-changing step
        ([`extracting()`][assertpy2.extracting.ExtractingMixin.extracting],
        [`first()`][assertpy2.collection.CollectionMixin.first],
        [`decoded_as()`][assertpy2.bytes_mixin.BytesMixin.decoded_as], ...) begins a *new* value with a
        fresh guard.  That is still safe, because those steps validate their own input and reject
        ``None`` or an incompatible type - so a pivot can never reach ``.value`` with a value derived
        from a failed ``is_not_none()``; it raises in the pivot first.  What survives a pivot is only a
        real derived fact from a usable value (the failed assertion was an orthogonal claim), which is
        consistent with the collect-and-continue intent of soft mode.

        ``value`` and those modes are opposite intents (extract-once-established vs
        continue-past-failure), so read ``value`` in strict mode, or after the soft block has closed.

        Examples:
            Usage:

                order: Order | None = repo.find_order(42)
                paid = assert_that(order).is_not_none().is_instance_of(PaidOrder).value
                paid.refund()  # statically typed as PaidOrder

        Returns:
            object: the original value under test (never a copy)

        Raises:
            TypeError: if an assertion on this chain failed under ``soft_assertions()`` or
                ``assert_warn()``, so the value cannot be trusted to match its narrowed type; the
                message carries the underlying (root) failure so its cause is not lost
        """
        if self._value_taint_reason is not None:
            raise TypeError(
                "cannot extract .value: the underlying assertion failed under soft or warn mode - "
                f"{self._value_taint_reason} (read .value in strict mode, or after the soft-assertions block)"
            )
        return self.val

    if TYPE_CHECKING:
        # Narrowing declarations, shadowing the runtime mixin methods for type checkers only:
        # is_not_none() removes None from the tracked value type, is_instance_of() narrows it to the
        # checked class. Runtime behavior lives in BaseMixin and is unchanged.

        @overload
        def is_not_none(self: AssertionBuilder[_U | None]) -> AssertionBuilder[_U]: ...
        @overload
        def is_not_none(self) -> Self: ...
        def is_not_none(self) -> Any:  # overload impl stub required outside stub files, never executed
            ...

        # the Self overload is never picked by calls (a class arg always binds type[_U] first); it keeps
        # AssertionBuilder structurally conformant with the protocols' `(type) -> Self` contract. pyright
        # flags it reportOverlappingOverload - intentional, same category as the assert_that fallback overlap
        @overload
        def is_instance_of(self, some_class: type[_U]) -> AssertionBuilder[_U]: ...
        @overload
        def is_instance_of(self, some_class: type) -> Self: ...
        def is_instance_of(self, some_class: type) -> Any:  # overload impl stub, never executed
            ...

        # satisfies() narrows when given a `TypeIs` predicate (user-extensible refinement narrowing):
        # a predicate typed `Callable[..., TypeIs[U]]` refines the tracked value to U, so a domain
        # predicate (class + condition) narrows the chain to its target type. Solved by ty/pyright/mypy;
        # PyCharm does not yet solve TypeVars through TypeIs (tracked in JetBrains PY-89124), so this
        # narrowing is advertised as advanced/checker-dependent. Runtime behavior lives in BaseMixin.
        @overload
        def satisfies(self, matcher: Callable[[Any], TypeIs[_U]]) -> AssertionBuilder[_U]: ...
        @overload
        def satisfies(self, matcher: Matcher | Callable[..., bool]) -> Self: ...
        def satisfies(self, matcher: Any) -> Any:  # overload impl stub, never executed
            ...

    def builder(self, val, description="", kind=None, expected=None, logger=None):
        """Helper to build a new `AssertionBuilder` instance. Use this only if not chaining to ``self``.

        Args:
            val: the value to be tested (aka the actual value)
            description (str, optional): the extra error message description.  Defaults to ``''``
                (aka empty string)
            kind (str, optional): the failure mode of the assertions, one of ``None`` (raise),
                ``soft`` (collect), or ``warn`` (log).  Defaults to ``None``.  Unrelated to
                [`DiffResult.kind`][assertpy2.errors.DiffResult], which is a diff category
            expected (Error, optional): the expected exception.  Defaults to ``None``
            logger (Logger, optional): the logger for warning messages.  Defaults to ``None``
        """
        return _builder(val, description, kind, expected, logger)

    def error(self, msg, *, actual=None, expected=None, diff=None) -> Self:
        """Helper to raise an ``AssertionError`` with the given message.

        If an error description is set by [`described_as()`][assertpy2.base.BaseMixin.described_as], then that
        description is prepended to the error message.

        When structured data (``actual``, ``expected``, or ``diff``) is provided, raises
        [`AssertionFailure`][assertpy2.errors.AssertionFailure] instead of plain ``AssertionError``.

        Args:
            msg: the error message
            actual: the actual value (for structured error reporting)
            expected: the expected value (for structured error reporting)
            diff: a [`DiffResult`][assertpy2.errors.DiffResult] instance (for structured error reporting)

        Raises:
            AssertionError: always raised unless ``kind`` is ``warn`` or ``soft``.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion, but only when
                ``AssertionError`` is not raised, as is the case when ``kind`` is ``warn`` or ``soft``.
        """
        out = f"{f'[{self.description}] ' if len(self.description) > 0 else ''}{msg}"
        if self.kind == "warn":
            if self._value_taint_reason is None:
                self._value_taint_reason = out
            self.logger.warning(out)
            return self
        elif self.kind == "soft":
            if self._value_taint_reason is None:
                self._value_taint_reason = out
            _soft_err.get().append((_soft_group.get(), out))
            return self
        else:
            if expected is not None or diff is not None:
                raise AssertionFailure(out, actual=actual, expected=expected, diff=diff)
            raise AssertionError(out)

    def eventually(
        self,
        *,
        timeout: float = 5.0,
        interval: float = 0.5,
        ignoring: type[Exception] | tuple[type[Exception], ...] = (),
        trace: bool = True,
    ) -> AsyncAssertionBuilder:
        """Switch to async polling mode for eventual-consistency assertions.

        The current ``val`` must be a callable (sync or async).  Returns an
        `AsyncAssertionBuilder` whose assertion
        methods are coroutines that poll ``val()`` until the assertion passes or
        ``timeout`` expires.

        By default only a failing assertion is retried: any exception raised by ``val()`` itself
        propagates immediately.  A probe that signals "not ready yet" by raising (a connection refused
        while a service boots, a record not yet visible) can be retried too by listing those exception
        types in ``ignoring``.

        Polling itself is always strict - retrying *requires* hard failures - but the final timeout
        failure honors the builder's mode: inside
        [`soft_assertions()`][assertpy2.assertpy.soft_assertions] it is collected instead of raised,
        and under [`assert_warn()`][assertpy2.assertpy.assert_warn] it is logged.

        Args:
            timeout: maximum seconds to keep retrying (default ``5.0``)
            interval: seconds between retries (default ``0.5``)
            ignoring: an ``Exception`` subclass (or tuple of them) the polling loop retries instead of
                propagating (default: none)
            trace: record a [`PollTrace`][assertpy2.errors.PollTrace] flight recorder attached to the
                timeout failure (default ``True``); pass ``False`` to skip recording, for tight
                polling loops where per-poll snapshots of a heavy probed value are too costly

        Examples:
            Usage:

                import asyncio
                from assertpy2 import assert_that

                counter = {"n": 0}

                def get_count():
                    counter["n"] += 1
                    return counter["n"]

                asyncio.run(
                    assert_that(get_count).eventually(timeout=2).is_equal_to(3)
                )

            Retry a probe that raises while the system under test is not ready yet:

                await assert_that(get_order).eventually(timeout=10, ignoring=ConnectionError).has_status("PAID")

                # or configure fluently on the returned builder
                await assert_that(get_order).eventually().within(10).ignoring(ConnectionError).has_status("PAID")

        Returns:
            AsyncAssertionBuilder: an async builder whose assertion methods are awaitable

        Raises:
            TypeError: if ``val`` is not callable, or if ``ignoring`` contains anything that is not an
                ``Exception`` subclass
        """
        if not callable(self.val):
            raise TypeError("val must be callable when using eventually()")
        return AsyncAssertionBuilder(
            self.val,
            builder_func=_builder,
            description=self.description,
            timeout=timeout,
            interval=interval,
            ignoring=_normalize_ignoring(ignoring),
            kind=self.kind,
            logger=self.logger,
            trace=trace,
        )

    def eventually_sync(
        self,
        *,
        timeout: float = 5.0,
        interval: float = 0.5,
        ignoring: type[Exception] | tuple[type[Exception], ...] = (),
        trace: bool = True,
    ) -> SyncAssertionBuilder:
        """Switch to blocking polling mode for eventual-consistency assertions, without asyncio.

        The synchronous sibling of [`eventually()`][assertpy2.assertpy.AssertionBuilder.eventually]:
        the current ``val`` must be a sync callable, and the returned
        `SyncAssertionBuilder` exposes assertion methods
        that block the calling thread (via ``time.sleep``) while polling ``val()`` until the
        assertion passes or ``timeout`` expires - no event loop and no ``await`` needed.  A probe
        that returns an awaitable raises ``TypeError``; poll async probes with ``eventually()``.

        Retry, failure-mode, and diagnostics semantics are identical to ``eventually()``: only a
        failing assertion (or an exception type listed in ``ignoring``) is retried, the final
        timeout failure honors the builder's soft/warn mode, and it carries the same
        [`PollTrace`][assertpy2.errors.PollTrace] flight recorder.

        Args:
            timeout: maximum seconds to keep retrying (default ``5.0``)
            interval: seconds between retries (default ``0.5``)
            ignoring: an ``Exception`` subclass (or tuple of them) the polling loop retries instead of
                propagating (default: none)
            trace: record a [`PollTrace`][assertpy2.errors.PollTrace] flight recorder attached to the
                timeout failure (default ``True``); pass ``False`` to skip recording, for tight
                polling loops where per-poll snapshots of a heavy probed value are too costly

        Examples:
            Usage:

                from assertpy2 import assert_that

                counter = {"n": 0}

                def get_count():
                    counter["n"] += 1
                    return counter["n"]

                assert_that(get_count).eventually_sync(timeout=2, interval=0.1).is_equal_to(3)

            Retry a probe that raises while the system under test is not ready yet:

                assert_that(get_order).eventually_sync(timeout=10, ignoring=ConnectionError).has_status("PAID")

                # or configure fluently on the returned builder
                assert_that(get_order).eventually_sync().within(10).ignoring(ConnectionError).has_status("PAID")

        Returns:
            SyncAssertionBuilder: a blocking builder whose assertion methods poll on call

        Raises:
            TypeError: if ``val`` is not callable, or if ``ignoring`` contains anything that is not an
                ``Exception`` subclass
        """
        if not callable(self.val):
            raise TypeError("val must be callable when using eventually_sync()")
        return SyncAssertionBuilder(
            self.val,
            builder_func=_builder,
            description=self.description,
            timeout=timeout,
            interval=interval,
            ignoring=_normalize_ignoring(ignoring),
            kind=self.kind,
            logger=self.logger,
            trace=trace,
        )


class _ExtendedBuilder(AssertionBuilder[Any]):
    """Host for user extensions: `add_extension()` installs plain functions here, so binding happens
    once at registration and `AssertionBuilder` itself stays pristine when an extension is removed."""
