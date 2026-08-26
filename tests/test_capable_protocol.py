"""Hold the façade the capability umbrella hands back to what it is generated from.

`assert_that()` returns this for a value that answers to some capability and to no overload by name.
It used to return the builder itself, which meant every assertion on it, including the six that order
the value: `assert_that(a_mapping).is_positive()` type-checked on all three checkers and raised
`TypeError` when it ran.

Two claims here, and they pull against each other, which is why both are written down. Nothing the
builder offers may be missing, because the umbrella exists for values the library could not name and a
narrowing by accident refuses a call that runs. And the six have to be restricted, because that is the
whole reason the façade exists.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

import assertpy2.assertpy
from assertpy2 import assert_that
from assertpy2._engine import _capable_typing
from assertpy2.assertpy import AssertionBuilder

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SOURCE = pathlib.Path(_capable_typing.__file__).read_text(encoding="utf-8")


def _generator() -> ModuleType:
    """Import the generator, which lives outside the package, only where it is needed.

    Inline for the reason `test_check_protocols.py` gives: `scripts/` is not copied into mutmut's
    mutants tree, and a module-level import of it loses the whole baseline at collection.
    """
    sys.path.insert(0, str(_ROOT / "scripts"))
    import generate_poll_protocols

    return generate_poll_protocols


def _formatted(source: str) -> str:
    """Both steps the generator runs after writing, so the comparison is of the same thing twice."""
    for command in (
        ["ruff", "format", "--stdin-filename", _capable_typing.__file__, "-"],
        ["ruff", "check", "--fix", "--quiet", "--stdin-filename", _capable_typing.__file__, "-"],
    ):
        result = subprocess.run(
            [sys.executable, "-m", *command], input=source, capture_output=True, text=True, cwd=_ROOT, check=False
        )
        source = result.stdout or source
    return source


def _declarations() -> dict[str, list[ast.FunctionDef]]:
    """`{name: its declarations}` off the façade, a list because the hand-written ones are ladders."""
    found: dict[str, list[ast.FunctionDef]] = {}
    for node in ast.walk(ast.parse(_SOURCE)):
        if isinstance(node, ast.ClassDef) and node.name == "_CapableAssertion":
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    found.setdefault(item.name, []).append(item)
    return found


_RECEIVER = "«the receiver»"

_FOLLOWS_THE_RECEIVER = frozenset({"is_not_none"})
"""The one ladder whose return is the same value narrowed, so on the façade it stays on the façade.

Every other one here pivots: `is_instance_of` lands on a class the umbrella may not claim at all, and
`first`, `single` and `mapped` land on an element or a list.  Those hand back the builder on both sides,
so this is a named exception rather than a normalisation applied to every return.
"""


def _normalised(node: ast.FunctionDef) -> str:
    """One rung as text, with the receiver's own type spelled the same on both sides.

    The receiver is the one part that has to differ: a rung reached through the façade is written over
    `_CapableAssertion` where the builder writes `AssertionBuilder`, and a value the umbrella claims is
    only ever the first of those.  Everything else, parameters and return alike, is compared as written.
    """
    rendered = ast.parse(ast.unparse(node)).body[0]
    if not isinstance(rendered, ast.FunctionDef):  # pragma: no cover - every rung here is a function
        raise TypeError(node.name)
    rendered.body = [ast.Expr(value=ast.Constant(value=...))]
    rendered.decorator_list = []
    receiver = rendered.args.args[0] if rendered.args.args else None
    if receiver is not None and receiver.annotation is not None:
        receiver.annotation = ast.Name(id=_without_the_receiver(ast.unparse(receiver.annotation)))
    if node.name in _FOLLOWS_THE_RECEIVER and rendered.returns is not None:
        rendered.returns = ast.Name(id=_without_the_receiver(ast.unparse(rendered.returns)))
    return ast.unparse(rendered)


def _without_the_receiver(written: str) -> str:
    for spelling in ("AssertionBuilder", "_CapableAssertion"):
        written = written.replace(spelling, _RECEIVER)
    return written


def _attributes() -> set[str]:
    """The façade's non-callable members, which are declared rather than defined."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(_SOURCE)):
        if isinstance(node, ast.ClassDef) and node.name == "_CapableAssertion":
            found |= {
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
    return found


def _builder_ladders() -> dict[str, list[str]]:
    """`{name: its rungs}` for every assertion the builder declares for checkers only.

    These live in a `TYPE_CHECKING` block inside the class, so they are reached through the `if` rather
    than off the class body, and they are the ones a mixin's own signature cannot stand in for.
    """
    source = pathlib.Path(assertpy2.assertpy.__file__).read_text(encoding="utf-8")
    found: dict[str, list[str]] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef) or node.name != "AssertionBuilder":
            continue
        for guard in (item for item in node.body if isinstance(item, ast.If)):
            for item in guard.body:
                if isinstance(item, ast.FunctionDef) and any(
                    ast.unparse(one) == "overload" for one in item.decorator_list
                ):
                    found.setdefault(item.name, []).append(_normalised(item))
    return found


