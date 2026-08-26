"""Assertion library for python unit testing with a fluent API"""

from __future__ import annotations

import contextvars
import logging
import os
import sys
import threading
import types
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Final, Generic, Literal, NoReturn, Protocol, TypeVar, cast, overload

if TYPE_CHECKING:
    import datetime
    import pathlib
    from collections.abc import Callable, Collection, Mapping

    from typing_extensions import TypeIs

    from ._engine._builder_check_typing import _CheckAnyValue
    from ._engine._capable_typing import _CapableAssertion
    from ._engine._compat import Self
    from ._engine._typing import (
        _ArrayAssertion,
        _ArrayT_co,
        _BoolAssertion,
        _BytesAssertion,
        _CallableAssertion,
        _CapableT,
        _ComplexAssertion,
        _DateAssertion,
        _DateTimeAssertion,
        _DictAssertion,
        _FrameAssertion,
        _FrameT_co,
        _IterableAssertion,
        _NumericAssertion,
        _ObjectAssertion,
        _PathAssertion,
        _StringAssertion,
    )
    from .errors import PollTrace
    from .matchers import Matcher

from . import _hints
from ._engine._contract import contract_drift
from ._engine._introspection import WarningLogger, is_same_implementation
from ._engine._operations import (
    CONFIGURES,
    DESCRIBES,
    POLLS,
    TRANSFORMS,
    WHAT_IT_DOES,
    WITHOUT_A_VERDICT,
)
from ._engine._path import _ROOT, _Path
from ._engine._require import argument, refuse
from .async_assertions import AsyncAssertionBuilder, SyncAssertionBuilder, _normalize_ignoring
from .base import BaseMixin
from .bytes_mixin import BytesMixin
from .collection import CollectionMixin
from .contains import ContainsMixin
from .dataframe import DataFrameMixin
from .date import DateMixin
from .dict import DictMixin
from .dynamic import DynamicMixin
from .errors import AssertionFailure, DiffEntry, DiffResult, Step, _safe_repr, _safe_str, _truncated, _windowed
from .exception import _UNSET, ExceptionMixin
from .extracting import ExtractingMixin
from .file import FileMixin
from .helpers import HelpersMixin
from .http_mixin import HttpMixin, response_note, response_of
from .json_mixin import JsonMixin
from .numeric import NumericMixin
from .outcome import MISSING, AssertionOutcome
from .snapshot import SnapshotMixin
from .string import StringMixin
from .warning import WarningMixin

__version__ = "2.23.0"

# the tracked value type of the generic AssertionBuilder fallback (_U appears only in narrowing stubs)
_T = TypeVar("_T")
# the assertion type `not_` was reached from, so an inverted step hands the same narrowed type back
_E_co = TypeVar("_E_co", covariant=True)  # the element a pivot hands back
_S = TypeVar("_S")
if TYPE_CHECKING:
    _U = TypeVar("_U")
    _E = TypeVar("_E")  # element type of a collection, so first()/element()/... narrow to it
    _R = TypeVar("_R")  # result element type after a mapping pivot
    _K = TypeVar("_K")  # dict key type, so .value keeps dict[K, V]
    _V = TypeVar("_V")  # dict value type
    _P = TypeVar("_P")  # what a probe hands back, so a polling chain asserts on that and not on `object`

    class _Extension(Protocol):
        """A function attached as an extension, which the registry keys on its own name.

        The name is part of the contract rather than incidental: `add_extension` refuses a value whose
        `__name__` is not an identifier, and `remove_extension` reads it to find what to take off.
        """

        __name__: str

        def __call__(self, *args: Any, **kwargs: Any) -> Any: ...

    class _ElementSource(Protocol[_E_co]):
        """Anything whose value is a collection of `_E_co`, however it was annotated.

        Structural because `AssertionBuilder` is invariant in `_T`: a builder over a `Sequence[int]`
        is not a builder over a `Collection[int]`, so the nominal self type bound for a mapping and
        missed every other container.
        """

        @property
        def value(self) -> Collection[_E_co]: ...


__tracebackhide__ = True  # clean tracebacks via py.test integration

# absolute paths in a set: one hash lookup a frame, and a user file of the same name cannot shadow ours
ASSERTPY_FILES: Final = frozenset(
    os.path.join(os.path.dirname(__file__), name)
    for name in os.listdir(os.path.dirname(__file__))
    if name.endswith(".py")
)


def _caller_location() -> tuple[str, int] | None:
    """The ``(filename, lineno)`` of the user frame that called into assertpy2, skipping internal frames.

    Used to locate a warn-mode warning and each collected soft-assertion failure.

    The answer is the frame just outside the *outermost* assertpy2 frame, which is why the walk cannot
    stop at the first user frame it meets going inwards: a predicate passed to `satisfies()` or `each()`
    runs inside our own call, and the line worth reporting is the assertion in the test rather than the
    lambda we invoked.  Walking outwards and keeping the last handover does the same in one pass,
    without building a list of the whole stack.

    ``None`` where no such handover exists, so a caller that cannot be located logs without the prefix
    instead of crashing on unpacking.
    """
    frame: types.FrameType | None = sys._getframe(1)  # CPython accessor; the inspect equivalent is 10x slower here
    location: tuple[str, int] | None = None
    inner_is_internal = False
    while frame:
        filename = frame.f_code.co_filename
        is_internal = filename in ASSERTPY_FILES
        if inner_is_internal and not is_internal:
            location = (filename, frame.f_lineno)
        inner_is_internal = is_internal
        frame = frame.f_back
    return location


class _SoftBlock:
    """The failures one `soft_assertions()` block is collecting, and whether it is still collecting.

    ``active`` exists because a context variable is copied *by value* into a new task: a child created
    inside the block inherits the depth and the list, and the parent's exit is invisible to it.  The
    list is shared, so the flag rides along with it and the child can see that nobody is listening any
    more.  Without it, an assertion in a task that outlived the block appended to an orphaned list and
    the test passed having checked nothing.
    """

    __slots__ = ("active", "failures")

    def __init__(self) -> None:
        self.failures: list[AssertionOutcome] = []
        self.active = True


def _collecting() -> _SoftBlock | None:
    """The block currently collecting in this context, or ``None`` when assertions should raise."""
    if not _soft_ctx.get():
        return None
    block = _soft_err.get(None)
    return block if block is not None and block.active else None


