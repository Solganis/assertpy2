"""The compatibility gate: what changed in the public surface, and whether it may change that way.

A caller breaks on things no other guard here watches. A parameter renamed, a default dropped, a
keyword argument becoming positional, an exported name quietly gone: each of those passes the type
checker, passes the suite, and fails in someone else's test run after an upgrade.

So the surface is snapshotted and compared. The comparison is not "did anything move" but "how did it
move", because the four kinds of movement carry different obligations:

* **breaking** - a caller that worked stops working. Needs a major, or must not ship.
* **behaviour** - the call still binds, but does something else: a default value changed. A minor, and
  the release notes name it under behaviour changes.
* **addition** - new names, new optional parameters, a parameter accepting one more way of being passed.
  A minor.
* **typing** - annotations only, the runtime is unchanged. A minor, and the release notes say so.
* **internal** - never reaches this file, because private names are not collected.

Updating the snapshot is deliberate and visible: run with `ASSERTPY2_UPDATE_API=1`, and the diff of
`api_snapshot.json` is what review reads.
"""

from __future__ import annotations

import copy
import json
import os
import pathlib
from typing import ClassVar

import pytest
from api_surface import collect

from assertpy2 import assert_that

SNAPSHOT = pathlib.Path(__file__).parent / "api_snapshot.json"