def test_the_facade_matches_what_the_generator_produces() -> None:
    generator = _generator()
    assert_that(_formatted(generator.generate_capable())).described_as(
        "the façade is out of step; run python scripts/generate_poll_protocols.py"
    ).is_equal_to(_formatted(_SOURCE))


class TestNothingTheBuilderOffersIsMissing:
    """The half that decides whether this can ship at all.

    A value reaching the umbrella used to get the builder, so anything absent here is an assertion that
    stopped type-checking while still running, which is the expensive direction of the two.
    """

    def test_every_public_member_of_the_builder_is_declared(self) -> None:
        """Read off a builder itself, not off the generator's idea of where to look.

        Rewritten twice, and each version was green while something was missing.  Built from
        `_builder_surface() | _BY_HAND` it could not name what the generator does not read, and four
        members that live on the builder rather than on a mixin were absent.  Built from the class it
        could not name what `__init__` sets, and four more went the same way.
        """
        # constructed here rather than reached through `assert_that()`, which hands back a subclass
        # carrying whatever extensions a suite has registered.  Measured: running `test_extensions.py`
        # first left `is_even_integer` and three more on that subclass, and this read them as members
        # the façade had dropped.  A gate whose verdict depends on what ran before it is worse than none
        carried = {name for name in dir(AssertionBuilder({"id": 1})) if not name.startswith("_")}
        declared = set(_declarations()) | _attributes()
        assert_that(carried - declared).described_as("a member the umbrella used to offer").is_empty()

    def test_the_runtime_answers_every_name_the_facade_declares(self) -> None:
        """Declared and not there at run time would be the same defect read from the other end."""
        builder = assert_that({"id": 1})
        missing = [name for name in _declarations() if not name.startswith("__") and not hasattr(builder, name)]
        assert_that(missing).described_as("declared on the façade and absent from the builder").is_empty()


class TestTheSixThatOrderTheValue:
    """What the façade exists to add, and the boundary of it."""

    def test_each_one_asks_the_value_for_an_ordering(self) -> None:
        generator = _generator()
        restricted = {
            name
            for name, nodes in _declarations().items()
            if any(
                node.args.args
                and node.args.args[0].annotation is not None
                and "_Orderable" in ast.unparse(node.args.args[0].annotation)
                for node in nodes
            )
        }
        assert_that(restricted).described_as("the assertions keyed on an ordering").is_equal_to(
            set(generator._ORDERING)
        )

    def test_the_ordering_is_asked_for_as_less_than(self) -> None:
        """`__lt__` and not `__gt__`, which is the runtime's own gate rather than a guess.

        Every one of the six reaches `_engine._ordering.compare`, which orders the pair with `<`.
        Measured on a class carrying one operator at a time, `__lt__` was the only one any of them ran
        with, so keying on `__gt__` would have refused a type that spells only `__lt__` and works.
        """
        orderable = next(
            node
            for node in ast.walk(ast.parse(_SOURCE))
            if isinstance(node, ast.ClassDef) and node.name == "_Orderable"
        )
        assert_that([item.name for item in orderable.body if isinstance(item, ast.FunctionDef)]).is_equal_to(["__lt__"])

    def test_a_value_with_an_ordering_still_answers_them(self) -> None:
        """The runtime half of the same claim: the rung must not refuse what runs."""

        class Ordered:
            def __iter__(self):
                return iter(("a",))

            def __lt__(self, other):
                return False

            def __gt__(self, other):
                return True

        assert_that(Ordered()).is_positive()

    def test_a_value_without_one_is_refused_by_the_runtime_too(self) -> None:
        with pytest.raises(TypeError):
            assert_that({"id": 1}.keys()).is_positive()


class TestTheLaddersTheBuilderDeclares:
    """The narrowings carried across by hand, which a flattened signature would have dropped."""

    def test_every_ladder_the_builder_declares_is_one_here_too(self) -> None:
        """Read off the builder rather than off the generator's own list of names to carry.

        Written the other way round first, and the difference is the whole value of this test: comparing
        against `_BY_HAND` proved the façade agreed with the generator, which is a tautology when both
        come from the same list.  Three ladders were missing that way and the test was green.
        `mapped()` claimed the input container, `single()` claimed the collection instead of its
        element, and `satisfies()` lost its `TypeIs` refinement.
        """
        here = {name: [_normalised(node) for node in nodes] for name, nodes in _declarations().items()}
        differing = {
            name: {"builder": rungs, "façade": here.get(name, [])}
            for name, rungs in _builder_ladders().items()
            if here.get(name, []) != rungs
        }
        assert_that(differing).described_as("a ladder the builder declares and the façade does not").is_empty()

    def test_the_verdict_pivot_hands_back_the_verdict_twin(self) -> None:
        checks = _declarations()["check"]
        assert_that([ast.unparse(node.returns) for node in checks if node.returns]).is_equal_to(
            ["_CheckAnyValue[_CapableT_co]"]
        )
