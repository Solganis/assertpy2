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
import sys
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


def _alternatives(annotation: object) -> tuple[object, ...]:
    """The members of a union, `Annotated` and nested unions opened, or the annotation alone."""
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    if get_origin(annotation) in (Union, types.UnionType):
        return tuple(member for argument in get_args(annotation) for member in _alternatives(argument))
    return (annotation,)


_ITEM_ORIGINS = frozenset(
    {
        list,
        tuple,
        set,
        frozenset,
        collections.deque,
        collections.abc.Sequence,
        collections.abc.MutableSequence,
        collections.abc.Set,
        collections.abc.MutableSet,
        collections.abc.Collection,
        collections.abc.Iterable,
    }
)


_MAPPING_ORIGINS = frozenset({dict, collections.abc.Mapping, collections.abc.MutableMapping})

_Declared = tuple[object, object]
"""A declared type and the model class whose field declared it, whose config its validation ran in."""

_DECLARED: dict[tuple[int, object], tuple[_Declared, Any]] = {}
"""What a declaration says a container built from it holds, per declaration and kind of container: worked out once,
since a list of 1000 orders asks it for each order.  At most 1024 entries."""


def _declared_container(declared: _Declared | None) -> tuple[tuple[_Declared, ...] | None, _Declared | None] | None:
    """What *declared* says the items of a container built from it are declared as: one declaration per position of a
    fixed tuple, or one for every item; ``None`` where it does not say.

    Only a declaration that leaves validation no choice says (`_sole_member`): which member of a union validation took
    depends on what the field's own validators made of the payload, and the kind of container they left does not tell.
    """
    if declared is None:
        return None
    key = (id(declared), "items")
    known = _DECLARED.get(key)
    if known is not None and known[0] is declared:
        return known[1]
    annotation, owner = declared
    container = _sole_member(annotation)
    items = None
    if get_origin(container) in _ITEM_ORIGINS and get_args(container):
        arguments = get_args(container)
        if _is_fixed_tuple(container):
            items = (tuple((argument, owner) for argument in arguments), None)
        else:
            items = (None, (arguments[0], owner))
    if len(_DECLARED) < 1024:
        _DECLARED[key] = (declared, items)
    return items


def _declared_mapping_value(declared: _Declared | None) -> _Declared | None:
    """The declaration of the values of the mapping *declared* is, where it leaves validation no choice, or ``None``."""
    if declared is None:
        return None
    key = (id(declared), "values")
    known = _DECLARED.get(key)
    if known is not None and known[0] is declared:
        return known[1]
    annotation, owner = declared
    mapping = _sole_member(annotation)
    value = (
        (get_args(mapping)[1], owner)
        if get_origin(mapping) in _MAPPING_ORIGINS and len(get_args(mapping)) == 2
        else None
    )
    if len(_DECLARED) < 1024:
        _DECLARED[key] = (declared, value)
    return value


def _sole_member(annotation: object) -> object:
    """*annotation* without `Annotated` and without ``None`` beside it; ``None`` where a union leaves a choice."""
    members = [member for member in _alternatives(annotation) if member is not type(None)]
    return members[0] if len(members) == 1 else None


def _chooses(annotation: object) -> bool:
    """Whether validation chose anywhere in *annotation* above the models it names: between two or more members of a
    union besides ``None``, or inside a named type alias, which is not opened."""
    members = [member for member in _alternatives(annotation) if member is not type(None)]
    if len(members) > 1 or any(hasattr(member, "__value__") for member in members):
        return True
    return any(_chooses(argument) for member in members for argument in get_args(member) if argument is not Ellipsis)


def _is_fixed_tuple(container: object) -> bool:
    arguments = get_args(container)
    return get_origin(container) is tuple and not (len(arguments) == 2 and arguments[1] is Ellipsis)


def _item_declarations(declared: _Declared | None, count: int) -> list[_Declared | None]:
    """The declaration of each of *count* items of a container built from *declared*, by position where a fixed tuple
    declares one."""
    items = _declared_container(declared)
    if items is None:
        return [None] * count
    positional, common = items
    if positional is None:
        return [common] * count
    return [positional[index] if index < len(positional) else None for index in range(count)]


