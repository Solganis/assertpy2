"""The compatibility gate: what changed in the public surface, and whether it may change that way.

A caller breaks on things no other guard here watches. A parameter renamed, a default dropped, a
keyword argument becoming positional, an exported name quietly gone: each of those passes the type
checker, passes the suite, and fails in someone else's test run after an upgrade.

So the surface is snapshotted and compared. The comparison is not "did anything move" but "how did it
move", because the four kinds of movement carry different obligations:

* **breaking** - a caller that worked stops working. Needs a major, or must not ship.
* **addition** - new names, new optional parameters. A minor.
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
    if before.get("returns") != after.get("returns"):
        changes.append(("typing", f"{path}: returns {after.get('returns')} instead of {before.get('returns')}"))
    if before.get("kind") != after.get("kind"):
        changes.append(("breaking", f"{path}: is a {after.get('kind')} instead of a {before.get('kind')}"))
    return changes


def _need(parameter: dict) -> str:
    return "required" if parameter["required"] else "optional"


def _parameter_changes(path: str, name: str, before: dict, after: dict) -> list[tuple[str, str]]:
    """How one parameter moved, each rule its own line rather than a nest of branches."""
    changes = []
    if after["kind"] != before["kind"]:
        changes.append(("breaking", f"{path}: parameter '{name}' is now {after['kind']}, was {before['kind']}"))
    if after["required"] and not before["required"]:
        changes.append(("breaking", f"{path}: parameter '{name}' lost its default"))
    if not after["required"] and before["required"]:
        changes.append(("addition", f"{path}: parameter '{name}' gained a default"))
    if after["annotation"] != before["annotation"]:
        changes.append(("typing", f"{path}: parameter '{name}' is now typed {after['annotation']}"))
    return changes


def _section_changes(section: str, before: dict, after: dict) -> list[tuple[str, str]]:
    changes: list[tuple[str, str]] = []
    changes.extend(("breaking", f"{section}.{name} removed") for name in sorted(set(before) - set(after)))
    changes.extend(("addition", f"{section}.{name} added") for name in sorted(set(after) - set(before)))
    for name in sorted(set(before) & set(after)):
        old, new = before[name], after[name]
        changes.extend(_callable_changes(f"{section}.{name}", old, new))
        for field in ("fields", "bases"):
            gone = [item for item in old.get(field, []) if item not in new.get(field, [])]
            fresh = [item for item in new.get(field, []) if item not in old.get(field, [])]
            changes += [("breaking", f"{section}.{name}: {field[:-1]} '{item}' removed") for item in gone]
            changes += [("addition", f"{section}.{name}: {field[:-1]} '{item}' added") for item in fresh]
    return changes


def differences(before: dict, after: dict) -> list[tuple[str, str]]:
    """Every way the surface moved, classified. Empty when the two describe the same package."""
    changes: list[tuple[str, str]] = []
    old_exports, new_exports = set(before["exports"]), set(after["exports"])
    changes.extend(("breaking", f"export '{name}' removed") for name in sorted(old_exports - new_exports))
    changes.extend(("addition", f"export '{name}' added") for name in sorted(new_exports - old_exports))
    for section in ("exported", "builder", "matchers"):
        changes.extend(_section_changes(section, before[section], after[section]))
    old_read, new_read = set(before["failure_attributes"]), set(after["failure_attributes"])
    changes.extend(("breaking", f"AssertionFailure.{name} no longer readable") for name in sorted(old_read - new_read))
    changes.extend(("addition", f"AssertionFailure.{name} now readable") for name in sorted(new_read - old_read))
    lost = set(before["matcher_protocol"]) - set(after["matcher_protocol"])
    changes.extend(("breaking", f"matcher protocol lost '{name}'") for name in sorted(lost))
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
            if name.startswith("_")
        ]
        assert_that(leaked).described_as("private names in the compatibility snapshot").is_empty()


class TestTheClassificationItself:
    """The gate is only as good as its severities, so they are exercised directly."""

    BASE: ClassVar[dict] = {
        "exports": ["assert_that"],
        "py_typed": True,
        "exported": {"assert_that": {"kind": "callable", "parameters": [], "returns": None}},
        "builder": {
            "is_equal_to": {
                "kind": "callable",
                "parameters": [
                    {"name": "other", "kind": "POSITIONAL_OR_KEYWORD", "required": True, "annotation": None}
                ],
                "returns": "Self",
            }
        },
        "matchers": {},
        "matcher_protocol": ["matches", "describe", "describe_mismatch"],
        "failure_attributes": ["actual"],
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
                "a parameter loses its default",
                lambda s: s["builder"]["is_equal_to"]["parameters"].append(
                    {"name": "tolerance", "kind": "KEYWORD_ONLY", "required": True, "annotation": None}
                ),
                "breaking",
            ),
            (
                "a method disappears",
                lambda s: s["builder"].clear(),
                "breaking",
            ),
            (
                "a readable failure attribute disappears",
                lambda s: s.update(failure_attributes=[]),
                "breaking",
            ),
            (
                "an optional parameter appears",
                lambda s: s["builder"]["is_equal_to"]["parameters"].append(
                    {"name": "tolerance", "kind": "KEYWORD_ONLY", "required": False, "annotation": None}
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
