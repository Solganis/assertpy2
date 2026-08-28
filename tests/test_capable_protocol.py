"""Hold the façade the capability umbrella hands back to what it is generated from.

`assert_that()` returns this for a value that answers to some capability and to no overload by name.
It used to return the builder itself, which meant every assertion on it, including the six that order
the value: `assert_that(a_mapping).is_positive()` type-checked on ty, mypy and Pyright, the three
gated then, and raised `TypeError` when it ran.

Two claims here, and they pull against each other, which is why both are written down. Nothing the
builder offers may be missing, because the umbrella exists for values the library could not name and a
narrowing by accident refuses a call that runs. And the six have to be restricted, because that is the
whole reason the façade exists.
"""

from __future__ import annotations

import ast
import collections
import numbers
import pathlib
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

import assertpy2.assertpy
from assertpy2 import AssertionFailure, assert_that
from assertpy2._engine import _capable_typing
from assertpy2.assertpy import AssertionBuilder

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SOURCE = pathlib.Path(_capable_typing.__file__).read_text(encoding="utf-8")


class _Capable:
    """The narrowest value the umbrella claims: one capability and nothing else."""

    def __iter__(self):
        return iter(("a",))


class _Maximal(_Capable):
    """Every capability the umbrella recognises, plus every operator a restricted assertion reads.

    Registered as a real number because that is what the numeric gate asks, and registration is the one
    thing no checker can see.  That is why the numeric family is the one left open: measured, `is_zero()`
    runs on a class registered without `__float__`, so every structural stand-in refused a working call.
    """

    def __float__(self):
        return 0.0

    def __lt__(self, other):
        return True

    def __gt__(self, other):
        return False

    def __le__(self, other):
        return True

    def __ge__(self, other):
        return False

    def __fspath__(self):
        return "."

    def __call__(self, *args, **kwargs):
        raise ValueError("boom")

    # the other four capabilities, so an assertion reading a mapping, a model or a response is answered here
    def keys(self):
        return ("id",)

    def __getitem__(self, key):
        return 1

    def __len__(self):
        return 1

    def __contains__(self, item):
        return True

    def model_dump(self, *args, **kwargs):
        return {"id": 1}

    @property
    def status_code(self):
        return 200

    @property
    def headers(self):
        return {"content-type": "application/json"}

    def json(self):
        return {"id": 1}


numbers.Real.register(_Maximal)


class _Ordered(_Capable):
    """Capable and orderable, which is what the relational assertions read."""

    def __lt__(self, other):
        return True

    def __gt__(self, other):
        return False

    def __le__(self, other):
        return True

    def __ge__(self, other):
        return False


class _Numeric(_Ordered):
    """Capable, orderable and a real number, which is what the numeric gate reads.

    Ordering as well, because `is_between` and `is_close_to` order the pair after the number gate, and
    a subject with only the registration reads as refusing them.
    """

    def __float__(self):
        return 0.0


numbers.Real.register(_Numeric)


class _Convertible(_Capable):
    """Capable and a real number that converts through `__float__`, carrying no ordering."""

    def __float__(self):
        return 0.0


class _Indexed(_Capable):
    """The other way to convert: `math.isnan` falls back to `__index__` when there is no `__float__`."""

    def __index__(self):
        return 0


class _Opaque(_Capable):
    """Registered as a real and converting neither way, which is what isolates the conversion.

    Every other subject that lacks conversion also lacks the registration, so it refuses at the number
    gate and proves nothing about conversion. This one gets past that gate and is refused by `math.isnan`.
    """


numbers.Real.register(_Convertible)
numbers.Real.register(_Indexed)
numbers.Real.register(_Opaque)


class _Bound:
    """A closeness operand that compares back, so the subject needs no ordering of its own.

    Measured: with ordinary int bounds a convertible subject with no `__lt__` raises, which reads as the
    assertion needing an ordering. It needs one on either side, and this is the side the caller supplies.
    """

    def __init__(self, held):
        self.held = held

    def __float__(self):
        return float(self.held)

    def __sub__(self, other):
        return _Bound(self.held - float(other))

    def __add__(self, other):
        return _Bound(self.held + float(other))

    # answered without converting the subject: reading `float(other)` here would hand the subject the very
    # capability the rung is keyed on, and a subject that cannot convert would read as answering
    def __lt__(self, other):
        return self.held < 0

    def __gt__(self, other):
        return self.held > 0

    def __eq__(self, other):
        return False

    def __hash__(self):
        return hash(self.held)


numbers.Real.register(_Bound)


class _Pathish(_Capable):
    """Capable and a path, which is the structural half of `isinstance(val, (str, os.PathLike))`."""

    def __fspath__(self):
        return "."