_ADAPTERS: dict[int, tuple[_Declared, Any]] = {}
"""A pydantic `TypeAdapter` per declaration, or ``None`` where none can be built: building one costs a schema.  At
most 256 entries, each holding its declaration so the id stays its own."""


def _adapter(declared: _Declared) -> Any:
    """A `TypeAdapter` for a declared type, in the config of the model that declared it, from the pydantic the models
    came from; ``None`` where there is none."""
    known = _ADAPTERS.get(id(declared))
    if known is not None and known[0] is declared:
        return known[1]
    annotation, owner = declared
    adapter_class = getattr(sys.modules.get("pydantic"), "TypeAdapter", None)
    adapter = None
    if adapter_class is not None:
        # a schema pydantic refuses: TypeError in 2.0, RuntimeError in 2.13, NameError for a forward reference
        try:
            adapter = adapter_class(annotation, config=getattr(owner, "model_config", None) or None)
        except (TypeError, RuntimeError, NameError):
            adapter = None
    if len(_ADAPTERS) < 256:
        _ADAPTERS[id(declared)] = (declared, adapter)
    return adapter


_FieldReads = tuple[tuple[str, tuple[tuple[object, ...], ...], _Declared], ...]

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
            (name, _field_sources(name, info, config), (getattr(info, "annotation", None), model))
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

_REPLAYED = (0, -1)
"""In the pairs a walk has seen, where no pair of ids can be: the walk is under a replay (`_replayed`), which reads no
field where validation chose, since the validators it skipped could have steered the choice."""


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
    declared, fields = _reads_of(model)
    if _REPLAYED in _seen:
        fields = tuple(field for field in fields if not _chooses(field[2][0]))
    if getattr(model, "__pydantic_root_model__", False):
        return _value_drift(payload, instance.root, path, _seen, fields[0][2]) if fields else []
    if not isinstance(payload, (dict, collections.abc.Mapping)):
        _refuse_if_key_hides(
            payload, instance, path, f"the payload holds a {type(payload).__name__} where a model was built"
        )
        return []
    seen = _seen | {(id(payload), id(instance))}
    prefix = f"{path}." if path else ""
    drift: list[str] = []
    if getattr(model, "model_config", {}).get("extra") != "allow":
        drift += [f"{prefix}{key}" for key in payload if key not in declared]
    else:
        # extras typed through `__pydantic_extra__` are built too; untyped ones are the payload's own objects
        for key, built in (getattr(instance, "__pydantic_extra__", None) or {}).items():
            if key in payload:
                drift += _value_drift(payload[key], built, f"{prefix}{key}", seen)
    for name, sources, annotated in fields:
        found, raw = _raw_field(payload, sources)
        if not found:
            continue
        value = getattr(instance, name, None)
        # a scalar built from a scalar holds nothing to pair
        if (value is None or isinstance(value, (str, int, float, bytes))) and not isinstance(raw, _CONTAINERS):
            continue
        drift += _value_drift(raw, value, f"{prefix}{name}", seen, annotated)
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


def _value_drift(
    raw: object, value: object, path: str, seen: frozenset[tuple[int, int]], declared: _Declared | None = None
) -> list[str]:
    """Drift under one validated value: a model's own keys, and every element or dict value that became a model.

    *declared* is the type the value was declared as and the model that declared it, where the walk knows them: what
    a model field or a root declares, and from it the item type of each container below.
    """
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
    return _container_drift(raw, value, path, seen, declared)


def _container_drift(
    raw: object, value: object, path: str, seen: frozenset[tuple[int, int]], declared: _Declared | None
) -> list[str]:
    """Drift under a built container, paired with the raw part it came from as its kind allows."""
    if isinstance(value, (list, tuple)):
        return _sequence_drift(raw, value, path, seen, declared)
    if isinstance(value, dict):
        return _mapping_drift(raw, value, path, seen, declared)
    if isinstance(value, (set, frozenset)):
        return _set_drift(raw, value, path, seen, declared)
    if isinstance(value, collections.abc.Mapping):
        return _mapping_drift(raw, dict(value), path, seen, declared)
    if isinstance(value, collections.abc.Iterator):
        if _holds(raw, _is_mapping, read_text=True):
            raise UncheckableDriftError(path, "validation is lazy here and builds the models only as the value is read")
        return []
    # a sequence validation kept as the payload's own kind, a deque under `Sequence[A]`
    items = _items_of(value)
    return [] if items is None else _sequence_drift(raw, items, path, seen, declared)