def _stored() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _write(surface: dict) -> None:
    SNAPSHOT.write_text(json.dumps(surface, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _parameters(entry: dict) -> dict[str, dict]:
    return {parameter["name"]: parameter for parameter in entry.get("parameters", [])}


def _positional(entry: dict) -> list[str]:
    """The names a caller may pass positionally, in the order they must be passed.

    Compared as a sequence rather than as a set: swapping two of them, or slipping an optional one in
    front of an existing one, keeps every name and still rebinds every positional call at the site.
    """
    return [
        parameter["name"]
        for parameter in entry.get("parameters", [])
        if parameter["kind"] in ("POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD")
    ]


# how a parameter may change the ways it can be passed.  Widening is an addition: a caller that worked
# still works and gains a spelling.  Narrowing takes a spelling away, so it breaks
_WIDENING = {
    ("POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD"),
    ("KEYWORD_ONLY", "POSITIONAL_OR_KEYWORD"),
}


def _callable_changes(path: str, before: dict, after: dict) -> list[tuple[str, str]]:
    """How one callable moved, as (severity, description) pairs."""
    changes: list[tuple[str, str]] = []
    old, new = _parameters(before), _parameters(after)
    for name, parameter in old.items():
        if name not in new:
            changes.append(("breaking", f"{path}: parameter '{name}' removed"))
        else:
            changes.extend(_parameter_changes(path, name, parameter, new[name]))
    changes.extend(
        (
            "breaking" if parameter["required"] else "addition",
            f"{path}: parameter '{name}' added ({_need(parameter)})",
        )
        for name, parameter in new.items()
        if name not in old
    )
    old_order, new_order = _positional(before), _positional(after)
    if old_order != new_order[: len(old_order)]:
        changes.append(("breaking", f"{path}: positional order changed from {old_order} to {new_order}"))
    if before.get("returns") != after.get("returns"):
        changes.append(("typing", f"{path}: returns {after.get('returns')} instead of {before.get('returns')}"))
    if before.get("kind") != after.get("kind"):
        changes.append(("breaking", f"{path}: is a {after.get('kind')} instead of a {before.get('kind')}"))
    return changes


def _owned(construction: str | None) -> bool:
    """Whether the package itself defines the call, rather than inheriting it from somewhere else."""
    return construction is None or construction == "assertpy2" or construction.startswith("assertpy2.")


def _need(parameter: dict) -> str:
    return "required" if parameter["required"] else "optional"


def _parameter_changes(path: str, name: str, before: dict, after: dict) -> list[tuple[str, str]]:
    """How one parameter moved, each rule its own line rather than a nest of branches."""
    changes = []
    if after["kind"] != before["kind"]:
        severity = "addition" if (before["kind"], after["kind"]) in _WIDENING else "breaking"
        changes.append((severity, f"{path}: parameter '{name}' is now {after['kind']}, was {before['kind']}"))
    if after["required"] and not before["required"]:
        changes.append(("breaking", f"{path}: parameter '{name}' lost its default"))
    if not after["required"] and before["required"]:
        changes.append(("addition", f"{path}: parameter '{name}' gained a default"))
    if after.get("default") != before.get("default") and after["required"] == before["required"]:
        # both labels on purpose: the call still binds, and it now does something else.  Whoever reads
        # the gate has to see that this is not a free minor
        moved = f"{path}: parameter '{name}' defaults to {after.get('default')}, was {before.get('default')}"
        changes.extend([("behaviour", moved), ("breaking", moved)])
    if after["annotation"] != before["annotation"]:
        changes.append(("typing", f"{path}: parameter '{name}' is now typed {after['annotation']}"))
    return changes


def _section_changes(section: str, before: dict, after: dict) -> list[tuple[str, str]]:
    changes: list[tuple[str, str]] = []
    changes.extend(("breaking", f"{section}.{name} removed") for name in sorted(set(before) - set(after)))
    changes.extend(("addition", f"{section}.{name} added") for name in sorted(set(after) - set(before)))
    for name in sorted(set(before) & set(after)):
        old, new = before[name], after[name]
        if old.get("construction") != new.get("construction"):
            changes.append(("breaking", f"{section}.{name}: construction moved to {new.get('construction')}"))
        elif _owned(old.get("construction")):
            changes.extend(_callable_changes(f"{section}.{name}", old, new))
        else:
            # the signature belongs to a base outside this package: it moves when the standard library
            # moves, which is not a promise this package made and not a change it can make
            pass
        for field in ("fields", "bases"):
            # order matters for both: fields carry positional construction and unpacking, bases carry
            # the method resolution order, so a reshuffle changes behaviour while keeping every name
            gone = [item for item in old.get(field, []) if item not in new.get(field, [])]
            fresh = [item for item in new.get(field, []) if item not in old.get(field, [])]
            changes += [("breaking", f"{section}.{name}: {field[:-1]} '{item}' removed") for item in gone]
            changes += [("addition", f"{section}.{name}: {field[:-1]} '{item}' added") for item in fresh]
            kept_before = [item for item in old.get(field, []) if item in new.get(field, [])]
            kept_after = [item for item in new.get(field, []) if item in old.get(field, [])]
            if kept_before != kept_after:
                changes.append(("breaking", f"{section}.{name}: {field} reordered, {kept_before} -> {kept_after}"))
    return changes


def _overload_changes(before: list[str], after: list[str]) -> list[tuple[str, str]]:
    """Overloads compared as a sequence, because the first matching one wins.

    Reordering keeps every declaration and still changes which protocol a caller gets, so it is reported
    rather than passing as "the same set".
    """
    changes: list[tuple[str, str]] = []
    changes.extend(("breaking", f"overload gone: {text}") for text in before if text not in after)
    changes.extend(("typing", f"overload added: {text}") for text in after if text not in before)
    kept_before = [text for text in before if text in after]
    kept_after = [text for text in after if text in before]
    if kept_before != kept_after:
        changes.append(("breaking", "overloads reordered, so an overlapping call may resolve elsewhere"))
    return changes


def differences(before: dict, after: dict) -> list[tuple[str, str]]:
    """Every way the surface moved, classified. Empty when the two describe the same package."""
    changes: list[tuple[str, str]] = []
    old_exports, new_exports = set(before["exports"]), set(after["exports"])
    changes.extend(("breaking", f"export '{name}' removed") for name in sorted(old_exports - new_exports))
    changes.extend(("addition", f"export '{name}' added") for name in sorted(new_exports - old_exports))
    for section in ("exported", "builder", "matchers"):
        changes.extend(_section_changes(section, before[section], after[section]))
    old_read, new_read = before["failure_attributes"], after["failure_attributes"]
    changes.extend(
        ("breaking", f"AssertionFailure.{name} no longer readable") for name in sorted(set(old_read) - set(new_read))
    )
    changes.extend(
        ("addition", f"AssertionFailure.{name} now readable") for name in sorted(set(new_read) - set(old_read))
    )
    changes.extend(
        ("breaking", f"AssertionFailure.{name} is now a {new_read[name]}, was a {old_read[name]}")
        for name in sorted(set(old_read) & set(new_read))
        if old_read[name] != new_read[name]
    )
    changes.extend(_overload_changes(before.get("entry_overloads", []), after.get("entry_overloads", [])))
    changes.extend(_section_changes("matcher_protocol", before["matcher_protocol"], after["matcher_protocol"]))
    if before["py_typed"] and not after["py_typed"]:
        changes.append(("breaking", "py.typed is gone, so every consumer silently loses the types"))
    return changes


class TestThePublicSurfaceHasNotMoved:
    def test_the_snapshot_still_describes_the_package(self):
        """The gate itself. A red run here is a decision to make, not a failure to paper over.

        Read the classification below, decide whether the change is allowed to ship in this release,
        then re-record with `ASSERTPY2_UPDATE_API=1 pytest tests/test_api_compatibility.py` and let the
        snapshot diff carry the decision into review.
        """
        current = collect()
        if os.environ.get("ASSERTPY2_UPDATE_API"):
            _write(current)
            pytest.skip("snapshot re-recorded on request")
        changes = differences(_stored(), current)
        breaking = [description for severity, description in changes if severity == "breaking"]
        other = [f"[{severity}] {description}" for severity, description in changes if severity != "breaking"]
        assert_that(breaking).described_as("BREAKING changes to the public surface").is_empty()
        assert_that(other).described_as("surface changed and the snapshot was not re-recorded").is_empty()

    def test_the_snapshot_holds_no_private_names(self):
        # a snapshot that captured privates would turn every internal rename into a red gate, which is
        # the fastest way to teach everyone to re-record without reading
        stored = _stored()
        leaked = [
            f"{section}.{name}"
            for section in ("exported", "builder", "matchers")
            for name in stored[section]
            # one leading underscore is private; `__version__` and its kind are part of the surface
            if name.startswith("_") and not name.startswith("__")
        ]
        assert_that(leaked).described_as("private names in the compatibility snapshot").is_empty()


class TestTheClassificationItself:
    """The gate is only as good as its severities, so they are exercised directly."""

    BASE: ClassVar[dict] = {
        "exports": ["assert_that"],
        "py_typed": True,
        "exported": {
            "assert_that": {"kind": "callable", "parameters": [], "returns": None},
            "AssertionFailure": {
                "kind": "class",
                "parameters": [],
                "returns": None,
                "bases": ["AssertionError"],
                "fields": ["actual", "expected"],
            },
        },
        "builder": {
            "is_equal_to": {
                "kind": "callable",
                "parameters": [
                    {
                        "name": "other",
                        "kind": "POSITIONAL_OR_KEYWORD",
                        "required": True,
                        "default": None,
                        "annotation": None,
                    },
                    {
                        "name": "tolerance",
                        "kind": "POSITIONAL_OR_KEYWORD",
                        "required": False,
                        "default": "0.0",
                        "annotation": None,
                    },
                    {
                        "name": "strict",
                        "kind": "KEYWORD_ONLY",
                        "required": False,
                        "default": "False",
                        "annotation": None,
                    },
                ],
                "returns": "Self",
            }
        },
        "matchers": {},
        "entry_overloads": ["(val: str) -> _StringAssertion"],
        "matcher_protocol": {
            "matches": {"kind": "callable", "parameters": [], "returns": "bool"},
            "describe": {"kind": "callable", "parameters": [], "returns": "str"},
            "describe_mismatch": {"kind": "callable", "parameters": [], "returns": "str"},
        },
        "failure_attributes": {"actual": "instance attribute"},
    }

    def _after(self, **changes):
        surface = copy.deepcopy(self.BASE)
        for path, value in changes.items():
            surface[path] = value
        return surface

    @pytest.mark.parametrize(
        ("label", "mutate", "severity"),
        [
            ("an export disappears", lambda s: s.update(exports=[]), "breaking"),
            ("py.typed disappears", lambda s: s.update(py_typed=False), "breaking"),
            (
                "an existing parameter loses its default",
                lambda s: s["builder"]["is_equal_to"]["parameters"][1].update(required=True, default=None),
                "breaking",
            ),
            (
                "a required parameter is added",
                lambda s: s["builder"]["is_equal_to"]["parameters"].append(
                    {"name": "mode", "kind": "KEYWORD_ONLY", "required": True, "default": None, "annotation": None}
                ),
                "breaking",
            ),
            (
                "a parameter is renamed",
                lambda s: s["builder"]["is_equal_to"]["parameters"][0].update(name="expected"),
                "breaking",
            ),
            (
                "positional parameters swap places",
                lambda s: s["builder"]["is_equal_to"]["parameters"].reverse(),
                "breaking",
            ),
            (
                "a keyword-only parameter becomes positional too",
                lambda s: s["builder"]["is_equal_to"]["parameters"][2].update(kind="POSITIONAL_OR_KEYWORD"),
                "addition",
            ),
            (
                "a positional parameter becomes keyword-only",
                lambda s: s["builder"]["is_equal_to"]["parameters"][0].update(kind="KEYWORD_ONLY"),
                "breaking",
            ),
            (
                "a default value changes",
                lambda s: s["builder"]["is_equal_to"]["parameters"][1].update(default="True"),
                "behaviour",
            ),
            (
                "record fields are reordered",
                lambda s: s["exported"]["AssertionFailure"].update(fields=["expected", "actual"]),
                "breaking",
            ),
            (
                "an assert_that overload disappears",
                lambda s: s.update(entry_overloads=[]),
                "breaking",
            ),
            (
                "a matcher protocol method disappears",
                lambda s: s["matcher_protocol"].pop("describe"),
                "breaking",
            ),
            (
                "a method disappears",
                lambda s: s["builder"].clear(),
                "breaking",
            ),
            (
                "a readable failure attribute disappears",
                lambda s: s.update(failure_attributes={}),
                "breaking",
            ),
            (
                "an optional parameter appears",
                lambda s: s["builder"]["is_equal_to"]["parameters"].append(
                    {"name": "ignore", "kind": "KEYWORD_ONLY", "required": False, "default": "None", "annotation": None}
                ),
                "addition",
            ),
            ("an export appears", lambda s: s.update(exports=["assert_that", "assert_soon"]), "addition"),
            (
                "an annotation appears where there was none",
                lambda s: s["builder"]["is_equal_to"]["parameters"][0].update(annotation="object"),
                "typing",
            ),
            (
                "a return type is narrowed",
                lambda s: s["builder"]["is_equal_to"].update(returns="_StringAssertion"),
                "typing",
            ),
        ],
        ids=lambda value: value if isinstance(value, str) else "",
    )
    def test_each_kind_of_move_is_called_what_it_is(self, label, mutate, severity):
        after = self._after()
        mutate(after)
        found = differences(self.BASE, after)
        assert_that([kind for kind, _ in found]).described_as(label).contains(severity)

    def test_an_unchanged_surface_reports_nothing(self):
        assert_that(differences(self.BASE, self._after())).is_empty()
