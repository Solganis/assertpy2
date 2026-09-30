"""Contract-drift detection for `assert_conforms(..., exact=True)`.

Reports fields a raw payload carries that its pydantic v2 model does **not** declare - the silent API
growth that `model_validate` drops by default.  Duck-typed on ``model_fields`` (no pydantic import),
alias-aware, and walked beside the validated instance, so every nested model is checked where pydantic put one.
"""

from __future__ import annotations

import collections.abc
import datetime
import decimal
import enum
import fractions
import json
import pathlib
import types
import uuid
from functools import reduce
from typing import TYPE_CHECKING, Annotated, Any, Literal, Union, get_args, get_origin

if TYPE_CHECKING:
    from collections.abc import Callable


def _alias_sources(alias: object) -> list[tuple[object, ...]]:
    """The payload paths an alias reads, in the order pydantic tries them (str, ``AliasChoices``, ``AliasPath``)."""
    if isinstance(alias, str):
        return [(alias,)]
    choices = getattr(alias, "choices", None)
    if choices is not None:
        return [source for choice in choices for source in _alias_sources(choice)]
    path = getattr(alias, "path", None)
    return [tuple(path)] if path else []


def _declared_keys(model: Any) -> set[str]:
    """Field names plus the top-level key of every alias, so an aliased payload key is not mistaken for drift."""
    keys: set[str] = set()
    for name, info in model.model_fields.items():
        keys.add(name)
        for alias in (getattr(info, "alias", None), getattr(info, "validation_alias", None)):
            if alias is not None:
                keys.update(source[0] for source in _alias_sources(alias) if isinstance(source[0], str))
    return keys


def _field_sources(name: str, info: Any, config: Any) -> tuple[tuple[object, ...], ...]:
    """Where pydantic reads field *name*, in the order it looks: its alias sources, then the name if allowed."""
    validation_alias = getattr(info, "validation_alias", None)
    alias = validation_alias if validation_alias is not None else getattr(info, "alias", None)
    if alias is None:
        return ((name,),)
    sources = _alias_sources(alias) if config.get("validate_by_alias") is not False else []
    by_name = config.get("validate_by_name")
    if by_name if by_name is not None else config.get("populate_by_name"):
        sources.append((name,))
    return tuple(sources)


_KEYLESS = (
    int,
    float,
    complex,
    str,
    bytes,
    bytearray,
    type(None),
    decimal.Decimal,
    fractions.Fraction,
    datetime.date,
    datetime.time,
    datetime.timedelta,
    uuid.UUID,
    enum.Enum,
    pathlib.PurePath,
)
_PLAIN_ORIGINS = {
    list,
    tuple,
    set,
    frozenset,
    dict,
    collections.abc.Sequence,
    collections.abc.MutableSequence,
    collections.abc.Set,
    collections.abc.MutableSet,
    collections.abc.Mapping,
    collections.abc.MutableMapping,
    collections.abc.Iterable,
    collections.abc.Iterator,
    collections.abc.Collection,
}


def _may_hold_model(annotation: object, outer: bool = True) -> bool:
    """Whether a model can be built anywhere under a field's *annotation*; only a type made of plain parts says no.

    ``Any`` says yes at the top of the field, where only a validator puts a model and the payload's own object kept
    there costs one identity check, and no inside a container, where passing each kept item costs what skipping saves.
    """
    if annotation is Any or annotation is object:
        return outer
    if annotation in (list, tuple, set, frozenset, dict):
        return False
    origin = get_origin(annotation)
    if origin is Literal:
        return False
    if origin is Annotated:
        return _may_hold_model(get_args(annotation)[0], outer)
    if origin is Union or origin is types.UnionType:
        return any(_may_hold_model(arg, outer) for arg in get_args(annotation))
    if origin in _PLAIN_ORIGINS:
        return any(_may_hold_model(arg, outer=False) for arg in get_args(annotation) if arg is not Ellipsis)
    return origin is not None or not isinstance(annotation, type) or not issubclass(annotation, _KEYLESS)


_FieldReads = tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]

