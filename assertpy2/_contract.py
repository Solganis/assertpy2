"""Contract-drift detection for `assert_conforms(..., exact=True)`.

Reports fields a raw payload carries that its pydantic v2 model does **not** declare - the silent API
growth that `model_validate` drops by default.  Duck-typed on ``model_fields`` (no pydantic import),
alias-aware, and recursive into nested sub-models and ``list``/``tuple`` of sub-models.
"""

from __future__ import annotations

import types
import typing
from functools import reduce
from typing import Any


def _submodel(annotation: object) -> type | None:
    """The nested model class for an annotation, peeling ``Optional`` / ``list`` / ``tuple``; else ``None``."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Union or origin is types.UnionType:
        non_none = [arg for arg in args if arg is not type(None)]
        return _submodel(non_none[0]) if len(non_none) == 1 else None
    if origin in (list, tuple, set, frozenset) and args:
        return _submodel(args[0])
    if isinstance(annotation, type) and hasattr(annotation, "model_fields"):
        return annotation
    return None


def _declared_keys(model: Any) -> set[str]:
    """Field names plus their string aliases, so an aliased payload key is not mistaken for drift."""
    keys: set[str] = set()
    for name, info in model.model_fields.items():
        keys.add(name)
        alias = getattr(info, "alias", None)
        if isinstance(alias, str):
            keys.add(alias)
    return keys


def contract_drift(payload: object, model: Any, path: str = "") -> list[str]:
    """Paths of fields ``payload`` carries that ``model`` does not declare, recursively.

    A model whose config opts into extras (``extra="allow"``) keeps them intentionally, so its level is
    skipped.  Non-dict payloads (already validated) contribute nothing.
    """
    if not isinstance(payload, dict):
        return []
    drift: list[str] = []
    if getattr(model, "model_config", {}).get("extra") != "allow":
        declared = _declared_keys(model)
        drift += [f"{path}{key}" for key in payload if key not in declared]
    for name, info in model.model_fields.items():
        submodel = _submodel(info.annotation)
        if submodel is None:
            continue
        alias = getattr(info, "alias", None)
        value = payload.get(name)
        if value is None and isinstance(alias, str):
            value = payload.get(alias)
        if isinstance(value, (list, tuple)):
            for index, element in enumerate(value):
                drift += contract_drift(element, submodel, f"{path}{name}[{index}].")
        elif isinstance(value, dict):
            drift += contract_drift(value, submodel, f"{path}{name}.")
    return drift


def shape(value: object) -> object:
    """The structural shape of a value: paths and type *categories*, never values.

    Numbers collapse to one category (so ``5`` and ``5.0`` do not read as drift) and ``None`` becomes
    ``"null"`` (a nullable wildcard).  A list becomes a single merged element shape.  This is what a
    contract snapshot stores, so later runs pass when values change but fail on structural drift.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "str"
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        element_shapes = [shape(item) for item in value]
        return [reduce(_merge, element_shapes)] if element_shapes else []
    return type(value).__name__


def _merge(left: Any, right: Any) -> Any:
    """Merge two element shapes into one representative shape (``null`` yields to a concrete type)."""
    if left == right:
        return left
    if left == "null":
        return right
    if right == "null":
        return left
    if isinstance(left, dict) and isinstance(right, dict):
        return {key: _merge(left.get(key, "null"), right.get(key, "null")) for key in set(left) | set(right)}
    if isinstance(left, list) and isinstance(right, list):
        if not left:
            return right
        if not right:
            return left
        return [_merge(left[0], right[0])]
    return "mixed"


def _shape_name(part: object) -> str:
    if isinstance(part, str):
        return part
    return "object" if isinstance(part, dict) else "list"


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def shape_diff(old: Any, new: Any, path: str = "") -> list[tuple[str, str, str]]:
    """Structural drift between two shapes: ``(kind, path, detail)`` for added / removed / retyped leaves.

    A ``null`` on either side is a nullable wildcard and never counts as drift.
    """
    if old == new or old == "null" or new == "null":
        return []
    if isinstance(old, dict) and isinstance(new, dict):
        drift: list[tuple[str, str, str]] = [("added", _join(path, key), "") for key in new if key not in old]
        for key in old:
            child = _join(path, key)
            if key not in new:
                drift.append(("removed", child, ""))
            else:
                drift += shape_diff(old[key], new[key], child)
        return drift
    if isinstance(old, list) and isinstance(new, list):
        if not old or not new:
            return []
        return shape_diff(old[0], new[0], f"{path}[*]")
    return [("retyped", path, f"{_shape_name(old)} -> {_shape_name(new)}")]
