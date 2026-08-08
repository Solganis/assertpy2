"""Guard the two claims the project makes about its own type checking.

The README badge and `docs/concepts/type-safety.md` promise that ty, mypy ``--strict`` and Pyright all
run against ``tests/test_typing.py`` **with zero suppressions**.  That is prose, and prose drifts: one
``# type: ignore`` added to silence an inconvenient checker would leave the badge saying something
untrue with nothing to notice.  The first test below turns the sentence into a gate.

The second is the project's own rule rather than a public claim: a suppression anywhere in the package
has to say why it is there, so the next reader can judge whether it still applies.  Both are cheap
checks over source text, which is exactly the shape of claim no other test can reach.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from assertpy2 import assert_that

_ROOT = pathlib.Path(__file__).resolve().parent.parent

# every form the three checkers honour, so silencing any one of them trips this
_SUPPRESSION = re.compile(r"#\s*(type:\s*ignore|ty:\s*ignore|pyright:\s*ignore|mypy:)")

_PACKAGE_FILES = sorted((_ROOT / "assertpy2").rglob("*.py"))


class TestThePinnedTypingSurfaceCarriesNoSuppressions:
    """`tests/test_typing.py` is the file the badge is about: 105 `assert_type` calls pinning every
    public overload.  A suppression in it would hide the very regression it exists to catch."""

    _SURFACE = _ROOT / "tests" / "test_typing.py"

    def test_no_checker_is_silenced(self):
        offenders = [
            f"line {number}: {line.strip()}"
            for number, line in enumerate(self._SURFACE.read_text(encoding="utf-8").splitlines(), start=1)
            if _SUPPRESSION.search(line)
        ]
        assert_that(offenders).described_as("suppressions in the pinned typing surface").is_empty()

    def test_the_surface_is_not_empty(self):
        # a guard over an emptied file passes forever; this is what keeps the one above meaningful
        assert_that(self._SURFACE.read_text(encoding="utf-8")).contains("assert_type(")

    def test_the_claim_is_still_made(self):
        # if the sentence goes, the gate above is orphaned and should go with it
        claim = (_ROOT / "docs" / "concepts" / "type-safety.md").read_text(encoding="utf-8")
        assert_that(claim).contains("zero suppressions").contains("tests/test_typing.py")


class TestEverySuppressionInThePackageSaysWhy:
    """A bare ``# ty: ignore[rule]`` is a decision with its reasoning thrown away.  Six months later
    nobody can tell whether the checker was wrong, the code was wrong, or the rule has since improved,
    so the suppression outlives whatever justified it."""

    @pytest.mark.parametrize("path", _PACKAGE_FILES, ids=lambda path: path.name)
    def test_the_rule_is_followed(self, path):
        unexplained = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = _SUPPRESSION.search(line)
            if not match:
                continue
            trailing = line[match.end() :]
            # the rule name in brackets is part of the suppression, the reason is whatever follows the
            # second `#` on the line
            if "#" not in trailing.split("]", 1)[-1]:
                unexplained.append(f"{path.name} line {number}: {line.strip()}")
        assert_that(unexplained).described_as("suppressions with no stated reason").is_empty()

    def test_the_scan_actually_finds_suppressions(self):
        # the package does carry some; a scan that matched nothing would pass the check above vacuously
        found = sum(
            1
            for path in _PACKAGE_FILES
            for line in path.read_text(encoding="utf-8").splitlines()
            if _SUPPRESSION.search(line)
        )
        assert_that(found).is_greater_than(0)
