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
import pathlib
import re
import subprocess
import sys

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


def run(*command: str) -> str:
    result = subprocess.run([sys.executable, "-m", *command], capture_output=True, text=True, cwd=ROOT, check=False)
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