class _Callish(_Capable):
    """Capable and callable, which is what `callable(val)` reads.

    A fixed signature rather than `*args, **kwargs`, so the rung is measured against a real callable
    instead of one written to match its own protocol.
    """

    def __call__(self, first: int = 0) -> int:
        raise ValueError("boom")


_CARRIES = {
    "_Orderable": (_Ordered,),
    "_PathLike": (_Pathish,),
    "_Callable": (_Callish,),
    "SupportsFloat | _Indexable": (_Convertible, _Indexed),
}
"""Subjects per shape, each carrying that shape and no other, so a wrong key cannot read as right.

The conversion key has two, one per half of the union: `math.isnan` reads `__float__` and falls back to
`__index__`, and a carrier for only one half would leave the other unmeasured.
"""

_WITHOUT = {
    "_Orderable": (_Capable, _Pathish, _Callish),
    "_PathLike": (_Capable, _Ordered, _Callish),
    "_Callable": (_Capable, _Ordered, _Pathish),
    "SupportsFloat | _Indexable": (_Capable, _Ordered, _Pathish, _Callish, _Opaque),
}
"""Subjects that genuinely lack each shape, listed rather than derived.

`_Numeric` carries an ordering as well, because the numeric assertions order the pair after the number
gate, so "every other subject" would have read the numeric one as answering an ordering it was never
keyed on.
"""


_ASKED_OF_THE_CHAIN = frozenset({"when_called_with"})
"""Gated on a call before it rather than on the value, so asking it alone proves nothing."""

_ARGUMENTS = [
    (),
    ("a",),
    ("id",),
    (0,),
    (1, 1),
    (0, 9),
    (_Bound(0), _Bound(9)),
    (ValueError,),
    ("utf-8",),
    (b"a",),
    (0, b"a"),
    ({"id": 1},),
    ("$.id",),
    (lambda item: True,),
    (str,),
]


def _answers(value, name) -> bool:
    """Whether *value* can be asked *name* at all, over every plausible argument tuple.

    A verdict counts as an answer and so does a pass: what it is looking for is the refusal a gate
    raises, which is `TypeError` or `ValueError` whatever the arguments were.
    """
    for args in _ARGUMENTS:
        try:
            getattr(assert_that(value), name)(*args)
        # the loop is over argument tuples, not over a workload: the cost of the `try` is not the point
        except AssertionFailure:  # noqa: PERF203
            return True
        except Exception:  # any refusal is one, and the next tuple may still answer
            continue
        else:
            return True
    return False


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
            [sys.executable, "-m", *command],
            input=source,
            capture_output=True,
            text=True,
            # named rather than left to the locale: a Windows runner is not UTF-8, and ruff refused the bytes
            encoding="utf-8",
            cwd=_ROOT,
            check=False,
        )
        # refuse rather than fall back: `--fix` exits 1 with violations left, so 1 would let rejected output through
        if result.returncode != 0 or not result.stdout:
            raise RuntimeError(
                f"{' '.join(command)} exited {result.returncode}, so this gate would compare the wrong "
                f"thing: {result.stderr}"
            )
        source = result.stdout
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
        # built directly: `assert_that()` hands back a subclass, and a suite's four registered names read as dropped
        carried = {name for name in dir(AssertionBuilder({"id": 1})) if not name.startswith("_")}
        declared = set(_declarations()) | _attributes()
        assert_that(carried - declared).described_as("a member the umbrella used to offer").is_empty()

    def test_the_runtime_answers_every_name_the_facade_declares(self) -> None:
        """Declared and not there at run time would be the same defect read from the other end."""
        builder = assert_that({"id": 1})
        missing = [name for name in _declarations() if not name.startswith("__") and not hasattr(builder, name)]
        assert_that(missing).described_as("declared on the façade and absent from the builder").is_empty()