_READS: dict[type, tuple[object, frozenset[str], _FieldReads]] = {}
"""Per model class, with the validator they were read beside: the keys it declares and where each field is read.

Worked out per level of every payload, it was most of the walk: a list of 1000 nested models asked for it 1000 times.
A field whose type cannot hold a model is left out: a 300 by 300 grid of floats cost 35 ms to walk and holds nothing.
A rebuild replaces the validator, and with it what the class reads, so an entry answers only for the validator it
was made with.  At most 256 classes are kept, so models made on the fly cannot grow it without bound."""


def _reads_of(model: Any) -> tuple[frozenset[str], _FieldReads]:
    validator = getattr(model, "__pydantic_validator__", None)
    known = _READS.get(model)
    if known is None or known[0] is not validator:
        config = getattr(model, "model_config", {})
        fields = tuple(
            (name, _field_sources(name, info, config))
            for name, info in model.model_fields.items()
            if _may_hold_model(getattr(info, "annotation", None))
        )
        known = (validator, frozenset(_declared_keys(model)), fields)
        if model in _READS or len(_READS) < 256:
            _READS[model] = known
    return known[1], known[2]


def _followed(payload: object, path: tuple[object, ...]) -> tuple[bool, object]:
    """What *path* reaches in *payload*, key by key and index by index, and whether it reached anything."""
    current: Any = payload
    for step in path:
        if isinstance(current, dict):
            if step not in current:
                return False, None
            current = current[step]
        elif not isinstance(current, str):
            # read as pydantic reads it, through whatever `__getitem__` the object has
            try:
                current = current[step]
            except (LookupError, TypeError):
                return False, None
        else:
            return False, None
    return True, current


def _raw_field(payload: collections.abc.Mapping, sources: tuple[tuple[object, ...], ...]) -> tuple[bool, object]:
    """The part of *payload* pydantic validated a field from: the first of its sources that is there."""
    for source in sources:
        found, value = _followed(payload, source)
        if found:
            return True, value
    return False, None


def _is_model(value: object) -> bool:
    return not isinstance(value, type) and hasattr(type(value), "model_fields")


_CONTAINERS = (dict, list, tuple, set, frozenset)