def _sequence_drift(
    raw: object,
    value: list | tuple,
    path: str,
    seen: frozenset[tuple[int, int]],
    declared: _Declared | None = None,
) -> list[str]:
    """Paired by index, a collection pydantic also takes for a sequence (a deque, a set, a dict's values) in the
    order it iterates, which is the order validation read it in."""
    if not isinstance(raw, (list, tuple)):
        items = _items_of(raw)
        if items is None:
            reason = f"the payload holds a {type(raw).__name__} where a sequence was built"
            return _wrapped(raw, value, path, seen, reason, declared)
        raw = items
    if len(raw) != len(value):
        reason = f"validation changed its length, {len(raw)} items became {len(value)}"
        parts = [(f"{path}[{i}]", part) for i, part in enumerate(raw)]
        return _unpaired(raw, parts, value, path, seen, reason, declared=declared)
    items = _declared_container(declared)
    if items is None or items[0] is None:
        common = None if items is None else items[1]
        return [
            entry
            for index, (part, element) in enumerate(zip(raw, value, strict=True))
            for entry in _value_drift(part, element, f"{path}[{index}]", seen, common)
        ]
    declarations = _item_declarations(declared, len(value))
    return [
        entry
        for index, (part, element, item) in enumerate(zip(raw, value, declarations, strict=True))
        for entry in _value_drift(part, element, f"{path}[{index}]", seen, item)
    ]


def _mapping_drift(
    raw: object, value: dict, path: str, seen: frozenset[tuple[int, int]], declared: _Declared | None = None
) -> list[str]:
    """Paired by key where validation kept the keys (a `TypedDict` reorders them), else by order, which dict validation
    keeps while it coerces them; a key built into something other than text or a number is walked beside its raw key."""
    if not isinstance(raw, (dict, collections.abc.Mapping)):
        _refuse_if_key_hides(raw, value, path, f"the payload holds a {type(raw).__name__} where a mapping was built")
        return []
    if len(raw) != len(value):
        # an overwritten value may have become another member of a union than the one that survived
        _refuse_if_key_hides(raw, value, path, f"validation changed its size, {len(raw)} keys became {len(value)}")
        return []
    item = _declared_mapping_value(declared)
    if raw.keys() == value.keys():
        return [
            entry
            for key, part in raw.items()
            for entry in _value_drift(part, value[key], f"{path}.{key}" if path else str(key), seen, item)
        ]
    drift: list[str] = []
    for (key, part), (built, element) in zip(raw.items(), value.items(), strict=True):
        if not isinstance(built, (str, int)):
            drift += _value_drift(key, built, path, seen)
        drift += _value_drift(part, element, f"{path}.{key}" if path else str(key), seen, item)
    return drift


def _set_drift(
    raw: object, value: set | frozenset, path: str, seen: frozenset[tuple[int, int]], declared: _Declared | None
) -> list[str]:
    items = raw if isinstance(raw, (list, tuple)) else _items_of(raw)
    if items is None:
        reason = f"the payload holds a {type(raw).__name__} where a set was built"
        return _wrapped(raw, value, path, seen, reason, declared)
    reason = "a set keeps no order to pair its items with the models they became"
    parts = [(f"{path}[{i}]", part) for i, part in enumerate(items)]
    return _unpaired(raw, parts, value, path, seen, reason, merged=True, declared=declared)


