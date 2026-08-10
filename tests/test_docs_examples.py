"""Execute the copy-paste code examples in the guide docs so they cannot silently rot.

The guarded pages are the ones whose python blocks are mostly runnable. Illustrative pseudo-context
blocks (``repo.find(42)``, a bare ``response``, ...) carry an HTML comment ``<!-- docs-guard: skip -->``
directly above their fence; that comment is invisible in the rendered site and tells this guard to
skip them. A new example is therefore either runnable or explicitly marked - it cannot slip through
unchecked.

``<!-- docs-guard: raises -->`` marks a block that shows what a failure looks like, so running it here
would fail the suite for doing what the page says it does. It is the mirror of test_docs_typing's
``untyped`` marker, and both exist rather than widening ``skip`` so that neither takes a block out of
both guards.
"""

from __future__ import annotations

import datetime
import inspect
import json
import logging
import pathlib
import re
import types

import pytest

pytest.importorskip("pytest_examples")

from pytest_examples import CodeExample, EvalExample, find_examples

import assertpy2
from tests.docs_fixtures import PAGE_FIXTURES, documented_pages

# Pages this guard does not run, each with the reason. Everything else is run, including a page added
# after this line was written: a hand-kept list of pages to check is a list that quietly stops growing.
UNRUN_DOCS = {
    "docs/concepts/type-safety.md": "several blocks are counter-examples that are supposed to fail",
    "docs/guides/testing.md": "the examples write snapshot files, which would be left behind in the repo",
    "docs/getting-started/comparison.md": "the blocks are the other library's API, not ours",
    "docs/extending/custom-assertions.md": "the page registers extensions process-wide and shows a failing call",
    "docs/extending/integrations.md": "the behave blocks need a library the coverage cell must not install",
}

GUARDED_DOCS = documented_pages(UNRUN_DOCS)

# assertpy2's public API minus its submodules (which shadow builtins like `dict`/`bytes`), plus the
# stdlib names the guide pages assume are already imported by the time a reader reaches a later block.
DOC_NAMESPACE = {
    name: getattr(assertpy2, name)
    for name in dir(assertpy2)
    if not name.startswith("_") and not isinstance(getattr(assertpy2, name), types.ModuleType)
}
DOC_NAMESPACE.update(datetime=datetime, re=re, json=json, logging=logging, Path=pathlib.Path)

SKIP_MARKERS = {
    "docs-guard: skip": "illustrative example, marked non-executable in the docs",
    "docs-guard: raises": "demonstrates a failure, marked as raising in the docs",
    "docs-guard: type-error": "counter-example, marked as rejected by a type checker",
}
_EXAMPLES = [example for doc in GUARDED_DOCS for example in find_examples(doc)]


def _skip_reason(example: CodeExample) -> str | None:
    """The reason this fence is not executed, or None (indentation-agnostic, so it works for blocks
    nested in lists/admonitions too)."""
    lines = pathlib.Path(example.path).read_text(encoding="utf-8").splitlines()
    window = lines[max(0, example.start_line - 3) : example.start_line]
    return next((reason for marker, reason in SKIP_MARKERS.items() for line in window if marker in line), None)


def _namespace(doc: str) -> dict[str, object]:
    """The globals a block on this page runs with: the shared one, plus the page's own fixture."""
    namespace = dict(DOC_NAMESPACE)
    fixture = PAGE_FIXTURES.get(doc)
    if fixture is not None:
        exec(fixture, namespace)  # the fixture is repo source, and the block itself is exec'd too
    return namespace


@pytest.mark.parametrize("example", _EXAMPLES, ids=str)
def test_doc_example_runs(example: CodeExample, eval_example: EvalExample) -> None:
    reason = _skip_reason(example)
    if reason is not None:
        pytest.skip(reason)
    namespace = _namespace(pathlib.Path(example.path).as_posix())
    module = eval_example.run(example, module_globals=namespace)
    # an example written as a pytest test only binds the function, so running the module never reaches
    # the assertions in its body. Call the ones that ask for no fixtures, and the body is checked too
    for name, value in module.items():
        if name.startswith("test_") and callable(value) and not inspect.signature(value).parameters:
            value()
