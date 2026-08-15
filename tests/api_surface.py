"""What the package promises, in a form two revisions can be compared by.

The neighbouring guards each answer a different question. `test_public_surface` holds a hand-written
list of exported names and record fields, `test_protocol_parity` holds the typed surface against the
runtime, `test_typing` pins overload resolution. None of them notices a *signature* moving: a parameter
renamed, a default changed, a keyword becoming positional, two positional parameters swapping places.
Those break a caller silently, and they are what this module collects.

The collection is derived rather than hand-written, unlike the name list next door, and that is a
deliberate difference. A hand-written list of two hundred and fifty signatures would not be read on
review; a generated snapshot with a reviewable diff is. What keeps it honest is that the snapshot is
committed: changing the package without changing the snapshot fails, and changing the snapshot shows up
in the diff as its own decision.
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import inspect
import pathlib
from typing import Any

import assertpy2
import assertpy2.assertpy
from assertpy2.assertpy import AssertionBuilder
from assertpy2.matchers import Matcher

_UNSET = object()


def _default(parameter: inspect.Parameter) -> str | None:
    """The default as a stable string, or ``None`` when there is none.

    Recorded rather than reduced to "has a default", because `timeout=1` becoming `timeout=None` changes
    what an existing call does while leaving the arity untouched.  A repr is used so the snapshot stays
    JSON, and a sentinel object without a stable repr is reduced to its type, which still moves when the
    sentinel is replaced by a different kind of thing.
    """
    if parameter.default is inspect.Parameter.empty:
        return None
    value = parameter.default
    if value is None or isinstance(value, (bool, int, float, str, bytes, tuple, frozenset)):
        return repr(value)
    return f"<{type(value).__name__}>"


def _parameters(target: Any) -> list[dict[str, Any]]:
    """Each parameter as the things a caller can break on, in the order they are declared."""
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
            "default": _default(parameter),
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


def _class_entry(exported: type) -> dict[str, Any]:
    """A class as its callable form plus what inheritance and construction promise.

    The parameters are taken from the class itself rather than from `__init__`, because calling a class
    may be defined by `__new__` or by a metaclass, and a caller writes the call, not the method that
    happens to implement it.  They live under the same key as every other callable so the comparison
    treats them the same way rather than needing a rule of their own, which is how a whole constructor
    once went uncompared.

    A constructor inherited from elsewhere is recorded as inherited rather than copied, and that is not
    tidiness: `WarningLoggingAdapter` takes its `__init__` from `logging.LoggerAdapter`, which gained a
    parameter in 3.13, so copying it made the snapshot disagree with itself across the supported Python
    versions.  What this package promises there is the base class, which the `bases` list already holds.
    """
    own = any(name in vars(exported) for name in ("__init__", "__new__"))
    entry = _callable_entry(exported) if own else {"kind": "class", "parameters": [], "returns": None}
    return entry | {
        "kind": "class",
        "construction": "own" if own else "inherited",
        "bases": [base.__name__ for base in exported.__mro__[1:] if base is not object],
        "fields": _fields(exported),
    }


def collect() -> dict[str, Any]:
    """The whole public surface, sorted so two snapshots differ only where the package does."""
    exported: dict[str, Any] = {}
    for name in sorted(assertpy2.__all__):
        value = getattr(assertpy2, name)
        if inspect.isclass(value):
            exported[name] = _class_entry(value)
        elif callable(value):
            exported[name] = _callable_entry(value)
        else:
            exported[name] = {"kind": type(value).__name__, "parameters": [], "returns": None}

    return {
        "exports": sorted(assertpy2.__all__),
        "py_typed": _has_py_typed(),
        "exported": exported,
        "builder": {
            name: _member_entry(AssertionBuilder, name)
            for name in sorted(dir(AssertionBuilder))
            if not name.startswith("_")
        },
        "matchers": {
            name: _callable_entry(getattr(assertpy2.match, name))
            for name in sorted(dir(assertpy2.match))
            if not name.startswith("_")
        },
        "entry_overloads": _entry_overloads(),
        "matcher_protocol": _matcher_protocol(),
        "failure_attributes": _failure_attributes(),
    }


def _entry_overloads() -> list[str]:
    """The `assert_that` overloads as text, in declaration order.

    The runtime knows nothing about them: it sees one implementation, while a checker sees fourteen, and
    dropping one changes which protocol a caller gets without changing anything the runtime can be asked
    about.  `test_typing` pins the resolution of chosen calls, which is a different question: it would
    stay green if an overload nobody wrote an `assert_type` for disappeared.
    """
    source = pathlib.Path(assertpy2.assertpy.__file__).read_text(encoding="utf-8")
    declarations = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef) or node.name != "assert_that":
            continue
        if any(isinstance(decorator, ast.Name) and decorator.id == "overload" for decorator in node.decorator_list):
            arguments = ", ".join(
                f"{argument.arg}: {ast.unparse(argument.annotation) if argument.annotation else '?'}"
                for argument in node.args.args
            )
            returns = ast.unparse(node.returns) if node.returns else "?"
            declarations.append(f"({arguments}) -> {returns}")
    return declarations


def _matcher_protocol() -> list[str]:
    """The methods a custom matcher must provide, read off the protocol rather than repeated here.

    Repeating them as a constant made the check tautological: renaming a method in the library would
    have changed nothing in the snapshot, because the snapshot was the constant.
    """
    return sorted(name for name in vars(Matcher) if not name.startswith("_"))


def _fields(record: type) -> list[str]:
    """Field names for a dataclass or a NamedTuple, in declaration order, empty for anything else."""
    if dataclasses.is_dataclass(record):
        return [field.name for field in dataclasses.fields(record)]
    return list(getattr(record, "_fields", []))


def _failure_attributes() -> list[str]:
    """What a caller can read off a failure, from the class and from failures of several shapes.

    Two sources on purpose.  The class gives properties, slots and inherited descriptors, which a single
    instance never shows; the instances give attributes set in `__init__`, which the class does not
    carry.  And more than one failure is raised, because `trace` is filled by polling and `failures` by
    a soft block, so a snapshot built from one plain failure would call the others new every time.
    """
    from_class = {
        name
        for name, value in vars(assertpy2.AssertionFailure).items()
        if not name.startswith("_") and isinstance(value, (property, staticmethod, classmethod))
    }
    return sorted(from_class | _attributes_of_real_failures())


def _attributes_of_real_failures() -> set[str]:
    return set().union(*(_attributes_of(raise_it) for raise_it in (_plain_failure, _soft_failure, _polling_failure)))


def _attributes_of(raise_it: Any) -> set[str]:
    try:
        raise_it()
    except assertpy2.AssertionFailure as failure:
        return {name for name in vars(failure) if not name.startswith("_")}
    raise AssertionError("the probe did not fail")  # pragma: no cover - each probe always fails


def _plain_failure() -> None:
    assertpy2.assert_that(1).is_equal_to(2)


def _soft_failure() -> None:
    with assertpy2.soft_assertions():
        assertpy2.assert_that(1).is_equal_to(2)


def _polling_failure() -> None:
    assertpy2.assert_that(lambda: 1).eventually_sync(timeout=0.05, interval=0.01).is_equal_to(2)


def _has_py_typed() -> bool:
    return (pathlib.Path(assertpy2.__file__).parent / "py.typed").exists()