class UncheckableDriftError(Exception):
    """A part of the payload no reading pairs with the model it became, so whether it drifted cannot be told."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path or 'the payload'}: {reason}")
        self.path = path
        self.reason = reason


def contract_drift(
    payload: object, instance: Any, path: str = "", _seen: frozenset[tuple[int, int]] = frozenset()
) -> list[str]:
    """Paths of fields ``payload`` carries that the model ``instance`` was validated into does not declare.

    Walked beside the instance rather than read off the annotations: which member of a union, which element type
    of a tuple and which dict value a part of the payload became is what pydantic decided, and the instance holds
    the answer.  A model whose config opts into extras (``extra="allow"``) keeps them intentionally, so its own
    level is skipped.

    Raises:
        UncheckableDriftError: where a part of the payload that could hide an undeclared key (a dict inside it, or
            inside the JSON text it is) cannot be paired with a model built from it: a set, a resized list or an
            object wrapped into either whose built items are not all one model class, or whose raw item that class
            refuses on its own, dict keys coercion merged, a part of another shape than what was built, an iterable
            validation read up or left lazy.  The payload is read as validation left it: a validator renaming keys,
            changing the payload in place, or reordering or rewriting a container's items without changing its size
            is not seen, and the walk reads those items by position.
    """
    model = type(instance)
    if getattr(model, "__pydantic_root_model__", False):
        return _value_drift(payload, instance.root, path, _seen) if _reads_of(model)[1] else []
    if not isinstance(payload, (dict, collections.abc.Mapping)):
        _refuse_if_key_hides(
            payload, instance, path, f"the payload holds a {type(payload).__name__} where a model was built"
        )
        return []
    seen = _seen | {(id(payload), id(instance))}
    declared, fields = _reads_of(model)
    prefix = f"{path}." if path else ""
    drift: list[str] = []
    if getattr(model, "model_config", {}).get("extra") != "allow":
        drift += [f"{prefix}{key}" for key in payload if key not in declared]
    else:
        # extras typed through `__pydantic_extra__` are built too; untyped ones are the payload's own objects
        for key, built in (getattr(instance, "__pydantic_extra__", None) or {}).items():
            if key in payload:
                drift += _value_drift(payload[key], built, f"{prefix}{key}", seen)
    for name, sources in fields:
        found, raw = _raw_field(payload, sources)
        if not found:
            continue
        value = getattr(instance, name, None)
        # a scalar built from a scalar holds nothing to pair
        if (value is None or isinstance(value, (str, int, float, bytes))) and not isinstance(raw, _CONTAINERS):
            continue
        drift += _value_drift(raw, value, f"{prefix}{name}", seen)
    return drift


def exactness_failure(pairs: Any, *, carrier: str) -> str | None:
    """What an exact check of ``(payload, instance, path)`` pairs found, in the words a failure continues with.

    The undeclared fields, after *carrier*, or the first part that cannot be checked; ``None`` when neither.
    """
    drift: list[str] = []
    try:
        for payload, instance, path in pairs:
            drift += contract_drift(payload, instance, path)
    except UncheckableDriftError as refusal:
        return f"<{refusal.path or 'the payload'}> cannot be checked: {refusal.reason}"
    except RecursionError:
        return "<the payload> cannot be checked: it nests deeper than the walk can follow"
    if not drift:
        return None
    return f"{carrier}{len(drift)} undeclared field(s) the model does not declare: {sorted(drift)}"


def _value_drift(raw: object, value: object, path: str, seen: frozenset[tuple[int, int]]) -> list[str]:
    """Drift under one validated value: a model's own keys, and every element or dict value that became a model."""
    # the payload's own object kept as it was, or a scalar: nothing was built from it
    if raw is value or value is None or isinstance(value, (str, int, float, bytes)):
        return []
    if isinstance(raw, (str, bytes, bytearray)):
        raw = _decoded_container(raw)
    # a pair already on the path is a cycle, the payload's own or one a validator built by assigning a model to itself
    pair = (id(raw), id(value))
    if pair in seen:
        return []
    seen = seen | {pair}
    if _is_model(value):
        return contract_drift(raw, value, path, seen)
    return _container_drift(raw, value, path, seen)


def _container_drift(raw: object, value: object, path: str, seen: frozenset[tuple[int, int]]) -> list[str]:
    """Drift under a built container, paired with the raw part it came from as its kind allows."""
    if isinstance(value, (list, tuple)):
        return _sequence_drift(raw, value, path, seen)
    if isinstance(value, dict):
        return _mapping_drift(raw, value, path, seen)
    if isinstance(value, (set, frozenset)):
        return _set_drift(raw, value, path, seen)
    if isinstance(value, collections.abc.Mapping):
        return _mapping_drift(raw, dict(value), path, seen)
    if isinstance(value, collections.abc.Iterator):
        if _holds(raw, _is_mapping, read_text=True):
            raise UncheckableDriftError(path, "validation is lazy here and builds the models only as the value is read")
        return []
    # a sequence validation kept as the payload's own kind, a deque under `Sequence[A]`
    items = _items_of(value)
    return [] if items is None else _sequence_drift(raw, items, path, seen)


def _sequence_drift(raw: object, value: list | tuple, path: str, seen: frozenset[tuple[int, int]]) -> list[str]:
    """Paired by index, a collection pydantic also takes for a sequence (a deque, a set, a dict's values) in the
    order it iterates, which is the order validation read it in."""
    if not isinstance(raw, (list, tuple)):
        items = _items_of(raw)
        if items is None:
            reason = f"the payload holds a {type(raw).__name__} where a sequence was built"
            return _wrapped(raw, value, path, seen, reason)
        raw = items
    if len(raw) != len(value):
        reason = f"validation changed its length, {len(raw)} items became {len(value)}"
        return _unpaired(raw, [(f"{path}[{i}]", part) for i, part in enumerate(raw)], value, path, seen, reason)
    return [
        entry
        for index, (part, element) in enumerate(zip(raw, value, strict=True))
        for entry in _value_drift(part, element, f"{path}[{index}]", seen)
    ]


