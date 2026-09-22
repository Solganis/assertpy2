"""Runtime-checkable protocols for duck-typed object introspection.

The comparison and diff code accepts arbitrary user objects, so it inspects them structurally: pydantic
models (``model_dump``), ``attrs`` classes (``__attrs_attrs__``) and namedtuples (``_fields`` /
``_asdict``).  Expressing those shapes as ``@runtime_checkable`` protocols lets the diff code use
``isinstance`` checks the type checker can follow - narrowing the value instead of probing it with
``hasattr`` and then suppressing the attribute access.
"""

from __future__ import annotations

import collections
import itertools
import types
from typing import TYPE_CHECKING, Any, Final, Protocol, TypeGuard, TypeVar, cast, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from types import CellType

_T = TypeVar("_T")

# exact builtins carrying no `__dict__`, so the isinstance is skipped; a subclass takes the structural check
_ATOMIC_TYPES: Final = frozenset(
    {type(None), bool, int, float, complex, str, bytes, bytearray, list, tuple, set, frozenset}
)


@runtime_checkable
class SupportsModelDump(Protocol):
    """A pydantic-style model exposing ``model_dump()``."""

    def model_dump(self) -> dict[str, Any]: ...


@runtime_checkable
class NamedTupleLike(Protocol):
    """A ``collections.namedtuple`` / ``typing.NamedTuple`` instance."""

    _fields: tuple[str, ...]

    def _asdict(self) -> dict[str, Any]: ...


@runtime_checkable
class AttrsInstance(Protocol):
    """An ``attrs``-decorated instance exposing ``__attrs_attrs__``."""

    __attrs_attrs__: tuple[Any, ...]


class WarningLogger(Protocol):
    """What a warning-mode assertion asks of a logger: the one method it calls when an assertion fails.

    Structural rather than either concrete type, because both are promised and both work.  The
    docstring of `assert_warn` says `Logger`, the default the builder installs is a `LoggerAdapter`,
    and naming one of them in the signature refuses the other for no reason the runtime shares.

    Widest on both sides.  `str` because a logger declared to take only a string is a working one and
    the message here is always a string, and `object` because a return this never reads is not a
    reason to refuse a logger that has one.
    """

    def warning(self, msg: str) -> object: ...


@runtime_checkable
class Readable(Protocol):
    """A file-like object, recognised by the one method that reads it whole.

    The return is spelled out because the caller promises a `str`: a text handle answers with one and a
    binary handle with `bytes`, which is decoded, and a reader that answers with neither would be
    handed straight back through a signature that says `str`.
    """

    def read(self) -> str | bytes: ...


@runtime_checkable
class MappingLike(Protocol):
    """A dict-like object that can be iterated over and subscripted by key."""

    def keys(self) -> Any: ...

    def __iter__(self) -> Any: ...

    def __getitem__(self, key: Any, /) -> Any: ...  # positional, so a plain `dict` satisfies it


def is_model_dump_object(obj: object) -> TypeGuard[SupportsModelDump]:
    """Return whether ``obj``'s type exposes a callable ``model_dump()`` (e.g. a pydantic model)."""
    if type(obj) is dict or type(obj) in _ATOMIC_TYPES:
        return False
    # on the type first, which a `unittest.mock` object's fabricated attribute never reaches; then on the
    # value, because an ordinary method is a non-data descriptor and `obj.model_dump = None` shadows it
    return hasattr(type(obj), "model_dump") and callable(getattr(obj, "model_dump", None))


def is_namedtuple(obj: object) -> TypeGuard[NamedTupleLike]:
    """Return whether ``obj`` is a namedtuple instance (a ``tuple`` whose type carries the whole surface).

    Both ``_fields`` and ``_asdict``, because the callers use both: a ``tuple`` subclass with a bare
    ``_fields`` is not one, and asking for only that let it through.

    Asked of the type and not the instance, as its two neighbours are and for the same reason.  A
    ``unittest.mock`` object fabricates every attribute through ``__getattr__``, so it answered all three
    of these and the diff walk read a call's own elements as field names, then as keys.  Its class
    carries none of them.

    Cheaper as well as narrower: a ``runtime_checkable`` protocol was measured here at 876 ns against
    41 ns for the attribute, on the walk that asks this about every differing element.
    """
    return isinstance(obj, tuple) and hasattr(type(obj), "_fields") and hasattr(type(obj), "_asdict")


def is_attrs_instance(obj: object) -> TypeGuard[AttrsInstance]:
    """Return whether ``obj`` is an ``attrs``-decorated instance (not the class itself, which also
    carries ``__attrs_attrs__`` but has no field values to read).

    The atomic fast path is the same one its two neighbours above have, and it was the one predicate
    missing it.  That mattered out of proportion to the line: the diff walk asks this about every
    differing element, and a profile of a 2000-element sequence diff put 39% of the whole walk inside
    the ``runtime_checkable`` isinstance this skips.
    """
    if type(obj) in _ATOMIC_TYPES:
        return False
    return not isinstance(obj, type) and hasattr(type(obj), "__attrs_attrs__")


def is_mapping_like(obj: object) -> TypeGuard[MappingLike]:
    """Return whether ``obj`` is dict-like: iterable with ``keys()`` and ``[]`` access."""
    if type(obj) is dict:
        return True
    if type(obj) in _ATOMIC_TYPES:
        return False
    return isinstance(obj, MappingLike) and callable(obj.keys)


