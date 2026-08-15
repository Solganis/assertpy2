"""What the package promises, in a form two revisions can be compared by.

The neighbouring guards each answer a different question. `test_public_surface` holds a hand-written
list of exported names and record fields, `test_protocol_parity` holds the typed surface against the
runtime, `test_typing` pins overload resolution. None of them notices a *signature* moving: a parameter
renamed, a default changed, a keyword becoming positional, two positional parameters swapping places,
an overload disappearing. Those break a caller silently, and they are what this module collects.

The collection is derived rather than hand-written, unlike the name list next door, and that is a
deliberate difference. A hand-written list of two hundred and fifty signatures would not be read on
review; a generated snapshot with a reviewable diff is. What keeps it honest is that the snapshot is
committed: changing the package without changing the snapshot fails, and changing the snapshot shows up
in the diff as its own decision.

One thing is deliberately outside: the *value* of an exported constant. The only ones are `__version__`,
which changes every release by design, and the `match` namespace, whose contents are collected in full
under `matchers`. Checking the value there would fail on every version bump and teach everyone to
re-record without reading, which is the failure mode this file exists to avoid.
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import enum
import inspect
import pathlib
import types
from typing import Any

import assertpy2
import assertpy2.assertpy
from assertpy2.assertpy import AssertionBuilder
from assertpy2.matchers import Matcher

_SIMPLE = (bool, int, float, str, bytes, type(None))
_DESCRIPTORS = (property, staticmethod, classmethod, types.MemberDescriptorType, types.GetSetDescriptorType)


def _value(value: Any, depth: int = 0) -> str:
    """A default value as a stable string, deep enough that two different values look different.

    `[]` and `[1]` reduced to the same text once, which made a changed default invisible, and the whole
    reason defaults are recorded is that `timeout=1` becoming `timeout=None` changes what an existing
    call does.  So containers are walked, enums are named by member, callables by qualified name, and
    only a genuinely opaque object falls back to its type, where the type at least is still compared.
    """
    if isinstance(value, _SIMPLE):
        return repr(value)
    if isinstance(value, enum.Enum):
        return f"{type(value).__module__}.{type(value).__qualname__}.{value.name}"
    if isinstance(value, (list, tuple, set, frozenset)) and depth < 3:
        items = [_value(item, depth + 1) for item in value]
        if isinstance(value, (set, frozenset)):
            items = sorted(items)  # a set has no order of its own, and its iteration order is not news
        return f"{type(value).__name__}[{', '.join(items)}]"
    if isinstance(value, dict) and depth < 3:
        pairs = ", ".join(f"{_value(key, depth + 1)}: {_value(item, depth + 1)}" for key, item in value.items())
        return f"dict[{pairs}]"
    if callable(value):
        module = getattr(value, "__module__", type(value).__module__)
        return f"<callable {module}.{getattr(value, '__qualname__', type(value).__name__)}>"
    return f"<{type(value).__module__}.{type(value).__name__}>"


def _default(parameter: inspect.Parameter) -> str | None:
    return None if parameter.default is inspect.Parameter.empty else _value(parameter.default)


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
    """An annotation as a stable string, or ``None`` when there is none."""
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


def _defining_module(exported: type) -> str:
    """Where the call is defined: this class, or whichever base first provides a constructor."""
    for base in exported.__mro__:
        if "__init__" in vars(base) or "__new__" in vars(base):
            return f"{base.__module__}.{base.__qualname__}"
    return "object"  # pragma: no cover - object always provides both


def _class_entry(exported: type) -> dict[str, Any]:
    """A class as its call signature plus what inheritance and construction promise.

    The signature comes from the class rather than from `__init__`, because calling a class may be
    defined by `__new__` or by a metaclass, and a caller writes the call, not the method that implements
    it.  Where the constructor comes from is recorded beside it, and that is not bookkeeping:
    `WarningLoggingAdapter` inherits `__init__` from `logging.LoggerAdapter`, which gained a parameter in
    3.13, so a snapshot that copied it disagreed with itself across the supported Python versions.  The
    comparison uses this to stay quiet about a signature the package does not own, while still reporting
    the day the base itself is swapped.
    """
    return _callable_entry(exported) | {
        "kind": "class",
        "construction": _defining_module(exported),
        "bases": [f"{base.__module__}.{base.__qualname__}" for base in exported.__mro__[1:] if base is not object],
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
            exported[name] = {"kind": f"{type(value).__module__}.{type(value).__name__}", "parameters": []}

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


def _overload_names(tree: ast.Module) -> set[str]:
    """The names `typing.overload` was actually imported under in this module.

    Guessing by suffix accepted `@custom_overload` and rejected `from typing import overload as ov`,
    which is two errors in opposite directions.  The imports say it exactly.
    """
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("typing", "typing_extensions"):
            names |= {alias.asname or alias.name for alias in node.names if alias.name == "overload"}
    return names


def _is_overload(decorator: ast.expr, names: set[str]) -> bool:
    if isinstance(decorator, ast.Name):
        return decorator.id in names
    return isinstance(decorator, ast.Attribute) and decorator.attr == "overload"


def _entry_overloads() -> list[str]:
    """The `assert_that` overloads as text, in declaration order.

    Order carries meaning: where two overloads both match, the first wins, so a reshuffle changes which
    protocol a caller gets while every declaration survives.  Hence a list compared as a sequence.

    The runtime knows nothing about any of it - it sees one implementation where a checker sees fourteen.
    `test_typing` pins the resolution of chosen calls, a different question: it would stay green if an
    overload nobody wrote an `assert_type` for disappeared.
    """
    tree = ast.parse(pathlib.Path(assertpy2.assertpy.__file__).read_text(encoding="utf-8"))
    names = _overload_names(tree)
    # taken from `tree.body` rather than `ast.walk`: the latter has no documented order and would also
    # find a nested function of the same name, and order is exactly what this list is compared by
    declared = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "assert_that"
        and any(_is_overload(decorator, names) for decorator in node.decorator_list)
    ]
    return [_signature_text(node) for node in sorted(declared, key=lambda node: node.lineno)]


def _signature_text(node: ast.FunctionDef) -> str:
    """The whole declared signature, not only the plain arguments.

    Positional-only, keyword-only, `*args` and `**kwargs` each change what a call may look like, and the
    first version of this collected `node.args.args` alone, which ignored every one of them.
    """
    arguments = node.args
    positional = arguments.posonlyargs + arguments.args
    # defaults line up with the tail of the positional arguments, which is how the grammar defines them
    padding: list[ast.expr | None] = [None] * (len(positional) - len(arguments.defaults))
    positional_defaults = padding + list(arguments.defaults)
    parts = [
        _argument_text(argument, default)
        for argument, default in zip(arguments.posonlyargs, positional_defaults, strict=False)
    ]
    if arguments.posonlyargs:
        parts.append("/")
    parts += [
        _argument_text(argument, default)
        for argument, default in zip(arguments.args, positional_defaults[len(arguments.posonlyargs) :], strict=False)
    ]
    if arguments.vararg:
        parts.append(f"*{_argument_text(arguments.vararg, None)}")
    elif arguments.kwonlyargs:
        parts.append("*")
    parts += [
        _argument_text(argument, default)
        for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=False)
    ]
    if arguments.kwarg:
        parts.append(f"**{_argument_text(arguments.kwarg, None)}")
    returns = ast.unparse(node.returns) if node.returns else "?"
    return f"({', '.join(parts)}) -> {returns}"


def _argument_text(argument: ast.arg, default: ast.expr | None) -> str:
    """One argument as declared, defaults included.

    Without the default, `description: str` gaining `= ""`, or `= ""` becoming `= None`, moved nothing in
    the snapshot while changing what an existing call does.
    """
    annotation = ast.unparse(argument.annotation) if argument.annotation else "?"
    return f"{argument.arg}: {annotation}" + (f" = {ast.unparse(default)}" if default is not None else "")


def _matcher_protocol() -> dict[str, Any]:
    """What a custom matcher must provide, with signatures rather than names alone.

    Names were not enough twice over: they were first repeated from a constant in this file, which made
    the check tautological, and then read without signatures, so `matches(self, value)` losing its
    argument would have passed.  The MRO is walked, because a protocol may inherit a member, and
    annotation-only members are recorded too, since a protocol may require an attribute rather than a
    method.
    """
    members: dict[str, Any] = {}
    for base in reversed(Matcher.__mro__):
        members.update(
            {name: _member_entry(Matcher, name) for name in vars(base) if not name.startswith("_")},
        )
        for name, annotation in getattr(base, "__annotations__", {}).items():
            # assigned rather than set as a default: walking base to derived means the derived one has
            # to win, and `setdefault` kept whatever the base declared
            if not name.startswith("_"):
                members[name] = {"kind": "annotation", "annotation": _text(annotation, None)}
    return dict(sorted(members.items()))


def _fields(record: type) -> list[str]:
    """Field names for a dataclass or a NamedTuple, in declaration order, empty for anything else."""
    if dataclasses.is_dataclass(record):
        return [field.name for field in dataclasses.fields(record)]
    return list(getattr(record, "_fields", []))


def _failure_attributes() -> list[str]:
    """What a caller can read off a failure, from the whole hierarchy and from real failures.

    Two sources, and the class side walks the MRO rather than one `vars()`: a property or a slot
    descriptor inherited from a base is as readable as one declared here, and `vars()` on the leaf class
    sees neither.  The instance side raises three shapes of failure, because `trace` is filled only by
    polling and `failures` only by a soft block.
    """
    from_class = {
        name
        for base in assertpy2.AssertionFailure.__mro__
        for name, value in vars(base).items()
        # every public member that is not a plain method: properties, slots, class attributes and any
        # descriptor of someone else's making.  Narrowing this to three descriptor types once meant a
        # public class attribute could disappear without a word
        if not name.startswith("_") and not inspect.isroutine(value)
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
    """Whether the marker is in the tree.

    Whether it reaches the wheel is a different question, answered by the consumer run that installs the
    built artifact into a clean environment.  Asking it here would mean building the package inside the
    suite.
    """
    return (pathlib.Path(assertpy2.__file__).parent / "py.typed").exists()