def _mapping_drift(raw: object, value: dict, path: str, seen: frozenset[tuple[int, int]]) -> list[str]:
    """Paired by key where validation kept the keys (a `TypedDict` reorders them), else by order, which dict validation
    keeps while it coerces them; a key built into something other than text or a number is walked beside its raw key."""
    if not isinstance(raw, (dict, collections.abc.Mapping)):
        _refuse_if_key_hides(raw, value, path, f"the payload holds a {type(raw).__name__} where a mapping was built")
        return []
    if len(raw) != len(value):
        # an overwritten value may have become another member of a union than the one that survived
        _refuse_if_key_hides(raw, value, path, f"validation changed its size, {len(raw)} keys became {len(value)}")
        return []
    if raw.keys() == value.keys():
        return [
            entry
            for key, part in raw.items()
            for entry in _value_drift(part, value[key], f"{path}.{key}" if path else str(key), seen)
        ]
    drift: list[str] = []
    for (key, part), (built, element) in zip(raw.items(), value.items(), strict=True):
        if not isinstance(built, (str, int)):
            drift += _value_drift(key, built, path, seen)
        drift += _value_drift(part, element, f"{path}.{key}" if path else str(key), seen)
    return drift


def _set_drift(raw: object, value: set | frozenset, path: str, seen: frozenset[tuple[int, int]]) -> list[str]:
    items = raw if isinstance(raw, (list, tuple)) else _items_of(raw)
    if items is None:
        reason = f"the payload holds a {type(raw).__name__} where a set was built"
        return _wrapped(raw, value, path, seen, reason)
    reason = "a set keeps no order to pair its items with the models they became"
    parts = [(f"{path}[{i}]", part) for i, part in enumerate(items)]
    return _unpaired(raw, parts, value, path, seen, reason, merged=True)


def _wrapped(raw: object, value: object, path: str, seen: frozenset[tuple[int, int]], reason: str) -> list[str]:
    """Drift under a mapping a validator turned into a sequence or a set, a single object sent where many may be.

    Only a mapping that became one item is that item; one that became several was expanded in a way no reading
    pairs.
    """
    if isinstance(raw, (dict, collections.abc.Mapping)) and len(_items_of(value) or ()) == 1:
        return _unpaired(raw, [(path, raw)], value, path, seen, reason)
    _refuse_if_key_hides(raw, value, path, reason)
    return []


def _unpaired(
    raw: object,
    parts: list[tuple[str, object]],
    value: object,
    path: str,
    seen: frozenset[tuple[int, int]],
    reason: str,
    *,
    merged: bool = False,
) -> list[str]:
    """Drift under a container whose raw items no reading pairs one by one with the items validation built.

    Where every built item is an instance of one model class, each raw item became one too, so each raw item that
    could hide a key is validated again on its own by that class, JSON text in JSON mode as `Json[...]` read it, and
    walked beside what it becomes.  Anything else refuses with *reason*: items of mixed classes, an item the class
    refuses on its own, which needed its parent, and, where equal items *merged*, a class whose own `__eq__` could
    have merged an item of another class into it.
    """
    if not _holds(value, _builds_model) or not _holds(raw, _is_mapping, read_text=True):
        return []
    model = _sole_model_class(value)
    validate = getattr(model, "model_validate", None)
    validate_json = getattr(model, "model_validate_json", None)
    if validate is None or validate_json is None or (merged and not _equal_only_within_its_class(model)):
        raise UncheckableDriftError(path, reason)
    drift: list[str] = []
    for label, item in parts:
        part = _decoded_container(item) if isinstance(item, (str, bytes, bytearray)) else item
        if _holds(part, _is_mapping, read_text=True):
            try:
                built = validate(part) if part is item else validate_json(item)
            except ValueError:
                raise UncheckableDriftError(path, reason) from None
            drift += _value_drift(part, built, label, seen)
    return drift