def keyed_snapshot(candidate: object) -> MappingLike | None:
    """*candidate* as something safe to walk by key, or `None` when it cannot be walked that way.

    Iteration yields keys for a mapping and values for a sequence, and no test of the type tells which a
    duck-typed value does.  `unittest.mock.call_args` is a tuple subclass answering `keys`, so a renderer
    walked it for keys, got its items and indexed the tuple with one.

    A snapshot rather than a yes-or-no answer, because a probe and the walk that follows it are two
    readings of the same value: an iterator that yields `0` on the first pass and `"bad"` on the second
    passes the probe and raises in the walk.  Reading once and rendering from what was read closes that.

    Only a `dict` is handed back as it is.  Registering as a `Mapping` promises an interface and not
    stability between reads, so a custom one is snapshotted like anything else.
    """
    if type(candidate) is dict:
        return cast("MappingLike", candidate)
    keyed = cast("MappingLike", candidate)
    try:
        # an OrderedDict stays one, since its `==` reads the order a plain dict would forget
        snapshot = collections.OrderedDict() if isinstance(candidate, collections.OrderedDict) else {}
        snapshot.update((key, keyed[key]) for key in keyed)
    except Exception:
        return None
    return snapshot


def is_same_implementation(existing: object, candidate: object) -> bool:
    """Whether two registrations are the same implementation rather than two claiming one name.

    Object identity is too strict.  A ``def`` inside a pytest fixture builds a new function object
    every time the fixture runs, and a module-scoped fixture in ``conftest.py`` is the documented way
    to share an extension across test files, so that shape would otherwise look like a clash on the
    second module.  CPython reuses the enclosing code object across those rebuilds, and it differs the
    moment the body does, which is exactly the line wanted here.

    Callables without a ``__code__`` (instances with ``__call__``, builtins, partials) fall back to
    identity, which is the strictest answer available for them.

    A decorator's wrapper shares its code with everything that decorator wraps, so the functions a
    wrapper holds, in its closure, its defaults or its ``__wrapped__``, are compared the same way: two
    wrappers are one implementation only if what they wrap is.  Anything else they hold is data and is
    not compared, a callable without code (a builtin, a partial, a mock) included.  A fixture rebuilding
    its function carries fresh data every time, and the latest registration replacing the earlier one
    is the point of accepting it.
    """
    return _same_implementation(existing, candidate, set())


def _same_implementation(existing: object, candidate: object, seen: set[tuple[int, int]]) -> bool:
    if existing is candidate:
        return True
    left = getattr(existing, "__code__", None)
    if left is None or left is not getattr(candidate, "__code__", None):
        return False
    # a closure that holds its own function reaches this pair again
    if (id(existing), id(candidate)) in seen:
        return True
    seen.add((id(existing), id(candidate)))
    return all(
        _same_implementation(inner, other, seen)
        for inner, other in _held(existing, candidate)
        if isinstance(inner, types.FunctionType) or isinstance(other, types.FunctionType)
    )


def _held(existing: object, candidate: object) -> Iterator[tuple[object, object]]:
    """What two functions of one code object hold, side by side: closure cells, defaults, what they wrap."""
    # one code object, so one set of free variables on both sides
    cells = zip(
        getattr(existing, "__closure__", None) or (), getattr(candidate, "__closure__", None) or (), strict=True
    )
    yield from ((_cell_contents(mine), _cell_contents(theirs)) for mine, theirs in cells)
    yield from itertools.zip_longest(
        getattr(existing, "__defaults__", None) or (), getattr(candidate, "__defaults__", None) or ()
    )
    mine, theirs = getattr(existing, "__kwdefaults__", None) or {}, getattr(candidate, "__kwdefaults__", None) or {}
    yield from ((mine.get(name), theirs.get(name)) for name in mine.keys() | theirs.keys())
    yield getattr(existing, "__wrapped__", None), getattr(candidate, "__wrapped__", None)


def _cell_contents(cell: CellType) -> object:
    """What a closure cell holds, or ``None`` for one not yet filled."""
    try:
        return cell.cell_contents
    except ValueError:
        return None


def materialized(value: Iterable[_T]) -> Iterable[_T]:
    """``value``, drained into a list when it is a one-shot iterator, handed back untouched otherwise.

    An object that is its own iterator (a generator, a file, ``map``/``filter``/``zip``) is consumed by
    the first pass over it.  Assertions that walk their subject more than once - once to decide and
    again to describe, or once per argument - therefore see an empty value on the second pass, and
    either report a wrong verdict or a message with the wrong contents in it.

    Re-iterable values are returned as they are, so nothing is copied on the ordinary path.  A value
    that cannot be iterated at all is also returned as it is, leaving the caller's own guard to produce
    the error message it wants.

    Being its own iterator is not the only way to have one position: a wrapper handing out one shared
    iterator answers no here and still loses what a first walk read, so ``satisfies()`` over one
    reports the remainder rather than the value.  That is left uncaught on purpose.  Copying anything
    that merely lacks a length instead turns a Pydantic model into a list of its field pairs, and
    walking one to find out costs the position when the position is shared.
    """
    try:
        return list(value) if iter(value) is value else value
    except TypeError:
        return value


def definition_of(klass: type, name: str) -> tuple[type, object] | None:
    """The class in *klass*'s tree that defines *name*, and the definition itself, or ``None``.

    Walked and read raw, which is the reading the interpreter does for an operator: no attribute access
    on the class, so neither a metaclass nor a descriptor of the class's own gets to answer for it.

    A definition of ``None`` reads as no definition, so a class declaring `__hash__ = None` reports the
    hashable base above it.  Callers that care ask the class about `__hash__` directly, which is the
    cheaper question anyway.
    """
    for base in type.__getattribute__(klass, "__mro__"):
        found = type.__getattribute__(base, "__dict__").get(name)
        if found is not None:
            return base, found
    return None
