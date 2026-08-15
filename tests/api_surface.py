"""What the package promises, in a form two revisions can be compared by.

The neighbouring guards each answer a different question. `test_public_surface` holds a hand-written
list of exported names and record fields, `test_protocol_parity` holds the typed surface against the
runtime, `test_typing` pins overload resolution. None of them notices a *signature* moving: a parameter
renamed, a default removed, a keyword becoming positional. Those are exactly the changes that break a
caller silently, and they are what this module collects.

The collection is derived rather than hand-written, unlike the name list next door, and that is a
deliberate difference. A hand-written list of two hundred and fifty signatures would not be read on
review; a generated snapshot with a reviewable diff is. What keeps it honest is that the snapshot is
committed: changing the package without changing the snapshot fails, and changing the snapshot shows up
in the diff as its own decision.
"""

from __future__ import annotations

import contextlib
import dataclasses
import inspect
import pathlib
from typing import Any

import assertpy2
from assertpy2.assertpy import AssertionBuilder

# what a caller can reach without touching a private name: the package's own exports, every public
# attribute of the builder every chain ends up on, and the matcher factories a spec is written with
_MATCHER_PROTOCOL = ("matches", "describe", "describe_mismatch")


def _parameters(target: Any) -> list[dict[str, Any]]:
    """Each parameter as the four things a caller can break on."""
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):  # a builtin or a C function with no introspectable signature
        return []
    return [
        {
            "name": name,
            "kind": parameter.kind.name,
            "required": parameter.default is inspect.Parameter.empty
            and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD),
            "annotation": _text(parameter.annotation, inspect.Parameter.empty),
        }
        for name, parameter in signature.parameters.items()
        if name != "self"
    ]


def _text(annotation: Any, empty: Any) -> str | None:
    """An annotation as a stable string, or ``None`` when there is none.

    Stringified rather than kept as an object so the snapshot survives being written to JSON and read
    back, and so a diff shows the change rather than a repr with a memory address in it.
    """
    if annotation is empty:
        return None
    if isinstance(annotation, str):
        return annotation
    return getattr(annotation, "__name__", None) or str(annotation)


def _callable_entry(target: Any) -> dict[str, Any]:
    signature_return = inspect.Signature.empty
    with contextlib.suppress(TypeError, ValueError):  # a builtin with no introspectable signature
        signature_return = inspect.signature(target).return_annotation
    return {
        "kind": "callable",
        "parameters": _parameters(target),
        "returns": _text(signature_return, inspect.Signature.empty),
    }


def _member_entry(owner: type, name: str) -> dict[str, Any]:
    attribute = inspect.getattr_static(owner, name)
    if isinstance(attribute, property):
        returns = inspect.signature(attribute.fget).return_annotation if attribute.fget else None
        return {"kind": "property", "parameters": [], "returns": _text(returns, inspect.Signature.empty)}
    if isinstance(attribute, (staticmethod, classmethod)):
        return _callable_entry(attribute.__func__) | {"kind": type(attribute).__name__}
    return _callable_entry(attribute)


def collect() -> dict[str, Any]:
    """The whole public surface, sorted so two snapshots differ only where the package does."""
    surface: dict[str, Any] = {"exports": sorted(assertpy2.__all__), "py_typed": _has_py_typed()}

    functions = {}
    for name in sorted(assertpy2.__all__):
        exported = getattr(assertpy2, name)
        if inspect.isfunction(exported):
            functions[name] = _callable_entry(exported)
        elif inspect.isclass(exported):
            functions[name] = {
                "kind": "class",
                "bases": [base.__name__ for base in exported.__mro__[1:] if base is not object],
                "fields": _fields(exported),
                "init": _parameters(exported.__init__),
            }
    surface["exported"] = functions

    surface["builder"] = {
        name: _member_entry(AssertionBuilder, name)
        for name in sorted(dir(AssertionBuilder))
        if not name.startswith("_")
    }
    surface["matchers"] = {
        name: _callable_entry(getattr(assertpy2.match, name))
        for name in sorted(dir(assertpy2.match))
        if not name.startswith("_")
    }
    surface["matcher_protocol"] = list(_MATCHER_PROTOCOL)
    surface["failure_attributes"] = sorted(_failure_attributes())
    return surface


def _fields(record: type) -> list[str]:
    """Field names for a dataclass or a NamedTuple, empty for anything else."""
    if dataclasses.is_dataclass(record):
        return [field.name for field in dataclasses.fields(record)]
    return list(getattr(record, "_fields", []))


def _failure_attributes() -> list[str]:
    """What a caller reads off a raised failure, taken from a real one rather than from a list."""
    try:
        assertpy2.assert_that(1).is_equal_to(2)
    except assertpy2.AssertionFailure as failure:
        return [name for name in vars(failure) if not name.startswith("_")]
    raise AssertionError("the probe assertion did not fail")  # pragma: no cover - it always fails


def _has_py_typed() -> bool:
    return (pathlib.Path(assertpy2.__file__).parent / "py.typed").exists()
