"""Hold the typed surface and the runtime to the same signature, parameter by parameter.

`tests/test_protocol_parity.py` asks whether every declared method exists and whether the runtime
*accepts* what a declaration marks required.  That leaves six questions, and each of them is a way for
the two halves to drift while both gates stay green:

* the runtime accepts a parameter no declaration mentions, so a caller cannot pass it without a cast
* a declaration names one the runtime has not got, so the call type-checks and raises
* they disagree about how a parameter may be passed, so a keyword the checker allows is refused
* they disagree about whether it is required, so an omission the checker allows fails at run time
* between them the views refuse a value the runtime accepts, so no caller can write a working call
* a view offers one the runtime never promised, so the call type-checks on a signature that excludes it

The last two are a different kind of blindness from the first four.  Conformance to a protocol is
contravariant in parameters, so a view narrower than the runtime satisfies it however far it narrows,
and no checker has anything to report either way round.

This is the conformance half of the plan, and only its reporting half: it compares and complains and
generates nothing.  What it replaces is the audit that used to be done by hand, once, whenever somebody
remembered to wonder.
"""

from __future__ import annotations

import ast
import collections
import inspect

import pytest

from assertpy2 import assert_that
from assertpy2.assertpy import AssertionBuilder
from tests.test_protocol_parity import _PROTOCOLS, _VALUE_VIEWS, _declarations_of, _members_of

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


def _concrete_signature(name: str) -> inspect.Signature | None:
    """The runtime method's signature, or ``None`` where there is nothing to read."""
    concrete = inspect.getattr_static(AssertionBuilder, name, None)
    if concrete is None or isinstance(concrete, property):
        return None
    try:
        return inspect.signature(concrete)
    except (TypeError, ValueError):  # a C-implemented or otherwise unreadable callable
        return None


def _runtime(name: str) -> dict[str, tuple[str, bool]] | None:
    """The same reading of the concrete method, or ``None`` where there is nothing to compare."""
    signature = _concrete_signature(name)
    if signature is None:
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


def _shapes(annotation: ast.expr) -> set[str]:
    """The names a top-level union offers, one per member, with any subscript dropped.

    The head rather than the whole spelling, because the two halves write one promise two ways: a view
    says `Collection[_E]` where the runtime says `Collection[Any]`, and comparing those as text would
    report every generic in the surface.  What is lost with the subscript is real and is the limit of
    this comparison: `list[str]` and `list[int]` read the same here.

    The split is on the syntax tree and not on the character, which is not a refinement either.  Reading
    the `|` inside `type[set[_E] | frozenset[_E]]` as a top-level union makes `frozenset` look like
    something the views offer and the runtime does not, and four of the first four findings this check
    ever produced were that and nothing else.
    """
    return {member.split("[", 1)[0] for member in _members_of(annotation)}


def _covered() -> tuple[list[tuple[str, str, set[str], set[str]]], collections.Counter[str]]:
    """``(method, parameter, what the views offer between them, what the runtime declares)``, and the skips.

    The union across views rather than each view against the runtime, because narrowing per view is the
    design: `_TextAssertion.starts_with(prefix: str)` is deliberately narrower than a runtime that takes
    any element, and so is every other view of it.  What no set of views may do between them is leave a
    spelling the runtime accepts with nowhere to be written.
    """
    offered: dict[str, dict[str, set[str]]] = collections.defaultdict(lambda: collections.defaultdict(set))
    for view in sorted(_VALUE_VIEWS):
        for name, methods in _declarations_of(view).items():
            for method in methods:
                arguments = method.args
                for argument in arguments.posonlyargs + arguments.args + arguments.kwonlyargs:
                    if argument.arg != "self" and argument.annotation is not None:
                        offered[name][argument.arg] |= _shapes(argument.annotation)

    pairs: list[tuple[str, str, set[str], set[str]]] = []
    skipped: collections.Counter[str] = collections.Counter()
    for name, parameters in sorted(offered.items()):
        concrete = _concrete_signature(name)
        if concrete is None:
            continue
        for parameter, declared in sorted(parameters.items()):
            found = concrete.parameters.get(parameter)
            if found is None:
                skipped["the runtime has no such parameter: it arrives through `**kwargs`"] += 1
                continue
            if found.annotation is inspect.Parameter.empty:
                skipped["the runtime declares no annotation at all, so there is nothing to disagree with"] += 1
                continue
            runtime = _runtime_shapes(found.annotation)
            if runtime is None:
                skipped["the runtime spells it in a form this walk cannot read"] += 1
                continue
            if runtime == {"object"}:
                skipped["the runtime takes `object`, which no narrowing can fail to be covered by"] += 1
                continue
            pairs.append((name, parameter, declared, runtime))
    return pairs, skipped


def _runtime_shapes(annotation: object) -> set[str] | None:
    """The runtime's side of the comparison, or ``None`` when it cannot be read as a spelling."""
    try:
        return _shapes(ast.parse(str(annotation), mode="eval").body)
    except SyntaxError:  # every module here defers its annotations, so this is an object and not text
        return None


@pytest.fixture(scope="module")
def covered():
    return _covered()


class TestTheTypedSurfaceAndTheRuntimeAcceptTheSameThings:
    """The axis no checker can report, because conformance to a protocol is contravariant in parameters.

    A view narrower than the runtime satisfies it by construction, so nothing complains when every view
    between them refuses a value the runtime accepts.  `starts_with_bytes` declared `bytes` in the one
    view offering it while the runtime took a `bytearray` as well, and ty, mypy and pyright were clean on
    that for as long as it stood.  A view wider than the runtime is the same blindness from the other
    side: the call type-checks, and the runtime is under no obligation to do anything sensible with it.

    Both directions compare the head of each union member and nothing under it, so what a green run here
    means is narrower than the two test names read: `bytes` against `bytearray` is caught, `list[str]`
    against `list[int]` is not.  `_shapes` says why that is the honest limit rather than a shortcut.
    """

    def test_the_comparison_reached_most_of_what_the_views_declare(self, covered) -> None:
        pairs, skipped = covered
        # the headline must not be wider than the check: a third of the declared parameters go
        # uncompared, each for one of four stated reasons, and a walk that compared nothing at all
        # would pass both directions below without a word
        assert_that(pairs).described_as("parameters with a spelling on both sides").is_length_between(60, 250)
        assert_that(sum(skipped.values())).described_as("parameters skipped, each for a named reason").is_less_than(
            len(pairs)
        )

    def test_no_value_the_runtime_accepts_is_unwritable_through_every_view(self, covered) -> None:
        """The direction that caught `starts_with_bytes`: accepted at run time, refused by every view."""
        pairs, _skipped = covered
        unreachable = [
            f"{name}({parameter}): runtime takes {sorted(runtime)}, no view offers {sorted(runtime - declared)}"
            for name, parameter, declared, runtime in pairs
            if runtime - declared and "object" not in declared
        ]
        assert_that(sorted(unreachable)).described_as(
            "accepted at run time and unwritable in every typed view"
        ).is_empty()

    def test_no_view_offers_what_the_runtime_does_not_declare(self, covered) -> None:
        """The other direction: a call every checker allows, on a signature that never promised it."""
        pairs, _skipped = covered
        overreaching = [
            f"{name}({parameter}): views offer {sorted(declared - runtime)}, runtime declares {sorted(runtime)}"
            for name, parameter, declared, runtime in pairs
            if declared - runtime
        ]
        assert_that(sorted(overreaching)).described_as(
            "promised by a typed view and absent from the runtime signature"
        ).is_empty()