def _wrapped(
    raw: object,
    value: object,
    path: str,
    seen: frozenset[tuple[int, int]],
    reason: str,
    declared: _Declared | None,
) -> list[str]:
    """Drift under a mapping a validator turned into a sequence or a set, a single object sent where many may be.

    Only a mapping that became one item, or none, is that item; one that became several was expanded in a way no
    reading pairs.
    """
    if isinstance(raw, (dict, collections.abc.Mapping)) and len(_items_of(value) or ()) <= 1:
        return _unpaired(raw, [(path, raw)], value, path, seen, reason, declared=declared)
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
    declared: _Declared | None = None,
) -> list[str]:
    """Drift under a container whose raw items no reading pairs one by one with the items validation built.

    Where every built item is an instance of one model class, each raw item became one too, so each raw item that
    could hide a key is validated again on its own by that class and walked beside what it becomes.  Where validation
    kept no model at all, the raw items are validated again whole by the type the field *declared*, in its model's
    config, and what that builds is walked (`_replayed`).  Anything else refuses with *reason*: items of mixed classes,
    an item that does not validate on its own, which needed its parent, and, where equal items *merged*, a class whose
    own `__eq__` could have merged an item of another class into it.
    """
    if not _holds(raw, _is_mapping, read_text=True):
        return []
    if _holds(value, _builds_model):
        model = _sole_model_class(value)
        if model is None or (merged and not _equal_only_within_its_class(model)):
            raise UncheckableDriftError(path, reason)
        return _revalidated(parts, model, path, seen, reason)
    return [] if declared is None else _replayed(parts, path, seen, reason, declared)


def _replayed(
    parts: list[tuple[str, object]],
    path: str,
    seen: frozenset[tuple[int, int]],
    reason: str,
    declared: _Declared,
) -> list[str]:
    """Drift under raw items validation left without a model: validated again whole as the *declared* type, in Python
    mode as validation read them (`_replay_target`).  All of them are replayed first, so a fixed tuple's positions
    see what validation saw; where pydantic refuses that, only the items that could hide a key.  What that builds is
    paired item by item; a set it builds tells the one class they became.

    The replay skips the field's own validators, so whatever they did to the payload is missing from it.  Where that
    could have steered a choice (`_chooses`), nothing is read below it; where pydantic builds nothing from the items,
    or no sequence of as many, nothing is read at all, since its refusal says nothing about the payload.
    """
    if _chooses(declared[0]):
        return []
    replayed = _replay_target(declared)
    adapter = _adapter(replayed)
    if adapter is None:
        return []
    rebuilt = _replay(adapter, parts)
    if rebuilt is None:
        parts = [(label, part) for label, part in parts if _holds(part, _is_mapping, read_text=True)]
        rebuilt = _replay(adapter, parts)
    seen = seen | {_REPLAYED}
    if isinstance(rebuilt, collections.abc.Set):
        return _unpaired([part for _, part in parts], parts, rebuilt, path, seen, reason, merged=True)
    elements = _items_of(rebuilt)
    if elements is None or len(elements) != len(parts):
        return []
    declarations = _item_declarations(replayed, len(elements))
    return [
        entry
        for (label, part), element, item in zip(parts, elements, declarations, strict=True)
        for entry in _value_drift(part, element, label, seen, item)
    ]


def _replay(adapter: Any, parts: list[tuple[str, object]]) -> object:
    """What *adapter* builds from the raw items of *parts*, or ``None`` where pydantic refuses them."""
    try:
        return adapter.validate_python([part for _, part in parts])
    # a validation error, or a schema pydantic builds only on first use and then refuses
    except (ValueError, TypeError, RuntimeError, NameError):
        return None


def _replay_target(declared: _Declared) -> _Declared:
    """The type raw items are validated again as: the one member of the *declared* type without the `Annotated`
    validators of the container itself, which are what emptied it, and a set as a list of its items, so no model is
    hashed and each item keeps its place."""
    key = (id(declared), "replay")
    known = _DECLARED.get(key)
    if known is not None and known[0] is declared:
        return known[1]
    annotation, owner = declared
    member = _sole_member(annotation) or annotation
    if member in (set, frozenset) or get_origin(member) in (
        set,
        frozenset,
        collections.abc.Set,
        collections.abc.MutableSet,
    ):
        member = types.GenericAlias(list, get_args(member) or (Any,))
    target = (member, owner)
    if len(_DECLARED) < 1024:
        _DECLARED[key] = (declared, target)
    return target


def _revalidated(
    parts: list[tuple[str, object]], model: type, path: str, seen: frozenset[tuple[int, int]], reason: str
) -> list[str]:
    """Drift under each raw item that could hide a key, validated again on its own by *model*, JSON text in JSON mode
    as `Json[...]` read it."""
    validate = getattr(model, "model_validate", None)
    validate_json = getattr(model, "model_validate_json", None)
    if validate is None or validate_json is None:
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
