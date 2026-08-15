"""Report what an environment holds, run by `run.py` with that environment's own interpreter.

Prints one JSON object: every installed distribution and the requirements it carries, with markers
already evaluated here, where the interpreter and platform are the ones that matter.

`packaging` does the parsing.  By hand, both halves went wrong: a marker is not always a bare
`extra == "..."`, and `jsonpath-ng` and `jsonpath_ng` are one name only after canonicalisation.
"""

from __future__ import annotations

import contextlib
import json
from importlib.metadata import distributions
from typing import Any

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def _reading(requirement: Requirement, candidates: tuple[str, ...]) -> dict[str, Any]:
    """One requirement as data: what it names, which extras it wants of it, and when it applies.

    `applies` lists the extras of the *depending* distribution that switch this requirement on.  Empty,
    with `always` true, means it applies regardless.  The marker is evaluated here, where the
    interpreter and the platform are the ones that matter.
    """
    switches = [
        extra
        for extra in candidates
        if requirement.marker is not None and requirement.marker.evaluate({"extra": extra})
    ]
    unconditional = requirement.marker is None or requirement.marker.evaluate({"extra": ""})
    return {
        "name": canonicalize_name(requirement.name),
        "wants": sorted(canonicalize_name(extra) for extra in requirement.extras),
        "applies": [] if unconditional else switches,
        "always": unconditional,
    }


def _read(text: str, candidates: tuple[str, ...]) -> dict[str, Any]:
    """One requirement string, or a note that it could not be read: never a guess."""
    try:
        return _reading(Requirement(text), candidates)
    except Exception as refusal:  # whatever `packaging` refuses to read, the caller has to hear about
        return {"name": "", "wants": [], "applies": [], "always": True, "unreadable": f"{text}: {refusal}"}


def _candidate_extras() -> tuple[str, ...]:
    """Every extra name this environment mentions, from the two places a specification puts them.

    `Provides-Extra` is where a distribution declares its own, and `Requirement.extras` is where one
    asks for somebody else's.  Between them they cover every extra that can switch a requirement on.

    An earlier version also scraped names out of rendered markers with a regex, which read `extra ==
    "x"` and missed `extra in "x,y"`, the reversed operand order and anything else PEP 508 allows.  A
    partial scrape is worse than none: it looks like coverage.
    """
    found: set[str] = set()
    for distribution in distributions():
        found.update(canonicalize_name(extra) for extra in distribution.metadata.get_all("Provides-Extra") or ())
        for text in distribution.requires or []:
            with contextlib.suppress(Exception):
                found.update(canonicalize_name(extra) for extra in Requirement(text).extras)
    return tuple(sorted(found))


def _inventory() -> dict[str, list[dict[str, Any]]]:
    candidates = _candidate_extras()
    found: dict[str, list[dict[str, Any]]] = {}
    for distribution in distributions():
        name = distribution.metadata["Name"]
        if not name:
            continue
        found[canonicalize_name(name)] = [_read(text, candidates) for text in distribution.requires or []]
    return found


if __name__ == "__main__":
    print(json.dumps(_inventory()))
