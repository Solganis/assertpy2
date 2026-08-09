"""Runtime-checkable protocols for duck-typed object introspection.

The comparison and diff code accepts arbitrary user objects, so it inspects them structurally: pydantic
models (``model_dump``), ``attrs`` classes (``__attrs_attrs__``) and namedtuples (``_fields`` /
``_asdict``).  Expressing those shapes as ``@runtime_checkable`` protocols lets the diff code use
``isinstance`` checks the type checker can follow - narrowing the value instead of probing it with
``hasattr`` and then suppressing the attribute access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, Protocol, TypeGuard, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable

_T = TypeVar("_T")

# Exact builtin types whose instances cannot carry protocol members (no instance ``__dict__``), so the
# expensive ``runtime_checkable`` isinstance (getattr_static per member) is skipped for them.  Exact
# types only: subclasses always take the full structural check.
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


@runtime_checkable
class MappingLike(Protocol):
    """A dict-like object that can be iterated over and subscripted by key."""

    def keys(self) -> Any: ...

    def __iter__(self) -> Any: ...

    def __getitem__(self, key: Any) -> Any: ...


def is_model_dump_object(obj: object) -> TypeGuard[SupportsModelDump]:
    """Return whether ``obj`` exposes a callable ``model_dump()`` (e.g. a pydantic model)."""
    if type(obj) is dict or type(obj) in _ATOMIC_TYPES:
        return False
    return isinstance(obj, SupportsModelDump) and callable(obj.model_dump)


def is_namedtuple(obj: object) -> TypeGuard[NamedTupleLike]:
    """Return whether ``obj`` is a namedtuple instance (a ``tuple`` carrying ``_fields``/``_asdict``)."""
    return isinstance(obj, tuple) and isinstance(obj, NamedTupleLike)


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
    return not isinstance(obj, type) and isinstance(obj, AttrsInstance)


def is_mapping_like(obj: object) -> TypeGuard[MappingLike]:
    """Return whether ``obj`` is dict-like: iterable with ``keys()`` and ``[]`` access."""
    if type(obj) is dict:
        return True
    if type(obj) in _ATOMIC_TYPES:
        return False
    return isinstance(obj, MappingLike) and callable(obj.keys)


def is_same_implementation(existing: object, candidate: object) -> bool:
    """Whether two registrations are the same implementation rather than two claiming one name.

    Object identity is too strict.  A ``def`` inside a pytest fixture builds a new function object
    every time the fixture runs, and a module-scoped fixture in ``conftest.py`` is the documented way
    to share an extension across test files, so that shape would otherwise look like a clash on the
    second module.  CPython reuses the enclosing code object across those rebuilds, and it differs the
    moment the body does, which is exactly the line wanted here.

    Callables without a ``__code__`` (instances with ``__call__``, builtins, partials) fall back to
    identity, which is the strictest answer available for them.
    """
    if existing is candidate:
        return True
    left = getattr(existing, "__code__", None)
    return left is not None and left is getattr(candidate, "__code__", None)


def materialized(value: Iterable[_T]) -> Iterable[_T]:
    """``value``, drained into a list when it is a one-shot iterator, handed back untouched otherwise.

    An object that is its own iterator (a generator, a file, ``map``/``filter``/``zip``) is consumed by
    the first pass over it.  Assertions that walk their subject more than once - once to decide and
    again to describe, or once per argument - therefore see an empty value on the second pass, and
    either report a wrong verdict or a message with the wrong contents in it.

    Re-iterable values are returned as they are, so nothing is copied on the ordinary path.  A value
    that cannot be iterated at all is also returned as it is, leaving the caller's own guard to produce
    the error message it wants.
    """
    try:
        return list(value) if iter(value) is value else value
    except TypeError:
        return value