def _equal_only_within_its_class(model: type | None) -> bool:
    """Whether equal instances of *model* share its class: its `__eq__` is pydantic's own, which compares classes.

    A parametrized generic model does not: pydantic compares its origin, which every specialization shares.
    """
    if (getattr(model, "__pydantic_generic_metadata__", None) or {}).get("origin") is not None:
        return False
    owner = next((klass for klass in getattr(model, "__mro__", ()) if "__eq__" in vars(klass)), object)
    return owner.__module__.startswith("pydantic.")


def _sole_model_class(value: object) -> type | None:
    """The one model class every item of a built container is an instance of, or ``None``."""
    items = _items_of(value) or []
    kinds = {type(item) for item in items}
    return kinds.pop() if len(kinds) == 1 and _is_model(items[0]) else None


def _decoded_container(text: str | bytes | bytearray) -> object:
    """What JSON *text* decodes to, decoded again while that is text, when it ends in a mapping or a list; else *text*.

    A model read from JSON text (`Json[...]`) is walked beside what the text holds.  Text that is not JSON, or nests
    deeper than the decoder goes, is left as it is.
    """
    try:
        current = json.loads(text)
        while isinstance(current, str):
            current = json.loads(current)
    except (ValueError, RecursionError):
        return text
    return current if isinstance(current, (dict, list)) else text


def _refuse_if_key_hides(raw: object, value: object, path: str, reason: str) -> None:
    """Refuse a part no reading pairs with what it became, when a model was built there and a key could hide in it.

    A number, a model given as is, an object read by attributes and text that is not JSON hold no key to drift.
    """
    if _holds(value, _builds_model) and _holds(raw, _is_mapping, read_text=True):
        raise UncheckableDriftError(path, reason)


def _holds(value: object, found: Callable[[object], bool], *, read_text: bool = False) -> bool:
    """Whether *value*, or anything inside its containers (a dict's keys too), is *found*.

    With *read_text*, text counts as the JSON it decodes to, decoded again while that is text, and two things count
    as found, since what they hold cannot be told: text nesting deeper than the decoder goes, and an iterable that is
    no collection, which validation may have read up or may answer differently when read again.  Every part stays
    referenced until the search ends, so the id of one already seen is never taken by a part decoded later.
    """
    pending, visited = [value], {id(value): value}
    while pending:
        current = pending.pop()
        if read_text and isinstance(current, (str, bytes, bytearray)):
            try:
                pending.append(json.loads(current))
            except ValueError:
                pass
            except RecursionError:
                return True
            continue
        elif read_text and _read_once(current):
            return True
        if found(current):
            return True
        for part in _parts(current):
            if id(part) not in visited:
                visited[id(part)] = part
                pending.append(part)
    return False


def _is_mapping(value: object) -> bool:
    return isinstance(value, (dict, collections.abc.Mapping))


def _builds_model(value: object) -> bool:
    """A model, or an iterator validation left lazy, which builds its models only as it is read."""
    return _is_model(value) or isinstance(value, collections.abc.Iterator)


def _read_once(value: object) -> bool:
    """An iterable that is no collection and no model given as is: what it held cannot be read again."""
    return (
        isinstance(value, collections.abc.Iterable)
        and not isinstance(value, collections.abc.Collection)
        and not _is_model(value)
    )


def _items_of(value: object) -> list[Any] | None:
    """The items of a container read again as often as asked, not text and not a mapping; ``None`` for the rest."""
    if isinstance(value, collections.abc.Collection) and not isinstance(
        value, (str, bytes, bytearray, collections.abc.Mapping)
    ):
        return list(value)
    return None


def _parts(value: object) -> Any:
    """What a container holds, a mapping's keys too, or nothing for anything else."""
    if isinstance(value, (list, tuple, set, frozenset)):
        return value
    if isinstance(value, (dict, collections.abc.Mapping)):
        return [*value, *value.values()]
    return _items_of(value) or ()


def shape(value: object, _seen: frozenset[int] = frozenset()) -> object:
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
    if isinstance(value, (dict, list, tuple)):
        if id(value) in _seen:
            # a self-referential graph would otherwise recurse until the interpreter gives up
            return "<circular ref>"
        nested = _seen | {id(value)}
        if isinstance(value, dict):
            return {key: shape(item, nested) for key, item in value.items()}
        element_shapes = [shape(item, nested) for item in value]
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
