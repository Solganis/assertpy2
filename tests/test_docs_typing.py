"""Type-check the code examples in the README and the guide docs.

The badge promises three type checkers with zero suppressions, and the README's own first listing used
to fail all three: `has_name` on a dict is resolved dynamically at runtime and no protocol declares it.
Executing the snippets (test_docs_examples.py) cannot catch that, because the code runs perfectly well.

Two markers steer this guard, both invisible in the rendered page:

* ``<!-- docs-guard: skip -->``    the block is illustrative and not runnable, so neither guard reads it
* ``<!-- docs-guard: untyped -->`` the block runs but uses a dynamic assertion (``has_<attr>``), which
  is deliberately outside the typed surface. It is executed, and excluded from here.

Anything else has to type-check, which also means this guard reports the reverse of what
test_protocol_parity.py reports: parity proves every declared method exists, this proves the methods
the docs actually use are declared.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

pytest.importorskip("pytest_examples")

from pytest_examples import CodeExample, find_examples

from assertpy2 import assert_that

CHECKED_DOCS = [
    "README.md",
    "docs/guides/matchers.md",
    "docs/guides/assertions.md",
    "docs/guides/data.md",
    "docs/index.md",
    "docs/getting-started/migration.md",
    "docs/recipes.md",
]

# what the pages assume a reader already has in scope by the time they reach a later block
PREAMBLE = "import datetime, json, re\nfrom pathlib import Path\nfrom assertpy2 import *  # noqa: F403\n"

SKIP_MARKERS = ("docs-guard: skip", "docs-guard: untyped")


def _is_marked(example: CodeExample) -> bool:
    lines = pathlib.Path(example.path).read_text(encoding="utf-8").splitlines()
    window = lines[max(0, example.start_line - 3) : example.start_line]
    return any(marker in line for line in window for marker in SKIP_MARKERS)


def _write_snippets(target: pathlib.Path) -> int:
    written = 0
    for doc in CHECKED_DOCS:
        for example in find_examples(doc):
            if _is_marked(example):
                continue
            name = f"{doc.replace('/', '_').removesuffix('.md')}__{example.start_line}.py"
            (target / name).write_text(PREAMBLE + example.source, encoding="utf-8")
            written += 1
    return written


def test_doc_examples_type_check(tmp_path: pathlib.Path) -> None:
    written = _write_snippets(tmp_path)
    # a broken extractor would make this guard pass by checking nothing
    assert_that(written).is_greater_than(20)
    result = subprocess.run(
        [sys.executable, "-m", "ty", "check", "--output-format", "concise", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    diagnostics = [line for line in result.stdout.splitlines() if ": error" in line]
    assert_that(diagnostics).described_as("type errors in documented examples").is_empty()