_soft_ctx: contextvars.ContextVar[int] = contextvars.ContextVar("assertpy2_soft_ctx", default=0)
# nothing about a soft failure is flattened until the aggregate message is rendered
_soft_err: contextvars.ContextVar[_SoftBlock | None] = contextvars.ContextVar("assertpy2_soft_err", default=None)
_soft_group: contextvars.ContextVar[str | None] = contextvars.ContextVar("assertpy2_soft_group", default=None)


class _Group:
    """The context `group()` hands back.

    A class rather than a `@contextlib.contextmanager` generator, and the same goes for the soft block
    itself.  A generator-based manager puts `contextlib.__exit__` on the stack, so a failure raised on
    the way out is reported against `contextlib.py` instead of the `with` line in the test.  The old
    cure was setting `__tracebackhide__` on the `contextlib` module, which fixed our two managers by
    changing how every third-party context manager in the process is reported.
    """

    __slots__ = ("_label", "_token")

    def __init__(self, label: str) -> None:
        self._label = label

    def __enter__(self) -> None:
        self._token = _soft_group.set(self._label)

    def __exit__(self, *_exc: object) -> None:
        _soft_group.reset(self._token)


class SoftAssertionCollector:
    """Collector returned by [`soft_assertions()`][assertpy2.assertpy.soft_assertions] for grouping
    errors hierarchically."""

    def group(self, label: str) -> _Group:
        """Group subsequent assertion failures under *label*.

        Examples:
            Usage:

                with soft_assertions() as sa:
                    with sa.group("Headers"):
                        assert_that(headers).contains_key("Content-Type")
                    with sa.group("Body"):
                        assert_that(body["status"]).is_equal_to("ok")
        """
        return _Group(label)


def _located(location: tuple[str, int] | None, msg: str) -> str:
    """Append ``[file:line]`` so each collected soft failure can be jumped to, matching warn-mode."""
    if location is None:  # pragma: no cover - only None when a user file shadows assertpy2 (see _caller_location)
        return msg
    return f"{msg}  [{os.path.basename(location[0])}:{location[1]}]"


# half the block form's window, because the compact form puts both sides on one line
_SCANNABLE_WIDTH = 60


def _indented_diff(diff: object, indent: str) -> list[str]:
    """Render a collected failure's diff under its entry, or nothing when it carries none."""
    # one line per differing path: a soft run exists to show many of them at once
    lines = []
    entries = getattr(diff, "entries", None) or []
    # a mapping whose only differing key is spelled "." has a step, and used to be dropped here
    only = entries[0] if len(entries) == 1 else None
    if only is not None and not only.steps and only.path == ".":
        return lines
    if only is not None and only.steps == (Step("line", 1),):
        # past this width the change cannot be found by eye, so a window around it is drawn instead
        actual_text, expected_text = _safe_str(only.actual), _safe_str(only.expected)
        if len(actual_text) <= _SCANNABLE_WIDTH and len(expected_text) <= _SCANNABLE_WIDTH:
            return lines
        near_actual, near_expected = _windowed(actual_text, expected_text, _SCANNABLE_WIDTH)
        return [f"{indent}{only.path}: {near_actual} != {near_expected}"]
    shown = entries[:5]  # bound once: a slice and a separate threshold would drift apart
    for entry in shown:
        if entry.absent == "expected":  # an extra item, which has no counterpart to contrast with
            lines.append(f"{indent}{entry.path}: {_safe_repr(entry.actual)}")
        elif entry.absent == "actual":  # a missing one
            lines.append(f"{indent}{entry.path}: {_safe_repr(entry.expected)}")
        else:
            lines.append(f"{indent}{entry.path}: {_safe_repr(entry.actual)} != {_safe_repr(entry.expected)}")
    if len(entries) > len(shown):
        lines.append(f"{indent}... and {len(entries) - len(shown)} more")
    return lines


def _format_soft_errors(errs: list[AssertionOutcome]) -> str:
    has_groups = any(outcome.group is not None for outcome in errs)
    lines = ["soft assertion failures:"]
    current_group: str | None = None
    for counter, outcome in enumerate(errs, 1):
        group = outcome.group
        if has_groups and group != current_group:
            current_group = group
            if group is not None:
                lines.append(f"  [{group}]")
        indent = ("    " if group is not None else "  ") if has_groups else ""
        # written flat, the location landed on the last line and the next entry read as a new section
        headline, *continuation = outcome.message.splitlines() or [""]
        lines.append(f"{indent}{counter}. {_located(outcome.location, headline)}")
        lines.extend(f"{indent}   {line}" for line in continuation)
        lines.extend(_indented_diff(outcome.diff, indent + "   "))
    return "\n".join(lines)


def _attach_soft_note(exc: BaseException, rendered: str) -> None:
    """Put the collected failures on *exc* without ever becoming the reason the test failed.

    This is a diagnostic hung on somebody else's exception, so every step of it is best-effort.  Three
    things can go wrong and each of them used to matter more than the note:

    * `__notes__` may already be something other than a list.  CPython's own `add_note` refuses with
      `TypeError: Cannot add note: __notes__ is not a list`, and that error replaced the exception the
      user raised, leaving theirs in `__context__`.  Exactly backwards for a mechanism whose whole job
      is not losing information;
    * a user exception type can override `add_note` with something that raises, or with something that
      is not callable at all.  `BaseException.add_note` is called unbound to step around the override;
    * the attribute may not be writable, on a type with `__slots__` or a frozen instance.

    `add_note` also arrived in 3.11 and this package supports 3.10, which the first branch covers on the
    way past: there the unbound lookup raises `AttributeError` and the assignment takes over.
    """
    try:
        BaseException.add_note(exc, rendered)  # ty: ignore[unresolved-attribute]  # absent on 3.10
        return
    except Exception:  # every failure here falls through to the assignment below
        pass
    try:
        existing = getattr(exc, "__notes__", ())
        notes = [*existing, rendered] if isinstance(existing, (list, tuple)) else [rendered]
        exc.__notes__ = notes  # ty: ignore[unresolved-attribute]  # 3.10 lacks it until set
    except Exception:  # a note is worth nothing next to the exception it annotates
        pass


