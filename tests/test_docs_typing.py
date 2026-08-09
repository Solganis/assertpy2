"""Type-check the code examples in the README and the guide docs.

The badge promises three type checkers with zero suppressions, and the README's own first listing used
to fail all three: `has_name` on a dict is resolved dynamically at runtime and no protocol declares it.
Executing the snippets (test_docs_examples.py) cannot catch that, because the code runs perfectly well.

Three markers steer this guard, all invisible in the rendered page:

* ``<!-- docs-guard: skip -->``       the block is illustrative and not runnable, so neither guard reads it
* ``<!-- docs-guard: untyped -->``    the block runs but uses a dynamic assertion (``has_<attr>``), which
  is deliberately outside the typed surface. It is executed, and excluded from here.
* ``<!-- docs-guard: type-error -->`` the block demonstrates a rejection, so it has to fail the check.
  A counter-example that silently starts passing is how a page's promise rots unnoticed.

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
from tests.docs_fixtures import PAGE_FIXTURES

CHECKED_DOCS = [
    "README.md",
    "docs/guides/matchers.md",
    "docs/guides/assertions.md",
    "docs/guides/data.md",
    "docs/guides/errors.md",
    "docs/guides/fluent.md",
    "docs/guides/testing.md",
    "docs/concepts/type-safety.md",
    "docs/getting-started/quickstart.md",
    "docs/index.md",
    "docs/getting-started/migration.md",
    "docs/recipes.md",
]

# what the pages assume a reader already has in scope by the time they reach a later block, kept the
# same as the executing guard's namespace so a block cannot pass one and fail the other over an import
PREAMBLE = "import datetime, json, logging, re\nfrom pathlib import Path\nfrom assertpy2 import *  # noqa: F403\n"

SKIP_MARKERS = ("docs-guard: skip", "docs-guard: untyped")
TYPE_ERROR_MARKER = "docs-guard: type-error"


def _markers(example: CodeExample) -> list[str]:
    lines = pathlib.Path(example.path).read_text(encoding="utf-8").splitlines()
    window = lines[max(0, example.start_line - 3) : example.start_line]
    return [line for line in window if "docs-guard:" in line]


def _snippet(example: CodeExample, doc: str) -> str:
    return PREAMBLE + PAGE_FIXTURES.get(doc, "") + example.source


def _write_snippets(target: pathlib.Path) -> tuple[int, list[str]]:
    """Write every checkable block, and report which of them are the ones that must fail."""
    written = 0
    must_fail = []
    for doc in CHECKED_DOCS:
        for example in find_examples(doc):
            markers = _markers(example)
            if any(marker in line for line in markers for marker in SKIP_MARKERS):
                continue
            name = f"{doc.replace('/', '_').removesuffix('.md')}__{example.start_line}.py"
            (target / name).write_text(_snippet(example, doc), encoding="utf-8")
            written += 1
            if any(TYPE_ERROR_MARKER in line for line in markers):
                must_fail.append(name)
    return written, must_fail


def _check(target: pathlib.Path) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "ty", "check", "--output-format", "concise", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if ": error" in line]


def test_doc_examples_type_check(tmp_path: pathlib.Path) -> None:
    written, must_fail = _write_snippets(tmp_path)
    # a broken extractor would make this guard pass by checking nothing
    assert_that(written).is_greater_than(20)
    reported = _check(tmp_path)
    rejected = {name for name in must_fail for line in reported if name in line}
    diagnostics = [line for line in reported if not any(name in line for name in must_fail)]
    assert_that(diagnostics).described_as("type errors in documented examples").is_empty()
    assert_that(sorted(rejected)).described_as("counter-examples a checker still accepts").is_equal_to(
        sorted(must_fail)
    )
