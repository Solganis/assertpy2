"""The guard that stops a skipped gate from reading as a passing one.

A dependency that is not installed does not fail a run, it skips it, and a skipped gate leaves no mark
in a green summary.  That cost two red CI runs in one day: `pytest-examples` lives in its own group,
was absent locally, and the whole doc-example file was skipped while the run was reported as passing.

The guard lives in `tests/conftest.py` and is loaded here as a plugin rather than copied, so what these
cases exercise is the shipped one.
"""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys

from assertpy2 import assert_that

_ROOT = pathlib.Path(__file__).resolve().parent.parent

_SUITE = """
import pytest

pytest.importorskip("a_module_that_is_not_installed")


def test_never_reached():
    raise AssertionError
"""


_PASSES = """
def test_ok():
    assert True
"""


def _run(tmp_path: pathlib.Path, *extra: str, suite: str = _SUITE) -> subprocess.CompletedProcess[str]:
    # a second passing file, so the exit code reports the guard and not pytest's "nothing was collected"
    (tmp_path / "test_absent.py").write_text(suite, encoding="utf-8")
    (tmp_path / "test_present.py").write_text(_PASSES, encoding="utf-8")
    # its own coverage database: the child runs from the root, and a shared one would pad the gate under test
    environment = {**os.environ, "COVERAGE_FILE": str(tmp_path / ".coverage")}
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "tests.conftest", "-p", "no:cacheprovider", *extra],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        env=environment,
        check=False,
    )


def test_a_run_claiming_completeness_fails_on_a_missing_module(tmp_path):
    """The coverage floor is the claim: only the cell that enforces it promises every gate ran."""
    result = _run(tmp_path, "--cov=assertpy2", "--cov-fail-under=1")
    assert_that(result.returncode).described_as("exit code").is_equal_to(1)
    assert_that(result.stdout).described_as("the report").contains(
        "gates skipped for a missing module", "a_module_that_is_not_installed"
    )


def test_a_skip_that_says_why_is_left_alone(tmp_path):
    """The seam between an accident and a decision: a hand-written reason replaces pytest's own wording.

    A few gates are delegated on purpose, the checkers to the lint job and allure and behave to their own,
    and those say so where they skip.  Writing the reason is what makes the difference visible in the
    source rather than in a register somewhere else.
    """
    reasoned = _SUITE.replace(
        'importorskip("a_module_that_is_not_installed")',
        'importorskip("a_module_that_is_not_installed", reason="delegated to another job")',
    )
    result = _run(tmp_path, "--cov=assertpy2", "--cov-fail-under=1", suite=reasoned)
    assert_that(result.returncode).described_as("exit code").is_equal_to(0)
    assert_that(result.stdout).described_as("the report").does_not_contain("gates skipped for a missing module")


def test_a_partial_run_is_left_alone(tmp_path):
    """Without that claim the same skip is an ordinary partial run, which contributors do all day."""
    result = _run(tmp_path, "--no-cov")
    assert_that(result.returncode).described_as("exit code").is_equal_to(0)
    assert_that(result.stdout).described_as("the report").does_not_contain("gates skipped for a missing module")


# the checkers, named rather than read off the dependency groups, which do not line up: `typecheck` also
# holds stubs, `ty` sits in `dev`, and the coverage cell leaves `typecheck` out
_DELEGATED = frozenset({"pyright", "mypy", "pyrefly", "ty"})


def test_every_checker_skip_says_why_it_is_delegated() -> None:
    """The class, not the instance.

    Four files were given the reason by hand and two were missed, because the list was typed out rather
    than swept, and the guard went red in CI on exactly those two.  Read from the source instead, over
    the whole tree rather than its top level, so a file added later is read too.

    It recognises the one spelling this suite uses, `<anything>.importorskip("name", reason=...)`.  A
    bare `importorskip` imported from pytest, or a module name passed as a keyword or computed, goes
    unseen; a positional reason is seen and reported as missing.  Neither shape appears here.
    """
    tests = pathlib.Path(__file__).resolve().parent
    unexplained = []
    for path in sorted(tests.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "attr", "") != "importorskip":
                continue
            first = node.args[0] if node.args else None
            named = isinstance(first, ast.Constant) and first.value in _DELEGATED
            if named and not any(keyword.arg == "reason" for keyword in node.keywords):
                unexplained.append(f"{path.name}:{node.lineno} {first.value}")
    assert_that(unexplained).described_as("checker skips with no reason written").is_empty()