class _SoftAssertions:
    """The context `soft_assertions()` hands back.  See `_Group` for why this is a class."""

    __slots__ = ()

    def __enter__(self) -> SoftAssertionCollector:
        ctx = _soft_ctx.get()
        if ctx == 0 or _soft_err.get(None) is None:
            _soft_err.set(_SoftBlock())
        _soft_ctx.set(ctx + 1)
        return SoftAssertionCollector()

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, *_rest: object) -> None:
        _soft_ctx.set(_soft_ctx.get() - 1)
        if exc_type is not None:
            # the escaping error still wins, and what was collected before it travels as a note
            if exc is not None and (block := _soft_err.get(None)) is not None and _soft_ctx.get() == 0:
                block.active = False
                errs, block.failures = block.failures, []
                if errs:
                    _attach_soft_note(exc, _format_soft_errors(errs))
            return
        block = _soft_err.get(None)
        errs = block.failures if block is not None else []
        if _soft_ctx.get() == 0 and block is not None:
            # a task still running with this block in its own context copy stops collecting
            block.active = False
            block.failures = []
        if errs and _soft_ctx.get() == 0:
            out = _format_soft_errors(errs)
            # the same class as a single failure, so one `except AssertionFailure` covers both
            raise AssertionFailure(out, failures=tuple(errs))


def soft_assertions() -> _SoftAssertions:
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
        ``AssertionError`` is raised, each tagged with the ``file:line`` it came from:

            AssertionError: soft assertion failures:
            1. Expected <foo> to be of length <4>, but was <3>.  [test_str.py:10]
            2. Expected <foo> to be empty string, but was not.  [test_str.py:11]
            3. Expected <False>, but was not.  [test_str.py:12]
            4. Expected <foo> to contain only digits, but did not.  [test_str.py:13]
            5. Expected <123> to contain only alphabetic chars, but did not.  [test_str.py:14]

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
    return _SoftAssertions()


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


@overload
def assert_that(val: str, description: str = "") -> _StringAssertion: ...


@overload
def assert_that(val: bool, description: str = "") -> _BoolAssertion: ...
@overload
def assert_that(val: int, description: str = "") -> _NumericAssertion[int]: ...


@overload
def assert_that(val: float, description: str = "") -> _NumericAssertion[float]: ...


@overload
def assert_that(val: complex, description: str = "") -> _ComplexAssertion: ...


@overload
def assert_that(val: dict[_K, _V], description: str = "") -> _DictAssertion[_K, _V]: ...


@overload
def assert_that(val: list[_E] | tuple[_E, ...], description: str = "") -> _IterableAssertion[_E]: ...


@overload
def assert_that(val: set[_E] | frozenset[_E], description: str = "") -> _IterableAssertion[_E]: ...


@overload
# a `datetime` is a `date`, so it has to be claimed first: the chronological assertions refuse a plain
# date at run time, and one view for both types offered them to one that can never answer
def assert_that(val: datetime.datetime, description: str = "") -> _DateTimeAssertion: ...


@overload
def assert_that(val: datetime.date, description: str = "") -> _DateAssertion: ...


@overload
def assert_that(val: pathlib.Path, description: str = "") -> _PathAssertion: ...


@overload
def assert_that(val: bytes, description: str = "") -> _BytesAssertion[bytes]: ...


@overload
def assert_that(val: bytearray, description: str = "") -> _BytesAssertion[bytearray]: ...


# a `pandas.DataFrame` is assignable to every structural protocol, since pandas models column access with a catch-all
# attribute, so the frame overload goes first.  `tests/test_overload_order.py` holds that order
@overload
def assert_that(val: _FrameT_co, description: str = "") -> _FrameAssertion[_FrameT_co]: ...


@overload
def assert_that(val: _ArrayT_co, description: str = "") -> _ArrayAssertion[_ArrayT_co]: ...


# the capability umbrella: below the frame pair so it cannot claim their values, above the fallback so anything with
# a recognised capability keeps the whole surface
@overload
def assert_that(val: _CapableT, description: str = "") -> _CapableAssertion[_CapableT]: ...


# below the umbrella: an ASGI or WSGI response is a callable, and this overload claimed one before the
# capability that describes it could
@overload
def assert_that(val: Callable[..., _P], description: str = "") -> _CallableAssertion[_P]: ...


# the fallback, at the price of an overload overlap mypy and pyright report and ty does not
@overload
def assert_that(val: _T, description: str = "") -> _ObjectAssertion[_T]: ...


# `Any` rather than the common base protocol, which is what this returned until the umbrella started handing back a
# protocol of its own.  Measured: checking `_CoreAssertion` against a protocol carrying the whole surface took pyright
# past its 4 GB heap and killed it on this one file.  `Any` is compatible with every overload, so nothing is reported
# where the base protocol was reported before, and the overloads above are what a caller ever sees.
def assert_that(val: object, description="") -> Any:
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
    if _collecting() is not None:
        return _builder(val, description, "soft")
    return _builder(val, description)


def _contract_entries(exc: object, prefix: _Path = _ROOT) -> list[DiffEntry]:
    """Turn a pydantic ``ValidationError`` into diff rows, mirroring the OpenAPI path in `json_mixin`.

    ``errors()`` already carries the location, the message and the offending input, so the structured
    channel costs a reshape rather than a second walk of the payload.  Under ``each=True`` the caller
    passes the element's ``[i]`` prefix, the way ``contract_drift`` labels its own paths.

    ``loc`` is already a tuple of keys and indices, so the machine half of the path comes straight
    across rather than being parsed back out of the text.
    """
    errors = exc.errors() if hasattr(exc, "errors") else []  # ty: ignore[call-non-callable]  # duck-typed pydantic
    entries = []
    for error in errors:
        path = prefix
        for segment in error.get("loc", ()):
            path = path.index(segment) if isinstance(segment, int) else path.key(segment)
        entries.append(path.leaf_entry(actual=error.get("input"), expected=error.get("msg", "")))
    return entries


