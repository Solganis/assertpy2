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

One test per page, blocks in document order. A guide is written as a narrative and its blocks build on
each other through whatever the library holds process-wide: `matchers.md` registers a matcher in one
block and removes it in another, which passed only while the suite happened to run them in that order.
Under a shuffling runner two seeds in four went red. A failure names the block it came from.
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
from assertpy2 import matchers
from tests.docs_fixtures import PAGE_FIXTURES, documented_pages

# pages this guard does not run, with reasons: a hand-kept list of pages to check stops growing quietly
UNRUN_DOCS = {
    "docs/concepts/type-safety.md": "several blocks are counter-examples that are supposed to fail",
    "docs/guides/testing.md": "the examples write snapshot files, which would be left behind in the repo",
    "docs/extending/custom-assertions.md": "the page registers extensions process-wide and shows a failing call",
    "docs/extending/integrations.md": "the behave blocks need a library the coverage cell must not install",
}

GUARDED_DOCS = documented_pages(UNRUN_DOCS)

# the public API minus submodules shadowing builtins, plus the stdlib names a later block assumes
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
# grouped by page in document order: a block may register a matcher the block below removes.
# Python state is fresh per block, so only what the library holds process-wide carries over
_PAGES = {doc: sorted(find_examples(doc), key=lambda example: example.start_line) for doc in GUARDED_DOCS}


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
        exec(fixture, namespace)
    return namespace


def _run(example: CodeExample, eval_example: EvalExample) -> None:
    namespace = _namespace(pathlib.Path(example.path).as_posix())
    module = eval_example.run(example, module_globals=namespace)
    # an example written as a test only binds it, so the fixture-free ones are called and their bodies checked
    for name, value in module.items():
        if name.startswith("test_") and callable(value) and not inspect.signature(value).parameters:
            value()


@pytest.fixture
def _matchers_restored():
    """The registry a page's blocks write to, emptied first and put back after.

    Both halves matter: restoring keeps a page out of the rest of the suite, and emptying keeps the rest
    of the suite out of the page, so a name a guide registers cannot clash with one left behind.
    """
    saved = dict(matchers._custom_matchers)
    matchers._custom_matchers.clear()
    try:
        yield
    finally:
        matchers._custom_matchers.clear()
        matchers._custom_matchers.update(saved)


@pytest.mark.parametrize("doc", list(_PAGES), ids=str)
@pytest.mark.usefixtures("_matchers_restored")
def test_doc_examples_run(doc: str, eval_example: EvalExample) -> None:
    ran = 0
    for example in _PAGES[doc]:
        if _skip_reason(example) is not None:
            continue
        try:
            _run(example, eval_example)
        except Exception as failure:
            raise AssertionError(f"{doc}:{example.start_line}-{example.end_line}: {failure!r}") from failure
        ran += 1
    if ran == 0:
        pytest.skip("every block on this page is marked non-executable")
