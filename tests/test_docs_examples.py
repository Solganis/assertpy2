"""Execute the copy-paste code examples in the guide docs so they cannot silently rot.

The guarded pages are the ones whose python blocks are mostly runnable. Illustrative pseudo-context
blocks (``repo.find(42)``, a bare ``response``, ...) carry an HTML comment ``<!-- docs-guard: skip -->``
directly above their fence; that comment is invisible in the rendered site and tells this guard to
skip them. A new example is therefore either runnable or explicitly marked - it cannot slip through
unchecked.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import types

import pytest

pytest.importorskip("pytest_examples")

from pytest_examples import CodeExample, EvalExample, find_examples

import assertpy2

GUARDED_DOCS = [
    "docs/guides/matchers.md",
    "docs/guides/assertions.md",
    "docs/guides/data.md",
    "docs/index.md",
    "docs/getting-started/migration.md",
]

# assertpy2's public API minus its submodules (which shadow builtins like `dict`/`bytes`), plus the
# stdlib names the guide pages assume are already imported by the time a reader reaches a later block.
DOC_NAMESPACE = {
    name: getattr(assertpy2, name)
    for name in dir(assertpy2)
    if not name.startswith("_") and not isinstance(getattr(assertpy2, name), types.ModuleType)
}
DOC_NAMESPACE.update(datetime=datetime, re=re, json=json, Path=pathlib.Path)

SKIP_MARKER = "docs-guard: skip"
_EXAMPLES = [example for doc in GUARDED_DOCS for example in find_examples(doc)]


def _is_marked_skip(example: CodeExample) -> bool:
    """True if the fence is preceded by the skip marker (indentation-agnostic, so it works for
    blocks nested in lists/admonitions too)."""
    lines = pathlib.Path(example.path).read_text(encoding="utf-8").splitlines()
    window = lines[max(0, example.start_line - 3) : example.start_line]
    return any(SKIP_MARKER in line for line in window)


@pytest.mark.parametrize("example", _EXAMPLES, ids=str)
def test_doc_example_runs(example: CodeExample, eval_example: EvalExample) -> None:
    if _is_marked_skip(example):
        pytest.skip("illustrative example, marked non-executable in the docs")
    eval_example.run(example, module_globals=dict(DOC_NAMESPACE))
