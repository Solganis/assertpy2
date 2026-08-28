"""Run the three checkers over one file and read back what each reported, per line.

Split out of `test_typing_negative.py` when the integration matrix needed the same three parsers.  The
parsing is the whole of it: each checker names its diagnostics differently, and comparing them at all
means reducing three output formats to `{line: {code}}`.

The environment is passed rather than discovered.  `ty` picks its environment from `VIRTUAL_ENV`, then
from a `.venv` beside the project, and its target version from `requires-python`'s lower bound, none of
which is visible in the result.  A checker that silently resolved a different interpreter reports on a
different set of installed packages, so `environments()` records what each one actually used.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Final

ROOT = pathlib.Path(__file__).resolve().parent.parent

Reported = dict[int, set[str]]


def tagged_lines(path: pathlib.Path) -> dict[int, str]:
    """Line number to case name, read from the tags in the source rather than kept in step by hand."""
    found = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        tag = re.search(r"# case: ([\w-]+)", line)
        if tag:
            found[number] = tag.group(1)
    return found


PYRIGHT_ENGINE: Final = "1.1.413"
"""The pyright build every gate here asks for, rather than whichever one the wrapper defaults to.

The `pyright` distribution on PyPI is a launcher for a node package, and the two move at different
speeds: PyPI stopped at 1.1.411 on 25 June while npm has shipped 1.1.412 and 1.1.413 since. Pinning the
version through the wrapper's own variable is what keeps a contributor, CI and this table looking at
the same checker.

One build rather than whichever the launcher resolves, because every recorded number here was recorded
against one. Measured today on both: 169 diagnostics for the package under each, so the pin buys
reproducibility rather than a behaviour difference. It was originally taken for `TypeForm`, which 1.1.411
refuses a union against, and that construct is no longer in the package.
"""


def checker_env() -> dict[str, str]:
    """The environment a checker subprocess needs, with the engine pinned."""
    return {**os.environ, "PYRIGHT_PYTHON_FORCE_VERSION": PYRIGHT_ENGINE}


def run(*command: str, cwd: pathlib.Path | None = None, python: str | None = None) -> str:
    """Run a checker and hand back everything it said.

    `cwd` defaults to the project root, which is what the gates reading the working tree want.  A gate
    reading an *installed* package has to pass somewhere else: a checker resolves imports from its
    working directory first, so run it from the root and it reads this checkout no matter which
    interpreter it was pointed at.
    """
    result = subprocess.run(
        [python or sys.executable, "-m", *command],
        capture_output=True,
        text=True,
        cwd=cwd or ROOT,
        check=False,
        env=checker_env(),
    )
    # every one of them exits non-zero as soon as it reports anything, so the output is what to read
    return result.stdout + result.stderr


def pyright(path: pathlib.Path, *options: str) -> Reported:
    report = json.loads(run("pyright", "--outputjson", *options, str(path)))
    found: Reported = {}
    for item in report["generalDiagnostics"]:
        found.setdefault(item["range"]["start"]["line"] + 1, set()).add(item.get("rule", item["severity"]))
    return found


def mypy(path: pathlib.Path, *options: str) -> Reported:
    output = run("mypy", "--strict", "--follow-imports=silent", *options, str(path))
    found: Reported = {}
    for number, code in re.findall(rf"{re.escape(path.name)}:(\d+): error:.*\[([\w-]+)\]", output):
        found.setdefault(int(number), set()).add(code)
    return found


def ty(path: pathlib.Path, *options: str) -> Reported:
    output = run("ty", "check", "--output-format", "concise", *options, str(path))
    found: Reported = {}
    for number, code in re.findall(rf"{re.escape(path.name)}:(\d+):\d+: error\[([\w-]+)\]", output):
        found.setdefault(int(number), set()).add(code)
    return found


def by_case(reported: dict[str, Reported], path: pathlib.Path) -> dict[str, dict[str, set[str]]]:
    """Case name to the codes each checker reported for it."""
    return {
        name: {checker: found.get(number, set()) for checker, found in reported.items()}
        for number, name in tagged_lines(path).items()
    }
