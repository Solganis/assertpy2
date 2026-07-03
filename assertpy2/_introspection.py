"""Runtime-checkable protocols for duck-typed object introspection.

The comparison and diff code accepts arbitrary user objects, so it inspects them structurally: pydantic
models (``model_dump``), ``attrs`` classes (``__attrs_attrs__``) and namedtuples (``_fields`` /
``_asdict``).  Expressing those shapes as ``@runtime_checkable`` protocols lets the diff code use
``isinstance`` checks the type checker can follow - narrowing the value instead of probing it with
``hasattr`` and then suppressing the attribute access.
"""

from __future__ import annotations

from typing import Any, Final, Protocol, TypeGuard, runtime_checkable

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
    """Return whether ``obj`` is an ``attrs``-decorated instance."""
    return isinstance(obj, AttrsInstance)


def is_mapping_like(obj: object) -> TypeGuard[MappingLike]:
    """Return whether ``obj`` is dict-like: iterable with ``keys()`` and ``[]`` access."""
    if type(obj) is dict:
        return True
    if type(obj) in _ATOMIC_TYPES:
        return False
    return isinstance(obj, MappingLike) and callable(obj.keys)