class TestWhatEachRestrictedAssertionAsksFor:
    """The whole reason the façade exists, derived from the runtime rather than compared against a list.

    Written twice as a comparison against the generator's own tables, and both times an injection went
    through: removing a name from a table un-restricted it silently, and swapping one key for another
    left both sides agreeing.  These ask the runtime instead, with one subject per shape.
    """

    def test_each_family_holds_what_it_was_measured_to_hold(self) -> None:
        """How many assertions each key claims, which is where a name silently leaving is caught.

        The probe below cannot prove this direction: showing that nothing *outside* the tables is
        unanswerable needs a hand-written call per assertion, and a generic argument tuple reads a
        mapping assertion or a JSON pivot as unanswerable when it is only unsupplied.  Counts instead,
        against the families as they were measured, so removing an entry fails here and nowhere else.
        """
        generator = _generator()
        counted = {
            "shape": collections.Counter(generator._ASKS_A_SHAPE.values()),
            "type": collections.Counter(generator._ASKS_A_TYPE.values()),
        }
        assert_that(counted).described_as("what each key claims").is_equal_to(
            {
                "shape": collections.Counter(
                    {"_Orderable": 6, "_PathLike": 9, "_Callable": 5, "SupportsFloat | _Indexable": 5}
                ),
                "type": collections.Counter({"int": 3, "str": 14, "datetime.datetime": 7, "bytes | bytearray": 7}),
            }
        )

    def test_every_name_in_the_tables_is_one_the_builder_has(self) -> None:
        """A misspelling would restrict nothing and read as a restriction."""
        generator = _generator()
        builder = AssertionBuilder({"id": 1})
        tabled = set(generator._ASKS_A_SHAPE) | set(generator._ASKS_A_TYPE)
        assert_that([name for name in tabled if not hasattr(builder, name)]).described_as(
            "restricted, and not a name the builder has"
        ).is_empty()

    def test_every_restricted_assertion_is_answered_by_the_shape_it_asks_for(self) -> None:
        """And the direction that catches one key swapped for another."""
        generator = _generator()
        wrong = {
            name: asked
            for name, asked in generator._ASKS_A_SHAPE.items()
            if name not in _ASKED_OF_THE_CHAIN and not all(_answers(carrier(), name) for carrier in _CARRIES[asked])
        }
        assert_that(wrong).described_as("keyed on a shape that does not answer it").is_empty()

    def test_no_restricted_assertion_is_answered_without_its_shape(self) -> None:
        generator = _generator()
        loose = {
            name: asked
            for name, asked in generator._ASKS_A_SHAPE.items()
            if any(_answers(subject(), name) for subject in _WITHOUT[asked])
        }
        assert_that(loose).described_as("answered by a value that does not carry what it asks for").is_empty()

    @pytest.mark.parametrize(
        ("shape", "members"),
        [
            ("_Orderable", ["__lt__"]),
            ("_PathLike", ["__fspath__"]),
            ("_Callable", ["__call__"]),
            ("_Indexable", ["__index__"]),
        ],
    )
    def test_each_shape_asks_for_what_the_runtime_reads(self, shape, members) -> None:
        """The names are the measurement, not the family's own vocabulary.

        Every relational assertion reaches `_engine._ordering.compare`, which orders the pair with `<`,
        so `_Orderable` asks for `__lt__` and not `__gt__`.  The filesystem gate is
        `isinstance(val, (str, os.PathLike))` and a `str` never reaches here, so what is left of it is
        `__fspath__`.  The exception and warning gate is `callable(val)`.
        """
        declared = next(
            node for node in ast.walk(ast.parse(_SOURCE)) if isinstance(node, ast.ClassDef) and node.name == shape
        )
        assert_that([item.name for item in declared.body if isinstance(item, ast.FunctionDef)]).is_equal_to(members)

    def test_the_one_asked_of_the_chain_answers_after_what_it_waits_for(self) -> None:
        """`when_called_with()` is gated on a call before it rather than on the value, measured.

        On its own it refuses everything, callable or not, because it wants an expectation set first.
        Asked after `raises()`, a callable capable value answers it, which is what puts it in the table.
        """
        assert_that(_Callish()).raises(ValueError).when_called_with()


class TestWhatIsAskedOfATypeInstead:
    """The other half of the narrowing: rungs a capable value can never satisfy, and why they exist."""

    def test_no_such_assertion_answers_the_widest_capable_value(self) -> None:
        """A subject carrying every capability the umbrella knows and every operator these reach for.

        This is what makes a type-keyed rung honest rather than plausible.  Four separate readings
        during this work were wrong because the fixture lacked the one thing the assertion asked for, so
        the fixture here carries all of them at once: a name that runs belongs in the other table.
        """
        answered = [name for name in _generator()._ASKS_A_TYPE if _answers(_Maximal(), name)]
        assert_that(answered).described_as("keyed on a type, and yet answerable by a capable value").is_empty()

    def test_they_are_declared_rather_than_left_out(self) -> None:
        """Leaving one out refuses nothing, because `__getattr__` answers a name the façade does not have.

        Measured: with these dropped instead of declared, text, dates and bytes all still type-checked on
        a capable value in all three checkers.  The rung is what refuses, not the absence.
        """
        missing = set(_generator()._ASKS_A_TYPE) - set(_declarations())
        assert_that(missing).described_as("keyed on a type and not declared, so the hook answers it").is_empty()

    def test_the_two_tables_do_not_overlap(self) -> None:
        generator = _generator()
        both = set(generator._ASKS_A_SHAPE) & set(generator._ASKS_A_TYPE)
        assert_that(both).described_as("in both tables").is_empty()


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
