"""Hold the typed surface and the runtime to the same signature, parameter by parameter.

`tests/test_protocol_parity.py` asks whether every declared method exists and whether the runtime
*accepts* what a declaration marks required.  That leaves four questions, and each of them is a way for
the two halves to drift while both gates stay green:

* the runtime accepts a parameter no declaration mentions, so a caller cannot pass it without a cast
* a declaration names one the runtime has not got, so the call type-checks and raises
* they disagree about how a parameter may be passed, so a keyword the checker allows is refused
* they disagree about whether it is required, so an omission the checker allows fails at run time

This is the conformance half of the plan, and only its reporting half: it compares and complains and
generates nothing.  What it replaces is the audit that used to be done by hand, once, whenever somebody
remembered to wonder.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import ast

from assertpy2 import assert_that
from assertpy2.assertpy import AssertionBuilder
from tests.test_protocol_parity import _PROTOCOLS, _declarations_of

_KINDS = {
    inspect.Parameter.POSITIONAL_ONLY: "positional-only",
    inspect.Parameter.POSITIONAL_OR_KEYWORD: "positional",
    inspect.Parameter.KEYWORD_ONLY: "keyword-only",
    inspect.Parameter.VAR_POSITIONAL: "*args",
    inspect.Parameter.VAR_KEYWORD: "**kwargs",
}


def _declared(method: ast.FunctionDef) -> dict[str, tuple[str, bool]]:
    """``{parameter: (how it may be passed, whether it has a default)}`` for one declaration."""
    arguments = method.args
    positional = arguments.posonlyargs + arguments.args
    padding: list[ast.expr | None] = [None] * (len(positional) - len(arguments.defaults))
    defaults: dict[str, ast.expr | None] = dict(
        zip([argument.arg for argument in positional], padding + list(arguments.defaults), strict=True)
    )
    defaults.update(dict(zip([argument.arg for argument in arguments.kwonlyargs], arguments.kw_defaults, strict=True)))
    found = {}
    for group, kind in (
        (arguments.posonlyargs, "positional-only"),
        (arguments.args, "positional"),
        (arguments.kwonlyargs, "keyword-only"),
    ):
        for argument in group:
            found[argument.arg] = (kind, defaults.get(argument.arg) is not None)
    if arguments.vararg:
        found[arguments.vararg.arg] = ("*args", False)
    if arguments.kwarg:
        found[arguments.kwarg.arg] = ("**kwargs", False)
    return {name: value for name, value in found.items() if name != "self"}


def _runtime(name: str) -> dict[str, tuple[str, bool]] | None:
    """The same reading of the concrete method, or ``None`` where there is nothing to compare."""
    concrete = inspect.getattr_static(AssertionBuilder, name, None)
    if concrete is None or isinstance(concrete, property):
        return None
    try:
        signature = inspect.signature(concrete)
    except (TypeError, ValueError):  # a C-implemented or otherwise unreadable callable
        return None
    return {
        parameter.name: (_KINDS[parameter.kind], parameter.default is not inspect.Parameter.empty)
        for parameter in signature.parameters.values()
        if parameter.name != "self"
    }


def _pairs() -> list[tuple[str, str, dict[str, tuple[str, bool]], dict[str, tuple[str, bool]]]]:
    """Every declaration beside the runtime method it describes.

    An overload set is read as the union of what its rungs accept, since that is what it promises a
    caller.

    A runtime method taking `*args` or `**kwargs` is skipped whole, and that costs more than it sounds:
    176 of 1030 pairs, of which 31 are distinct names.  Twenty-six of those are purely variadic
    (`contains(*items)`, `is_in(*items)`), where there is genuinely nothing to compare.  Five are not,
    and their named parameters go unchecked along with the tail: `is_equal_to(other, **kwargs)`,
    `is_array_equal(expected, **options)`, `is_frame_equal(expected, **options)`,
    `is_array_close_to(expected, *, rtol, atol, equal_nan, **options)` and
    `is_subset_of(*supersets, allow_empty=False)`.  `is_equal_to` is the most used method here, and its
    `other` is compared on none of the four axes.

    Skipping per parameter instead would be worse, and that is measured rather than assumed: the six
    keywords `is_equal_to` declares (`ignore`, `include`, `tolerance`, `comparators`, `ignore_null`,
    `strict_types`) do not exist in its runtime signature at all, since they arrive through `**kwargs`.
    A finer skip would report all six as invented parameters, which the runtime accepts perfectly well.
    So this is the lesser of two wrong answers, and closing it properly means comparing the non-variadic
    head of a signature rather than skipping the method.
    """
    found = []
    for protocol in sorted(_PROTOCOLS):
        for name, methods in _declarations_of(protocol).items():
            concrete = _runtime(name)
            if concrete is None or any(kind.startswith("*") for kind, _ in concrete.values()):
                continue
            promised: dict[str, tuple[str, bool]] = {}
            for method in methods:
                for parameter, value in _declared(method).items():
                    promised.setdefault(parameter, value)
            found.append((protocol, name, promised, concrete))
    return found


@pytest.fixture(scope="module")
def pairs():
    return _pairs()


def test_the_comparison_itself_has_something_to_compare(pairs) -> None:
    # a walk that found nothing would pass every assertion below it
    assert_that(pairs).described_as("declarations with a runtime method to compare").is_length_between(600, 1200)


def test_no_parameter_is_accepted_at_runtime_without_being_declared(pairs) -> None:
    """One a caller cannot pass without a cast, though the runtime would take it."""
    undeclared = [
        f"{protocol}.{name}({parameter})"
        for protocol, name, promised, concrete in pairs
        for parameter in concrete
        if parameter not in promised
    ]
    assert_that(sorted(set(undeclared))).described_as("accepted at runtime, absent from the typed surface").is_empty()


def test_no_parameter_is_declared_without_existing_at_runtime(pairs) -> None:
    """The other direction, and the worse one: the call type-checks and then raises."""
    invented = [
        f"{protocol}.{name}({parameter})"
        for protocol, name, promised, concrete in pairs
        for parameter, (kind, _default) in promised.items()
        if parameter not in concrete and not kind.startswith("*")
    ]
    assert_that(sorted(set(invented))).described_as("declared, and the runtime has no such parameter").is_empty()


def test_the_two_agree_about_how_a_parameter_may_be_passed(pairs) -> None:
    """`f(x)`, `f(x, /)` and `f(*, x)` are three different promises, and only one of them is true."""
    differing = [
        f"{protocol}.{name}({parameter}): {kind} at runtime, {promised[parameter][0]} declared"
        for protocol, name, promised, concrete in pairs
        for parameter, (kind, _default) in concrete.items()
        if parameter in promised and promised[parameter][0] != kind and not promised[parameter][0].startswith("*")
    ]
    assert_that(sorted(set(differing))).described_as("passed one way at runtime and another in the type").is_empty()


def test_the_two_agree_about_whether_a_parameter_is_required(pairs) -> None:
    """An omission a checker allows and the runtime refuses is a failure at the call site, not here."""
    differing = [
        f"{protocol}.{name}({parameter}): {'optional' if has_default else 'required'} at runtime"
        for protocol, name, promised, concrete in pairs
        for parameter, (kind, has_default) in concrete.items()
        if parameter in promised and promised[parameter][0] == kind and promised[parameter][1] != has_default
    ]
    assert_that(sorted(set(differing))).described_as("required in one half and optional in the other").is_empty()
