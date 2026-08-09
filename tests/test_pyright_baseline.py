"""Hold the package-wide pyright surface to what `pyright_baseline.py` records.

CI gates pyright on `tests/test_typing.py`. The package itself was ungated, so a diagnostic introduced
anywhere in it went unreported.

Skipped where pyright is absent: it lives in the `typecheck` group, so this runs in the type-check job
rather than in the main suite.
"""

from __future__ import annotations

import collections
import json
import pathlib
import subprocess
import sys

import pytest

pytest.importorskip("pyright")

from assertpy2 import assert_that
from tests.pyright_baseline import BASELINE

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _observed() -> dict[tuple[str, str], int]:
    result = subprocess.run(
        [sys.executable, "-m", "pyright", "--outputjson", "assertpy2/"],
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )
    # pyright exits non-zero whenever it reports anything, so the payload is what to read, not the code
    report = json.loads(result.stdout)
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for item in report["generalDiagnostics"]:
        relative = pathlib.Path(item["file"]).resolve().relative_to(_ROOT).as_posix()
        counts[(relative, item.get("rule", item["severity"]))] += 1
    return dict(counts)


def test_no_unrecorded_pyright_diagnostics() -> None:
    observed = _observed()
    # the run itself has to have happened: an empty report would pass every comparison below
    assert_that(observed).is_not_empty()

    appeared = {key: count for key, count in observed.items() if count > BASELINE.get(key, 0)}
    assert_that(appeared).described_as("pyright diagnostics not recorded in pyright_baseline.py").is_empty()

    resolved = {key: count for key, count in BASELINE.items() if count > observed.get(key, 0)}
    assert_that(resolved).described_as("recorded in pyright_baseline.py but no longer reported").is_empty()
