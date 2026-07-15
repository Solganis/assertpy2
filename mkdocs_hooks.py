"""MkDocs build hooks.

Strip the `<!-- docs-guard: skip -->` markers (used by tests/test_docs_examples.py to flag
non-executable code blocks) from the rendered HTML, so they live only in the repo markdown and
never ship to the site.
"""

from __future__ import annotations

import re

_MARKER = re.compile(r"[ \t]*<!-- docs-guard: skip -->[ \t]*\n?")


def on_post_page(output: str, **_kwargs: object) -> str:
    return _MARKER.sub("", output)
