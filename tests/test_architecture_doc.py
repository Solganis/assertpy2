"""Hold `ARCHITECTURE.md` to naming things that exist.

A map of the typed surface is worth having and worth distrusting.  It is prose, so nothing executes it,
and it names four generated files, two scripts, thirteen gates and a handful of registries by hand.  A
rename anywhere in that list leaves the document quietly wrong, which is worse than not having one: a
contributor who follows a stale map spends their time in the wrong place and then does not trust the
rest of it either.

Three rounds of review on the document itself found six false statements in it, so the risk is not
theoretical.  What a test can check is the cheap half: that every path it names exists, and that every
name it uses, standing alone or inside a code fragment, is one the tree actually carries.  Whether the
*explanations* are still true is what review is for.
"""

from __future__ import annotations

import ast
import io
import pathlib
import re
import tokenize

from assertpy2 import assert_that

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_DOC = _ROOT / "ARCHITECTURE.md"

# tokens that are Python or prose rather than something this repository owns
_NOT_OURS = frozenset(
    {
        "Any",
        "Self",
        "assert_type",
        "isinstance",
        "ty",
    }
)

_TREE = ("assertpy2", "tests", "scripts")


def _quoted() -> list[str]:
    return sorted(set(re.findall(r"`([^`\n]+)`", _DOC.read_text(encoding="utf-8"))))


def _looks_like_a_path(token: str) -> bool:
    return "/" in token or token.endswith((".py", ".json", ".md"))


def _resolves(token: str) -> bool:
    """Whether the repository holds what this token names.

    Three spellings, because the document uses all three and each is the readable one in its place: the
    full path, a path relative to the package once the directory is established (`_engine/_typing.py`),
    and a bare filename once the directory is obvious from the sentence (`test_typing.py`).
    """
    if "*" in token:
        return any(_ROOT.glob(token))
    trimmed = token.rstrip("/")
    if "/" in trimmed or token.endswith("/"):
        return (_ROOT / trimmed).exists() or any((_ROOT / directory / trimmed).exists() for directory in _TREE)
    return any(found.name == trimmed for directory in _TREE for found in (_ROOT / directory).rglob(trimmed))


def _is_an_identifier(token: str) -> bool:
    return token.split("[")[0].isidentifier() and token not in _NOT_OURS


def _names_in(fragment: str) -> list[str]:
    """The identifiers a backticked code fragment uses, when it is one.

    `assert_that(1).is_positive()` names two things a rename can break, and neither is an identifier by
    itself.  Reading them out of the parse is the only way a typo inside a fragment is visible at all.
    """
    try:
        tree = ast.parse(fragment.strip("()"), mode="eval")
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.append(node.id)
        elif isinstance(node, ast.Attribute):
            found.append(node.attr)
    return [name for name in found if name not in _NOT_OURS]


def _defined_names() -> set[str]:
    """Every name the tree actually uses, from the token stream rather than from the text.

    Substring matching passed `DictAssertion` because `_DictAssertion` contains it, and counted names
    that appear only inside a comment or a string literal.  `tokenize` answers neither.
    """
    found: set[str] = set()
    for directory in _TREE:
        for source in (_ROOT / directory).rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            try:
                for token in tokenize.generate_tokens(io.StringIO(text).readline):
                    if token.type == tokenize.NAME:
                        found.add(token.string)
            except (tokenize.TokenError, IndentationError, SyntaxError):  # pragma: no cover - every file parses
                continue
    return found


def test_every_path_it_names_exists() -> None:
    paths = [token for token in _quoted() if _looks_like_a_path(token)]
    # the document is mostly a table of files, so a run that found few of them read the wrong thing
    assert_that(paths).described_as("paths quoted in the document").is_length_between(10, 100)

    missing = [token for token in paths if not _resolves(token)]
    assert_that(missing).described_as("paths ARCHITECTURE.md names that do not exist").is_empty()


def test_every_name_it_names_is_in_the_tree() -> None:
    """Catches a rename, which is the way a document like this goes wrong without anyone noticing."""
    quoted = [token for token in _quoted() if not _looks_like_a_path(token)]
    names = [token.split("[")[0] for token in quoted if _is_an_identifier(token)]
    # both halves matter: the bare identifiers, and the ones only a code fragment mentions
    names += [name for token in quoted if not _is_an_identifier(token) for name in _names_in(token)]
    # a floor rather than a count: the document is edited for brevity and the number moves, but a run that
    # found a handful read the wrong file or stopped matching
    assert_that(names).described_as("identifiers quoted in the document").is_length_between(10, 200)

    defined = _defined_names()
    missing = sorted({name for name in names if name not in defined})
    assert_that(missing).described_as("names ARCHITECTURE.md uses that are nowhere in the tree").is_empty()


def test_the_contributing_guide_still_points_at_it() -> None:
    """The document is only worth writing if the file contributors do read sends them to it."""
    guide = (_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert_that(guide).described_as("CONTRIBUTING.md").contains("ARCHITECTURE.md")
