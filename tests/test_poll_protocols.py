"""Hold the generated polling twins to what the generator produces, and to what the runtime answers.

A polling chain resolves every assertion through `__getattr__`, so before these twins existed a
checker saw `Any` from the first assertion onwards and `eventually_sync().no_such_assertion()` passed
all three.  The twins describe the same surface the value's own view describes, keyed on the probe's
return type.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import pathlib
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

from assertpy2 import assert_that
from assertpy2._engine import _builder_check_typing, _poll_typing, _typing
from assertpy2._engine._operations import NOT_AN_OPERATION, POLLS, WITHOUT_A_VERDICT
from assertpy2.assertpy import AssertionBuilder

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _generator() -> ModuleType:
    """Import the generator, which lives outside the package, only where it is needed.

    Inline rather than at the top on purpose: `scripts/` is not copied into mutmut's mutants tree, and
    a module-level import of it fails at collection, which takes the whole mutation baseline with it.
    Reached from two tests, so the run can deselect those two instead of losing the file.
    """
    sys.path.insert(0, str(_ROOT / "scripts"))
    import generate_poll_protocols

    return generate_poll_protocols


def _formatted(source: str) -> str:
    for command in (
        ["ruff", "format", "--stdin-filename", _poll_typing.__file__, "-"],
        ["ruff", "check", "--fix", "--quiet", "--stdin-filename", _poll_typing.__file__, "-"],
    ):
        result = subprocess.run(
            [sys.executable, "-m", *command], input=source, capture_output=True, text=True, cwd=_ROOT, check=False
        )
        # refuse rather than fall back to the input: with ruff absent the comparison below was of
        # unformatted text against formatted, which passed everywhere ruff was installed and failed on
        # the one CI cell that does not install it, a whole push later
        if result.returncode not in (0, 1) or not result.stdout:
            raise RuntimeError(f"ruff could not be run, so this gate would compare the wrong thing: {result.stderr}")
        source = result.stdout
    return source


def test_the_generated_twins_match_the_views_they_mirror() -> None:
    produced = _formatted(_generator().generate())
    assert_that(produced).described_as(
        "the polling twins are out of step; run python scripts/generate_poll_protocols.py"
    ).is_equal_to(_formatted(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8")))


def test_the_generated_verdict_twin_matches_the_views_it_mirrors() -> None:
    assert_that(_formatted(_generator().generate_verdict())).described_as(
        "the builder's verdict twin is out of step; run python scripts/generate_poll_protocols.py"
    ).is_equal_to(_formatted(pathlib.Path(_builder_check_typing.__file__).read_text(encoding="utf-8")))


class TestTheVerdictTwinOfAValueTheBuilderHolds:
    """What `check()` hands back after a pivot, where it used to hand back an untyped proxy."""

    def _declared(self) -> set[str]:
        return _names(pathlib.Path(_builder_check_typing.__file__).read_text(encoding="utf-8"), "_CheckAnyValue")

    def test_it_carries_no_operation_that_reaches_no_verdict(self) -> None:
        assert_that(self._declared() & set(WITHOUT_A_VERDICT)).described_as(
            "an operation that reaches no verdict cannot be asked for one"
        ).is_empty()

    def test_every_assertion_reaching_a_verdict_is_on_it(self) -> None:
        views = _names(pathlib.Path(_typing.__file__).read_text(encoding="utf-8"))
        skip = NOT_AN_OPERATION | set(WITHOUT_A_VERDICT) | _AFTER_A_CALL
        missing = {name for name in views - self._declared() - skip if not name.startswith("_")}
        assert_that(missing).described_as("asked of a value but not of a verdict on one").is_empty()

    def test_the_hook_and_the_negation_are_declared(self) -> None:
        assert_that(self._declared()).contains("not_", "__getattr__")

    @pytest.mark.parametrize(
        ("call", "passed"),
        [
            (lambda: assert_that([1, 2]).first().check().is_positive(), True),
            (lambda: assert_that([-1]).first().check().is_positive(), False),
            (lambda: assert_that(["ab"]).first().check().starts_with("a"), True),
            (lambda: assert_that([1]).first().check().not_.is_negative(), True),
        ],
        ids=["numeric-holds", "numeric-fails", "text", "negated"],
    )
    def test_the_runtime_answers_through_it(self, call, passed) -> None:
        assert_that(call().passed).is_equal_to(passed)

    def test_a_dynamic_assertion_still_reaches_the_proxy(self) -> None:
        # the reason the hook is declared, and the reason a typo stays the runtime's to name
        @dataclasses.dataclass
        class Order:
            status: str

        assert_that(assert_that(Order("PAID")).check().has_status("PAID").passed).is_true()
        with pytest.raises(AttributeError, match="has no assertion"):
            assert_that([1]).first().check().is_postive()


def _names(source: str, protocol: str | None = None) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef):
            continue
        if not (node.name == protocol if protocol else node.name.endswith("Assertion")):
            continue
        found |= {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
    return found


# the view reached through `when_called_with()`, never through `assert_that()`.  It adds these eight to
# the surface its value type would have, so the chain gives up its type at that pivot and they come off
# the hook rather than being declared for a chain over text
_AFTER_A_CALL = frozenset(
    {
        "caused_by",
        "contains_error",
        "does_not_contain_error",
        "error_of",
        "errors",
        "has_root_cause",
        "raised",
        "returned",
    }
)

# the chain's own accessors, which are not steps replayed on a builder
_THE_CHAIN_ITSELF = frozenset({"within", "every", "ignoring", "val", "close"})


class TestWhatTheTwinsCarry:
    def test_every_assertion_a_view_declares_is_reachable_on_a_chain(self) -> None:
        views = _names(pathlib.Path(_typing.__file__).read_text(encoding="utf-8"))
        twins = _names(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8"), "_SyncPoll")
        skip = NOT_AN_OPERATION | _AFTER_A_CALL | {name for name, kind in WITHOUT_A_VERDICT.items() if kind == POLLS}
        missing = {name for name in views - twins - skip if not name.startswith("_")}
        assert_that(missing).described_as("declared for a value but not for a chain over one").is_empty()

    def test_a_chain_cannot_start_another_one(self) -> None:
        twins = _names(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8"), "_SyncPoll")
        assert_that(twins & {name for name, kind in WITHOUT_A_VERDICT.items() if kind == POLLS}).is_empty()

    @pytest.mark.parametrize("flavour", ["_SyncPoll", "_AsyncPoll"])
    def test_the_knobs_and_the_hook_are_declared(self, flavour) -> None:
        twins = _names(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8"), flavour)
        assert_that(twins).contains("within", "every", "ignoring", "not_", "__getattr__")

    def test_every_declared_name_is_one_the_replay_can_answer(self) -> None:
        # a chain answers any name from its hook, so the parity question is about the builder the
        # steps are replayed on, not about the chain object
        twins = _names(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8"), "_SyncPoll")
        declared = {name for name in twins if not name.startswith("_") and name not in _THE_CHAIN_ITSELF}
        assert_that(sorted(declared - set(dir(AssertionBuilder)))).described_as(
            "promised on a chain and absent from the builder its steps replay on"
        ).is_empty()


class TestWhereAPivotLands:
    """A pivot keeps the chain's type where the view it lands on is one a value could have had."""

    def _returns(self, name: str) -> list[str]:
        found = []
        for node in ast.walk(ast.parse(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef) and node.name == "_SyncPoll":
                found = [
                    ast.unparse(item.returns)
                    for item in node.body
                    if isinstance(item, ast.FunctionDef) and item.name == name and item.returns is not None
                ]
        return found

    def test_an_element_pivot_keeps_what_the_landing_view_holds(self) -> None:
        assert_that(self._returns("first")).contains("_SyncPoll[str]", "_SyncPoll[_K]")

    def test_the_invoked_pivot_gives_the_type_up(self) -> None:
        # its view adds `raised()` and the seven others to what a chain over text would offer, so
        # calling the chain one over text would answer those off the hook and claim text for them
        assert_that(set(self._returns("when_called_with"))).is_equal_to({"_SyncPoll[Any]"})


class TestTheRuntimeAnswersThroughThem:
    @pytest.mark.parametrize(
        ("probe", "call"),
        [
            (lambda: 7, lambda chain: chain.is_positive()),
            (lambda: "ready", lambda chain: chain.starts_with("re")),
            (lambda: [1, 2], lambda chain: chain.contains(1)),
            (lambda: 7, lambda chain: chain.not_.is_negative()),
            (lambda: [1, 2], lambda chain: chain.within(1).every(0.01).is_length(2)),
        ],
        ids=["numeric", "text", "collection", "negated", "knobs"],
    )
    def test_a_declared_assertion_runs(self, probe, call) -> None:
        call(assert_that(probe).eventually_sync(timeout=0.5, trace=False))

    def test_a_name_no_declaration_lists_is_still_refused_at_run_time(self) -> None:
        """The measured cost of keeping the hook, written as a test rather than only as a comment.

        A dynamic assertion is resolved from the polled value's own attributes, so `has_status("PAID")`
        cannot be declared anywhere and the hook has to answer it.  With the hook there, a checker
        stops naming a typo, and only this is left to name it.
        """
        chain = assert_that(lambda: 7).eventually_sync(timeout=0.2, trace=False)
        with pytest.raises(AttributeError, match="has no assertion"):
            chain.no_such_assertion()

    def test_awaiting_a_chain_hands_back_a_builder_over_the_polled_value(self) -> None:
        async def probe() -> int:
            return 7

        async def run() -> None:
            settled = await assert_that(probe).eventually(timeout=0.5, trace=False).is_positive()
            assert_that(settled).is_instance_of(AssertionBuilder)
            assert_that(settled.val).is_equal_to(7)

        asyncio.run(run())

    def test_a_dynamic_assertion_still_polls(self) -> None:
        class _Order:
            def __init__(self) -> None:
                self.polls = 0

            @property
            def status(self) -> str:
                self.polls += 1
                return "PAID" if self.polls > 1 else "PENDING"

        order = _Order()
        assert_that(lambda: order).eventually_sync(timeout=1, interval=0.01, trace=False).has_status("PAID")
        assert_that(order.polls).is_greater_than(1)