@overload
def assert_conforms(
    val: object, model: type[_U], description: str = ..., *, exact: bool = ..., each: Literal[False] = ...
) -> AssertionBuilder[_U]: ...
@overload
def assert_conforms(
    val: object, model: type[_U], description: str = ..., *, exact: bool = ..., each: Literal[True]
) -> AssertionBuilder[list[_U]]: ...
def assert_conforms(
    val: object, model: type[_U], description: str = "", *, exact: bool = False, each: bool = False
) -> AssertionBuilder[Any]:
    """Validate ``val`` against a pydantic v2 ``model`` and continue over the validated instance.

    The narrowing-complete companion to [`assert_that()`][assertpy2.assertpy.assert_that] for
    contract testing.  Runs ``model.model_validate(val)``: on success the returned builder carries the
    validated, coerced instance (so ``.value`` and ``extracting`` see typed fields); on failure it
    fails with pydantic's validation errors.

    Because the return type is driven by ``model`` rather than by the type of ``val``, the chain
    narrows to ``model`` for **any** input - including the ``Any`` a decoded JSON payload carries.

    With ``exact=True`` it also asserts **contract drift**: the payload must not carry fields the model
    does not declare.  ``model_validate`` silently drops undeclared fields, so a stale model keeps
    passing after the live API grows new ones.

    ``exact`` catches that drift - recursively, into nested sub-models and lists - and reports the
    exact paths.  It is alias-aware, and respects a model that opts into extras (``extra="allow"``).

    Args:
        val: the raw payload to validate (e.g. a decoded JSON response)
        model: a pydantic v2 model class (anything exposing ``model_validate``)
        description (str, optional): the extra error message description.  Defaults to ``''``
        exact (bool, optional): also fail if the payload carries fields ``model`` does not declare.
            Defaults to ``False``
        each (bool, optional): validate a *list* payload element-by-element against ``model`` (for list
            endpoints), narrowing the chain to ``list[model]``.  ``exact`` then applies per element.
            Defaults to ``False``

    Examples:
        Usage:

            from assertpy2 import assert_conforms, assert_that

            order = assert_conforms(response.json(), OrderModel).value  # .value: OrderModel
            assert_that(order.total).is_greater_than(0)

            # catch silent API growth: fail if the response grew fields the model does not declare
            assert_conforms(response.json(), OrderModel, exact=True)

            # a list endpoint: validate every item, narrowing to list[OrderModel]
            orders = assert_conforms(response.json(), OrderModel, each=True).value  # .value: list[OrderModel]

    Returns:
        AssertionBuilder: a builder over the validated model instance, statically typed as ``model``

    Raises:
        TypeError: if ``model`` is not a pydantic v2 model class
        AssertionError: if ``val`` does not validate against ``model``, or (with ``exact``) drifts from it
    """
    if not (isinstance(model, type) and hasattr(model, "model_validate")):
        raise TypeError("assert_conforms requires a pydantic v2 model class")
    kind = "soft" if _collecting() is not None else None
    builder = _builder(val, description, kind)
    pydantic = sys.modules.get("pydantic")  # loaded already, since model exposes model_validate
    catchable: tuple[type[BaseException], ...] = (pydantic.ValidationError,) if pydantic is not None else ()
    if each:
        if not isinstance(val, (list, tuple)):
            raise TypeError("assert_conforms(each=True) requires a list or tuple payload")
        validated_items = []
        for index, item in enumerate(val):
            try:
                validated_items.append(model.model_validate(item))  # ty: ignore[call-non-callable]  # dynamic
            except catchable as exc:  # noqa: PERF203  # per-element catch reports which item failed; ~0 cost on 3.11+
                return builder.error(
                    f"Expected item [{index}] to conform to <{model.__name__}>, but it did not:\n{exc}",
                    actual=val,
                    expected=model,
                    diff=DiffResult(kind="match", entries=_contract_entries(exc, _ROOT.index(index))),
                    suppress_context=True,
                )
        if exact:
            drift = [f"[{index}].{path}" for index, item in enumerate(val) for path in contract_drift(item, model)]
            if drift:
                return builder.error(
                    f"Expected every item to conform exactly to <{model.__name__}>, but"
                    f" {len(drift)} undeclared field(s) the model does not declare: {sorted(drift)}",
                    actual=val,
                    expected=model,
                )
        return builder.builder(validated_items, description, kind)
    try:
        validated = model.model_validate(val)  # ty: ignore[call-non-callable]  # model_validate is dynamic
    except catchable as exc:
        return builder.error(
            f"Expected <{_truncated(str(val))}> to conform to <{model.__name__}>, but it did not:\n{exc}",
            actual=val,
            expected=model,
            diff=DiffResult(kind="match", entries=_contract_entries(exc)),
            suppress_context=True,
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


def assert_warn(val: object, description: str = "", logger: WarningLogger | None = None) -> Any:
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


def fail(msg: str = "") -> NoReturn:
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
    # the same class as every other failure, so a handler does not have to name two of them
    raise AssertionFailure(f"Fail: {msg}!" if msg else "Fail!")


def soft_fail(msg: str = "") -> None:
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

        Fails, and outputs the following soft error list (each tagged with its ``file:line``):

            AssertionError: soft assertion failures:
            1. Expected <1> to be equal to <2>, but was not.  [test_add.py:10]
            2. Fail: my message!  [test_add.py:11]
            3. Expected <foo> to be equal to <bar>, but was not.  [test_add.py:12]

    """
    if (block := _collecting()) is not None:
        block.failures.append(
            AssertionOutcome(
                message=f"Fail: {msg}!" if msg else "Fail!",
                group=_soft_group.get(),
                location=_caller_location(),
            )
        )
        return
    fail(msg)


_extensions = {}
# guards the check-then-set below against two threads adding the same name
_extensions_lock = threading.Lock()


# `not_` is answered inside `__getattr__` rather than declared, so it is named here
_POLLING_NAMES: Final = frozenset(
    name
    for builder in (AsyncAssertionBuilder, SyncAssertionBuilder)
    for name in vars(builder)
    if not name.startswith("_")
) | {"not_"}


def add_extension(func: _Extension, *, override: bool = False) -> None:
    """Add a new user-defined custom assertion to assertpy.

    Once the assertion is registered with assertpy, use it like any other assertion.  Pass val to
    [`assert_that()`][assertpy2.assertpy.assert_that], and then call it.

    A name already in use is refused, so an extension that would quietly replace a built-in assertion
    or another extension says so instead.  Registering the same implementation again is not a clash:
    a module-scoped ``conftest`` fixture rebuilds its function on every module that requests it.

    Args:
        func (Callable): the assertion function (to be added)
        override: replace an assertion of the same name instead of refusing

    Raises:
        TypeError: if ``func`` is not callable
        ValueError: if its ``__name__`` is not an identifier, or the name is taken and ``override``
            is false

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
        refuse(func, "callable", subject=argument("func"))
    name = getattr(func, "__name__", None)
    if not isinstance(name, str) or not name.isidentifier():
        raise ValueError(f"the assertion's __name__ must be a valid Python identifier, got {name!r}")
    # nothing to override: after `eventually()` the name is out of reach, and `override=True` bought a chain that
    # asserts nothing in silence
    if name in _POLLING_NAMES or name.startswith(("_", "cr_", "gi_")):
        raise ValueError(
            f"{name!r} is how a polling chain spells one of its own, so an extension of that name "
            f"would be unreachable after eventually(); give it another name"
        )
    with _extensions_lock:
        # re-adding the same implementation is a no-op, not a clash
        same = is_same_implementation(vars(_ExtendedBuilder).get(name), func) or is_same_implementation(
            _extensions.get(name), func
        )
        if not override and not same:
            # an extension called `is_equal_to` used to replace the core assertion in silence
            if name in vars(_ExtendedBuilder) or name in _extensions:
                raise ValueError(
                    f"an assertion named {name!r} has already been added; pass override=True to "
                    f"replace it, or remove_extension() it first"
                )
            if hasattr(AssertionBuilder, name):
                raise ValueError(
                    f"{name!r} is already defined on the assertion builder; pass override=True to "
                    f"replace it deliberately, or give the extension another name"
                )
        if isinstance(func, types.FunctionType):
            # the descriptor protocol binds once here, and the subclass keeps `AssertionBuilder` pristine on removal
            setattr(_ExtendedBuilder, name, func)
        else:
            _extensions[name] = func


def remove_extension(func: _Extension) -> None:
    """Remove a user-defined custom assertion.

    Args:
        func (Callable): the assertion function (to be removed)

    Examples:
        Usage:

            from assertpy2 import remove_extension

            remove_extension(is_5)
    """
    if not callable(func):
        refuse(func, "callable", subject=argument("func"))
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


class WarningLoggingAdapter(logging.LoggerAdapter[logging.Logger]):
    """Logging adapter to unwind the stack to get the correct callee filename and line number."""

    def process(self, msg: Any, kwargs: Any) -> tuple[Any, Any]:
        caller = _caller_location()
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


# what to do instead, per category: the register in `_engine/_operations.py` says what an operation does, and these
# say what that means for the proxy it was reached through.  `{name}` is filled in so the reader can find the call in
# their own line
_INSTEAD_OF_NEGATING: Final = {
    CONFIGURES: "negate the assertion that tests the expectation {name}() set instead",
    TRANSFORMS: "negate the assertion after {name}() instead",
    DESCRIBES: "call {name}() before not_ instead",
    POLLS: "assert the inverted condition instead",
}
_INSTEAD_OF_CHECKING: Final = {
    CONFIGURES: "ask check() for the verdict of the assertion that tests the expectation {name}() set",
    TRANSFORMS: "ask check() for the verdict of the assertion after {name}()",
    DESCRIBES: "call {name}() before check() instead",
    POLLS: "a poll delivers its own failure, so there is no verdict to hand back",
}


# the proxies themselves, reached the same way and not operations at all
_PROXY_ENTRIES: Final = {
    "check": "check() cannot be negated; call check().not_ before the assertion instead",
    "not_": "two negations cancel; drop both instead of writing not_.not_",
}


def _is_still_ours(target: object, name: str) -> bool:
    """Whether *name* on *target* is this library's own operation rather than an extension's.

    Asked of the object rather than of a global register, because the two ways an extension is applied
    have different lifetimes.  A plain function is set on `_ExtendedBuilder` and every instance sees it
    at once, but a non-function callable is grafted per instance at construction, so a builder made
    before the extension was registered keeps the built-in and one made before it was removed keeps the
    override.  Reading the registry instead let the first of those skip the refusal and then fail with
    `CollectionMixin.mapped() missing 1 required positional argument`.
    """
    return name not in vars(target) and name not in vars(_ExtendedBuilder)


def _refuse_without_a_verdict(target: object, name: str, proxy: str, remedies: dict[str, str]) -> None:
    """Raise for an operation reached through a proxy that has nothing to do with it.

    Both proxies exist to work on a verdict, so an operation that reaches none is a mistake in the
    call rather than something to invert or report.  Silently accepting one is worse than it sounds:
    `check()` answered `passed=True` for a pivot, which reads as an assertion that ran and held.
    """
    category = WITHOUT_A_VERDICT.get(name)
    # an extension over the name is somebody else's method, so the register's reason to refuse no longer applies
    if category is None or not _is_still_ours(target, name):
        return
    remedy = remedies[category].format(name=name)
    raise TypeError(f"{name}() {WHAT_IT_DOES[category]}, so it cannot be {proxy}; {remedy}")


class NegatedBuilder(Generic[_S]):
    """Proxy that inverts the next assertion. Created by ``assert_that(val).not_``.

    Generic over the assertion type it was reached from, so inverting a step returns what the
    un-inverted step would have: ``assert_that("x").not_.starts_with("y")`` stays a string assertion
    rather than collapsing to the untyped builder and letting a numeric assertion follow it.
    """

    if TYPE_CHECKING:
        # declared because a checker prefers a declared attribute over `__getattr__`, which would type this as the
        # negated method
        val: Any
        description: str
        kind: str | None
        expected: type[BaseException] | None
        logger: WarningLogger

    def __init__(self, builder: AssertionBuilder[Any]) -> None:
        self._builder = builder

    def __getattr__(self, name: str) -> Callable[..., _S]:
        _refuse_without_a_verdict(self._builder, name, "negated with not_", _INSTEAD_OF_NEGATING)
        # an extension over `check` or `not_` is somebody else's method, so it is not ours to refuse
        if name in _PROXY_ENTRIES and _is_still_ours(self._builder, name):
            raise TypeError(_PROXY_ENTRIES[name])
        attr = getattr(self._builder, name)
        if not callable(attr):
            return attr

        def _negated(*args: object, **kwargs: object) -> AssertionBuilder:
            if self._builder.kind == "soft":
                return self._negated_soft(name, attr, *args, **kwargs)
            if self._builder.kind == "warn":
                return self._negated_warn(name, attr, *args, **kwargs)
            if self._builder.kind == "check":
                return self._negated_check(name, attr, *args, **kwargs)
            return self._negated_strict(name, attr, *args, **kwargs)

        # every branch hands back the builder this proxy wraps, which cannot be said without `_builder: _S`, and an
        # unbound TypeVar has no attributes
        return _negated  # ty: ignore[invalid-return-type]  # see above

    def _make_msg(self, name: str, *args: object, **kwargs: object) -> str:
        """The negated failure, naming the call that held when it should not have.

        The arguments are in it because without them the message says which relation was asked for and
        not what it was asked about, which is the one thing the reader needs.

        Rendered here rather than by `HelpersMixin._fmt_args_kwargs()`, which spells a keyword as
        ``'key': value``: that is the shape `when_called_with()` has printed since assertpy and its
        messages are pinned to it, but this line reads as a call and ``key=value`` is what a call looks
        like.  Keyword order is the caller's, which Python preserves, so it is stable without sorting.
        """
        desc = f"[{self._builder.description}] " if self._builder.description else ""
        rendered = ", ".join(
            [_safe_repr(arg) for arg in args] + [f"{key}={_safe_repr(value)}" for key, value in kwargs.items()]
        )
        return f"{desc}Expected <{self._builder.val}> to NOT satisfy: {name}({rendered})"

    def _verdict(self, attr: Callable[..., object], *args: object, **kwargs: object) -> AssertionOutcome | None:
        """What the underlying assertion decided, or ``None`` when it held.

        Run in check mode, the one mode that hands a verdict back instead of delivering it.  That is
        what separates a verdict from an accident: anything still raised by the call came out of the
        value or out of an assertion nested inside it, and inverting *that* turns a break into a pass.

        Catching an exception class cannot make the distinction, whatever class is chosen.  A comparator
        that asserts with this library raises this library's own failure, and it is still not the
        verdict of the assertion being negated.  `_negated_check()` has always read the sink instead;
        the other three modes now do the same.
        """
        builder = self._builder
        kind, sink = builder.kind, builder._check_sink
        builder.kind = "check"
        builder._check_sink = None
        try:
            attr(*args, **kwargs)
            return builder._check_sink
        finally:
            builder.kind, builder._check_sink = kind, sink

    def _negated_strict(
        self, name: str, attr: Callable[..., object], *args: object, **kwargs: object
    ) -> AssertionBuilder:
        if self._verdict(attr, *args, **kwargs) is not None:
            return self._builder
        # composed here rather than by `error()`, which would prefix the description twice
        raise AssertionBuilder._failure(
            AssertionOutcome(message=self._make_msg(name, *args, **kwargs), actual=self._builder.val)
        )

    def _negated_soft(
        self, name: str, attr: Callable[..., object], *args: object, **kwargs: object
    ) -> AssertionBuilder:
        if self._verdict(attr, *args, **kwargs) is not None:
            return self._builder
        block = _collecting()
        err_list = block.failures if block is not None else []
        msg = self._make_msg(name, *args, **kwargs)
        if self._builder._value_taint_reason is None:
            self._builder._value_taint_reason = msg
        err_list.append(
            AssertionOutcome(
                message=msg,
                actual=self._builder.val,
                group=_soft_group.get(),
                location=_caller_location(),
            )
        )
        return self._builder

    def _negated_check(
        self, name: str, attr: Callable[..., object], *args: object, **kwargs: object
    ) -> AssertionBuilder:
        if self._verdict(attr, *args, **kwargs) is not None:
            self._builder._check_sink = None
            return self._builder
        self._builder._check_sink = AssertionOutcome(
            message=self._make_msg(name, *args, **kwargs), actual=self._builder.val
        )
        return self._builder

    def _negated_warn(
        self, name: str, attr: Callable[..., object], *args: object, **kwargs: object
    ) -> AssertionBuilder:
        if self._verdict(attr, *args, **kwargs) is not None:
            return self._builder
        msg = self._make_msg(name, *args, **kwargs)
        if self._builder._value_taint_reason is None:
            self._builder._value_taint_reason = msg
        self._builder.logger.warning(msg)
        return self._builder


class CheckBuilder:
    """Proxy returned by [`check()`][assertpy2.assertpy.AssertionBuilder.check].

    Runs one assertion with the builder in verdict mode and hands back what it decided.  The mode is
    put on and taken off around the call rather than held, so a builder that is also used normally
    afterwards is unaffected, and an assertion that raises for a bad argument still leaves it clean.

    ``not_`` is proxied rather than refused, so a negated assertion can be asked for a verdict too.
    Anything else that is not callable - ``val``, ``description`` - is handed straight back.
    """

    if TYPE_CHECKING:
        # declared because a checker prefers a declared attribute over `__getattr__`
        val: Any
        description: str

        @property
        def not_(self) -> CheckBuilder: ...

    def __init__(self, target: object, builder: AssertionBuilder[Any]) -> None:
        # two references: `not_` moves the target to the negation proxy while the mode stays underneath
        self._target = target
        self._builder = builder

    def __getattr__(self, name: str) -> Callable[..., AssertionOutcome]:
        _refuse_without_a_verdict(self._builder, name, "asked for a verdict", _INSTEAD_OF_CHECKING)
        if name == "check" and _is_still_ours(self._builder, name):
            raise TypeError("check() is already the verdict proxy; one check() is enough")
        attr = getattr(self._target, name)
        if isinstance(attr, NegatedBuilder):
            # ty: ignore[invalid-return-type]  # `not_` is declared above, where it types as a proxy;
            # this fallback is the one runtime path the annotation cannot describe
            return CheckBuilder(attr, self._builder)
        if not callable(attr):
            return attr

        def _checked(*args: object, **kwargs: object) -> AssertionOutcome:
            previous_kind = self._builder.kind
            self._builder.kind = "check"
            self._builder._check_sink = None
            try:
                attr(*args, **kwargs)
            finally:
                self._builder.kind = previous_kind
            failure = self._builder._check_sink
            self._builder._check_sink = None
            if failure is not None:
                return failure
            return AssertionOutcome(passed=True, actual=self._builder.val)

        return _checked


class AssertionBuilder(
    StringMixin,
    SnapshotMixin,
    NumericMixin,
    JsonMixin,
    HttpMixin,
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

    def __init__(
        self,
        val: Any,
        description: str = "",
        kind: str | None = None,
        expected: type[BaseException] | None = None,
        logger: WarningLogger | None = None,
    ) -> None:
        """Never call this constructor directly."""
        self.val = val
        self.description = description
        self.kind = kind
        self.expected = expected
        self.logger: WarningLogger = logger or _default_logger
        self._not_expected = False
        self._expected_warning = None
        self._return_value = _UNSET
        self._raised_exception = _UNSET
        # `.value` refuses an unverified value and names the root cause rather than breaking its type in silence
        self._value_taint_reason: str | None = None
        self._value_origin: str | None = None
        # where a failure lands while `check()` has this builder in verdict mode
        self._check_sink: AssertionOutcome | None = None

    @property
    def not_(self) -> NegatedBuilder[Self]:
        """Invert the next assertion in the chain."""
        return NegatedBuilder(self)

    def check(self) -> _CheckAnyValue[_T]:
        """Run the next assertion for its verdict instead of for its failure.

        The assertion does not raise, collect or log.  It returns an
        [`AssertionOutcome`][assertpy2.outcome.AssertionOutcome], truthy when it held and carrying the
        failure message, values and diff when it did not.

        For asking a question about a value.  An assertion states a requirement, and a test that stops
        at the first unmet one is the point; this is for the cases that are not that, like branching on
        a precondition, or reporting a check into a system that is not pytest.

        A bad argument still raises.  ``TypeError`` and ``ValueError`` mean the call itself is wrong,
        which is not a verdict about the value and would be silenced by returning one.

        Examples:
            Usage:

                outcome = assert_that(response).check().is_equal_to(expected)
                if not outcome:
                    logger.warning(outcome.message)

                assert_that(5).check().is_positive().passed        # True
                assert_that(5).check().not_.is_positive().passed   # False
        """
        # the proxy resolves every name through `__getattr__`, which is what the declared twin
        # describes: the twin is the shape, `CheckBuilder` is the thing
        return cast("_CheckAnyValue[_T]", CheckBuilder(self, self))

    @property
    def value(self) -> _T:
        """The value under test, returned as-is for typed extract-and-continue.

        Ends a chain by handing the checked value back, so a test can keep using it after the
        assertions passed.  For object- and union-typed values the static type is refined by the
        narrowing assertions along the way:
        [`is_not_none()`][assertpy2.base.BaseMixin.is_not_none] removes ``None`` and
        [`is_instance_of()`][assertpy2.base.BaseMixin.is_instance_of] narrows to the checked class, so
        no ``cast()`` or bare ``assert`` is needed to satisfy a type checker.

        ``value`` is a strict-mode extraction: it hands the value back only when *every* assertion on
        it passed.  If one failed under
        [`soft_assertions()`][assertpy2.assertpy.soft_assertions] or
        [`assert_warn()`][assertpy2.assertpy.assert_warn] - where failures are collected, not raised -
        reading ``value`` raises ``TypeError`` instead of returning an unverified value.  Read it in
        strict mode, or after the soft block has closed.

        The taint is per-value, not per-chain.  A value-changing pivot
        ([`extracting()`][assertpy2.extracting.ExtractingMixin.extracting],
        [`first()`][assertpy2.collection.CollectionMixin.first],
        [`decoded_as()`][assertpy2.bytes_mixin.BytesMixin.decoded_as], ...) starts a *new* value with a
        fresh guard and validates its own input, so a pivot never reaches ``.value`` with a value
        derived from a failed assertion - it raises in the pivot first.

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
        # narrowing declarations for checkers only; the runtime behaviour lives in `BaseMixin`

        @overload
        def is_not_none(self: AssertionBuilder[_U | None]) -> AssertionBuilder[_U]: ...
        @overload
        def is_not_none(self) -> Self: ...
        def is_not_none(self) -> Any: ...

        # never picked by a call, and it keeps the class conformant with the protocols' `(type) -> Self`; pyright
        # reports the overlap and that is intended
        @overload
        def is_instance_of(self, some_class: type[_U]) -> AssertionBuilder[_U]: ...
        @overload
        def is_instance_of(self, some_class: type) -> Self: ...
        def is_instance_of(self, some_class: type) -> Any: ...

        # the element pivots: the runtime returns `self.builder(<an element>)` while `CollectionMixin` declares `->
        # Self`, so `assert_that(rows).first().value.count(1)` type-checked and raised.  The self type is structural
        # because `_T` is invariant, and the nominal spelling bound for a mapping and missed every other container
        @overload
        def first(self: AssertionBuilder[Mapping[_K, _V]]) -> AssertionBuilder[_K]: ...
        @overload
        def first(self: _ElementSource[_E]) -> AssertionBuilder[_E]: ...
        @overload
        def first(self) -> Self: ...
        def first(self) -> Any: ...

        @overload
        def last(self: AssertionBuilder[Mapping[_K, _V]]) -> AssertionBuilder[_K]: ...
        @overload
        def last(self: _ElementSource[_E]) -> AssertionBuilder[_E]: ...
        @overload
        def last(self) -> Self: ...
        def last(self) -> Any: ...

        @overload
        def element(self: AssertionBuilder[Mapping[_K, _V]], index: int) -> AssertionBuilder[_K]: ...
        @overload
        def element(self: _ElementSource[_E], index: int) -> AssertionBuilder[_E]: ...
        @overload
        def element(self, index: int) -> Self: ...
        def element(self, index: int) -> Any: ...

        # `mapped()` for the same reason and with one more of its own: it builds a `list` whatever it
        # was given, so `-> Self` is wrong about the container as well as about the element.  It also
        # rejects working code rather than only accepting broken code:
        # `assert_that(rows).mapped(str).value[0].upper()` runs and was refused, because `.value` was
        # declared as the input rather than as the list that comes back.
        #
        # `mapped()` carries a smaller version of the same limit, worth knowing before relying on it:
        # a named function binds `_R` under both checkers, a lambda binds it under ty and comes back
        # `AssertionBuilder[Any]` under mypy.  That loses precision rather than rejecting anything, so
        # it is a boundary rather than the reason the two below are absent.
        #
        # `filtered_on()` and `flat_mapped()` are deliberately not declared here, and the reason is
        # measured.  A predicate parameter spelled `Matcher[_E] | Callable[[_E], object]` gives a
        # lambda nothing to bind against, so `filtered_on(lambda item: True)` came back `Unknown` under
        # ty and `Any` under mypy; `flat_mapped()` resolved under ty and stayed `Any` under mypy.  One
        # answer from three checkers is the bar, and neither reaches it.  A caller who wants them typed
        # reaches them through a curated view, where the element is already bound.
        @overload
        def mapped(self: _ElementSource[_E], func: Callable[[_E], _R]) -> AssertionBuilder[list[_R]]: ...
        @overload
        def mapped(self, func: Callable[..., Any]) -> Self: ...
        def mapped(self, func: Any) -> Any:  # overload impl stub, never executed
            ...

        @overload
        def single(self: AssertionBuilder[Mapping[_K, _V]]) -> AssertionBuilder[_K]: ...
        @overload
        def single(self: _ElementSource[_E]) -> AssertionBuilder[_E]: ...
        @overload
        def single(self) -> Self: ...
        def single(self) -> Any:  # overload impl stub, never executed
            ...

        # a `TypeIs` predicate narrows the chain to its target type.  Solved by ty, pyright and mypy;
        # PyCharm does not solve TypeVars through `TypeIs` yet (JetBrains PY-89124)
        @overload
        def satisfies(self, matcher: Callable[[Any], TypeIs[_U]]) -> AssertionBuilder[_U]: ...
        @overload
        def satisfies(self, matcher: Matcher[Any] | Callable[..., bool]) -> Self: ...
        def satisfies(self, matcher: Any) -> Any:  # overload impl stub, never executed
            ...

    def builder(
        self,
        val: Any,
        description: str = "",
        kind: str | None = None,
        expected: type[BaseException] | None = None,
        logger: WarningLogger | None = None,
        origin: str | None = None,
    ) -> Any:
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
        pivoted = _builder(val, description, kind, expected, logger)
        pivoted._value_origin = origin
        # the response this value came from, kept across the pivot: by the time an assertion on a parsed
        # body fails, the response itself is out of reach of everything downstream
        # `is not None` and not `or`: a `requests.Response` is falsey for every 4xx and 5xx, which is
        # exactly the response whose provenance a reader needs
        pivoted._response = self._response if self._response is not None else response_of(self.val)
        return pivoted

    def error(
        self,
        msg: str,
        *,
        actual: Any = MISSING,
        expected: Any = MISSING,
        diff: DiffResult | None = None,
        trace: PollTrace | None = None,
        suppress_context: bool = False,
    ) -> Self:
        """Helper to raise an ``AssertionError`` with the given message.

        If an error description is set by [`described_as()`][assertpy2.base.BaseMixin.described_as], then that
        description is prepended to the error message.

        Always raises [`AssertionFailure`][assertpy2.errors.AssertionFailure], which is an
        ``AssertionError``.  Structured data (``actual``, ``expected``, ``diff``) is carried on it when
        given, and the class is the same either way, which is why nothing reads the class to learn who
        raised it: `NegatedBuilder._verdict()` asks in check mode instead.

        Args:
            msg: the error message
            actual: the actual value (for structured error reporting)
            expected: the expected value (for structured error reporting)
            diff: a [`DiffResult`][assertpy2.errors.DiffResult] instance (for structured error reporting)
            trace: a [`PollTrace`][assertpy2.errors.PollTrace] from a poll that timed out
            suppress_context: raise ``from None``, dropping the exception currently being handled from
                the traceback.  Pass it when the caught exception is your own plumbing and its text is
                already folded into ``msg``, so the reader is not shown the same failure twice.  Leave
                it alone when the caught exception is the caller's, which is context they want.

        Raises:
            AssertionFailure: unless ``kind`` is ``warn``, ``soft`` or ``check``, which log it, collect
                it and record it respectively.

        Returns:
            AssertionBuilder: this instance, to chain the next assertion, whenever the failure was
                delivered some other way than by raising.
        """
        failure = self._deliver(self._compose(msg, actual=actual, expected=expected, diff=diff, trace=trace))
        if failure is None:
            return self
        # the raise stays here rather than in _deliver: a failing assertion's traceback ends at
        # `error`, and tests/test_traceback.py pins that it is exactly three frames deep
        if suppress_context:
            raise failure from None
        raise failure

    def _compose(
        self, msg: str, *, actual: object, expected: object, diff: DiffResult | None, trace: PollTrace | None
    ) -> AssertionOutcome:
        """Build the failure record.  Decides nothing about what happens to it."""
        # every message in the library reads "Expected <val> to ...", so the subject of a failure is
        # the value under test whether or not the assertion bothered to name it. filling it here is
        # what puts it on all 163 failures instead of the 34 that pass it explicitly
        provided = actual is not MISSING
        out = f"{f'[{self.description}] ' if len(self.description) > 0 else ''}{msg}"
        if self._value_origin and not len(self.val):
            # an empty derived value carries no context of its own, so name the step that produced it
            out = f"{out} The value is empty because {self._value_origin}."
        hint = _hints.diagnose(diff, actual, expected, identity=self._equality_comparison)
        if hint is not None:
            # on its own line, like the comparison-settings echo, so the original message stays a
            # prefix and a `match=` or `startswith` written against it keeps working
            out = f"{out}\n{hint}"
        response = self._response if self._response is not None else response_of(self.val)
        note = response_note(response) if response is not None else None
        if note is not None:
            # last, under the explanation: it says where the value came from, not why it differs
            out = f"{out}\n{note}"
        return AssertionOutcome(
            message=out,
            actual=actual if provided else self.val,
            actual_provided=provided,
            expected=expected,
            diff=diff,
            trace=trace,
            hint=hint,
        )

    def _deliver(self, outcome: AssertionOutcome) -> AssertionError | None:
        """Act on a composed failure according to the builder's mode.

        Returns the exception the caller should raise, or ``None`` when the failure was collected or
        logged instead.  Raising is left to `error()` so the traceback keeps its shape.
        """
        if self.kind == "warn":
            if self._value_taint_reason is None:
                self._value_taint_reason = outcome.message
            detail = _indented_diff(outcome.diff, "   ")
            self.logger.warning("\n".join([outcome.message, *detail]) if detail else outcome.message)
            return None
        if self.kind == "soft":
            block = _collecting()
            if block is None:
                # the block this builder was made under has since closed, which happens when a task
                # created inside it outlives it: the context copy still says "soft", and appending here
                # would put the failure in a list nobody reads. Failing is the honest answer
                return self._failure(outcome)
            if self._value_taint_reason is None:
                self._value_taint_reason = outcome.message
            block.failures.append(replace(outcome, group=_soft_group.get(), location=_caller_location()))
            return None
        if self.kind == "check":
            # no taint: a verdict was asked for, not asserted.  One assignment rather than a first-wins
            # guard, since every `self.error(...)` in the package returns at once
            self._check_sink = outcome
            return None
        return self._failure(outcome)

    @staticmethod
    def _failure(outcome: AssertionOutcome) -> AssertionFailure:
        """Build the exception for a composed failure.

        One class for every failure.  The older split raised a bare `AssertionError` whenever the
        assertion had named no expected value and built no diff, which is most of them, so whether a
        caught failure carried structure at all depended on which assertion had failed.

        Separate from `_deliver` for the one caller that composes its own message: `NegatedBuilder`
        inverts by catching, so its own failure is the case where nothing was caught.
        """
        failure = AssertionFailure(
            outcome.message,
            actual=outcome.actual,
            expected=None if outcome.expected is MISSING else outcome.expected,
            diff=outcome.diff,
        )
        failure._outcome = outcome
        return failure

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

        By default only a failing assertion is retried: any other exception raised by ``val()`` itself
        propagates immediately.  An ``AssertionError`` from ``val()`` reaches the same place a failing
        assertion does and is retried the same way, which the timeout message names.  A probe that
        signals "not ready yet" by raising something else (a connection refused while a service boots,
        a record not yet visible) can be retried too by listing those types in ``ignoring``.

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
            refuse(self.val, "callable, since eventually() polls it")
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
            refuse(self.val, "callable, since eventually_sync() polls it")
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
