"""Hold the typed surface as a consumer receives it, from an installed wheel rather than this checkout.

Every other typing gate reads the working tree, where `py.typed` and the `_engine` package are present
because they are files on disk.  A consumer gets whatever the wheel contains, and the two are the same
only for as long as the packaging says so.  Dropping `py.typed` from the build, or excluding a
subpackage, turns the whole typed surface into `Unknown` for every user while every gate here stays
green: the checkers would still be reading the checkout.

Deliberately small.  What the overloads resolve to is `tests/typing_integrations.py`'s question and it
is answered against real libraries there.  This one asks whether a checker can see them at all.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import venv
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pathlib

pytest.importorskip("mypy", reason="the lint job installs the typecheck group and this cell does not")

from assertpy2 import assert_that
from tests import typing_harness

# a value with no capability, so the answer names the narrowed view and not the builder: a checker
# reading nothing at all would answer `Any` here and the `assert_type` would pass on emptiness
_CONSUMER = """from typing import assert_type

from assertpy2 import assert_that
from assertpy2._engine._typing import _ObjectAssertion, _StringAssertion


class Plain:
    name: str


def resolution(plain: Plain, text: str) -> None:
    assert_type(assert_that(plain), _ObjectAssertion[Plain])
    assert_type(assert_that(text), _StringAssertion)
    assert_that(plain).is_positive()
"""


@pytest.fixture(scope="module")
def consumer(tmp_path_factory) -> tuple[pathlib.Path, pathlib.Path]:
    """A throwaway environment with the wheel installed, plus a file that uses the typed surface."""
    root = tmp_path_factory.mktemp("wheel")
    # the executable rather than `-m uv`: uv is the project's build tool and is not a module in the
    # environment it manages, which is how the first version of this skipped without saying anything
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not on PATH, so the wheel cannot be built here")
    built = subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(root)],
        capture_output=True,
        text=True,
        cwd=typing_harness.ROOT,
        check=False,
    )
    wheels = sorted(root.glob("*.whl"))
    if built.returncode or not wheels:
        pytest.fail(f"the wheel could not be built: {(built.stderr or built.stdout)[-400:]}")
    environment = root / "venv"
    venv.create(environment, with_pip=True)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", str(wheels[0])], check=True)
    source = root / "consumer.py"
    source.write_text(_CONSUMER, encoding="utf-8")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", "mypy"], check=True)
    return python, source


def test_a_checker_reading_the_installed_wheel_sees_the_typed_surface(consumer) -> None:
    python, source = consumer
    # `--follow-imports=silent`, as the other typing gates use: without it `--strict` walks into the
    # installed package and reports its internals, which is a different question asked by another gate
    output = typing_harness.run(
        "mypy",
        "--strict",
        "--follow-imports=silent",
        "--python-executable",
        str(python),
        str(source),
        cwd=source.parent,
        python=str(python),
    )
    assert_that(output).described_as("the narrowing is not visible to a consumer").contains(
        '"_ObjectAssertion[Plain]" has no attribute "is_positive"'
    )
    # and nothing else about the consumer file: an unresolved import or a missing `py.typed` lands
    # there as its own diagnostic, which is exactly the packaging mistake this exists to catch
    other = [
        line for line in output.splitlines() if ": error:" in line and source.name in line and "is_positive" not in line
    ]
    assert_that(other).described_as("the wheel is missing something a checker needs").is_empty()
