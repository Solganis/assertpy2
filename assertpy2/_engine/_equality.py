"""The equality decision itself, with nothing around it.

Equality was already computed in one place structurally: `_sub_diff_entries` walks both sides and the
compare config travels with it.  What was not in one place was the *entry* to that walk.  The recursive
mapping comparison, the ignore/include filtering and the dict-shape test lived on `HelpersMixin`, which
made them reachable from a builder and from nowhere else.  A matcher therefore could not offer
`tolerance`, `ignore`, `include`, `comparators` or `ignore_null` at all: `match.equal_to(x, tolerance=0.1)`
raised `TypeError` while `assert_that(v).is_equal_to(x, tolerance=0.1)` worked, and the two spellings of
one relation answered different questions.

Everything here is a free function over values.  The mixin keeps thin wrappers so that an extension
calling `self._dict_not_equal(...)` still works, and the matcher calls the same functions directly.
"""

from __future__ import annotations

import collections.abc
import re
import types
from typing import TYPE_CHECKING, cast

from ._compare import _guarded_not_equal, _keyed_types_differ, _node_decision, _spec_matches
from ._diff import _sub_diff_entries
from ._path import _ROOT
from ._require import refuse

if TYPE_CHECKING:
    from collections.abc import Callable

    from ._compare import _CompareConfig
    from ._introspection import MappingLike


def normalize_key_specs(specs: object, param: str) -> list:
    """An ``ignore``/``include`` argument as a flat list of key-specs.

    A ``list``/``set``/``frozenset`` is a collection of specs and is expanded.  A ``str``/``bytes``/
    ``tuple`` (a single key, or a nested-path key) or any non-iterable hashable key is one spec.  Any
    other iterable is refused: it is one-shot or ambiguous, and would otherwise be mishandled in silence
    as a single opaque key.
    """
    if isinstance(specs, (list, set, frozenset)):
        return list(specs)
    if isinstance(specs, (str, bytes, tuple)) or not isinstance(specs, collections.abc.Iterable):
        return [specs]
    refuse(specs, "a key, a nested-path tuple, or a list/set/frozenset of them", subject=param)


def ignore_specs(ignore: object) -> list:
    """Ignore-specs, keeping nested paths whole: a one-element tuple is just that key."""
    return [
        entry[0] if type(entry) is tuple and len(entry) == 1 else entry
        for entry in normalize_key_specs(ignore, "ignore")
    ]


def include_specs(include: object) -> list:
    """Include-specs for one level: a nested path selects its first segment here, the rest deeper down."""
    return [entry[0] if type(entry) is tuple else entry for entry in normalize_key_specs(include, "include")]


_NOT_DEFINED = object()


def _defined_on(cls: type, name: str) -> object:
    """What the interpreter's own type lookup finds for *name*, or `_NOT_DEFINED`.

    A walk of the MRO namespaces, which is what `_PyType_Lookup` does and what `getattr` on the class
    does not: the ordinary one runs through the metaclass, so a `__getattr__` there can fabricate a
    member the C slot never sees, and a `__getattribute__` there can hide one it does.  Reached through
    `type.__getattribute__` for the same reason.

    A `None` found this way is a definition and not an absence.  It is how a subclass takes a special
    member away, and the lookup stops on it exactly as it stops on a real one.
    """
    for base in type.__getattribute__(cls, "__mro__"):
        namespace = type.__getattribute__(base, "__dict__")
        if name in namespace:
            return namespace[name]
    return _NOT_DEFINED


_DIRECTLY_CALLABLE = (
    types.FunctionType,
    types.BuiltinFunctionType,
    types.MethodType,
    types.MethodWrapperType,
    types.WrapperDescriptorType,
    types.BuiltinMethodType,
)
"""Callables answered without resolving anything.  A class is deliberately not one: a metaclass can null
`__call__` out, and then `callable()` says yes and instantiating raises."""


def _bound_special(candidate: object, name: str, hops: int) -> object:
    """What the interpreter would call for *name* as a special member, or `_NOT_DEFINED`.

    The type lookup plus the descriptor step, which together are `_PyObject_LookupSpecial`.  A
    definition that cannot be resolved comes back as `None`, because that is what calling it amounts
    to: not callable, and the caller says so in its own words.
    """
    raw = _defined_on(type(candidate), name)
    if raw is _NOT_DEFINED:
        return _NOT_DEFINED
    binding = _defined_on(type(raw), "__get__")
    if binding is _NOT_DEFINED:
        return raw  # nothing to resolve through, so the definition found is the one called
    if not _reachable_call(binding, hops):
        return None  # a defined `__get__` is reached whatever it holds, so `__get__ = None` raises
    resolve = cast("Callable[[object, object, type], object]", binding)
    try:
        return resolve(raw, candidate, type(candidate))
    except Exception:
        # a binding that raises would raise on the real lookup too, and this question is asked while
        # rendering a failure, where a crash replaces the failure the reader came for
        return None


def _reachable_call(value: object, hops: int = 3) -> bool:
    """Whether calling *value* reaches an implementation rather than raising `TypeError`.

    `callable()` answers one level: it says the type has a call slot, and Python's own documentation
    says that is not a promise the call succeeds.  `__call__ = None` fills the slot and fails when
    reached, which is the same trick as `__getitem__ = None` one level down.

    Bounded rather than fully recursive, and the bound is not arbitrary: almost every callable is a
    function, a method or a class and is answered by the first test, so a chain deep enough to exhaust
    the hops is one built on purpose.  A value that does is called what `callable()` calls it.
    """
    if not callable(value):
        return False
    if isinstance(value, _DIRECTLY_CALLABLE) or hops == 0:
        return True
    return _reachable_call(_bound_special(value, "__call__", hops - 1), hops - 1)


def carries_callable(candidate: object, name: str) -> bool:
    """Whether calling `candidate.name()` reaches an implementation rather than raising `TypeError`.

    Deliberately no test for where the attribute came from.  Forwarding through `__getattr__` is how a
    proxy delegates, and a rule against it refuses every wrapper over a mapping.  Two attempts at such a
    rule were made and both were unsound: fabrication is not the offence, and no nominal test tells a
    `unittest.mock` attribute from a delegated one.

    A value that answers this and is then unreadable by key is handled where it shows, in `_dict_err`,
    which falls back to a plain repr rather than letting the shape guess replace the failure.
    """
    return _reachable_call(getattr(candidate, name, None))


def supports_subscript(candidate: object) -> bool:
    """Whether `candidate[key]` will reach an implementation instead of raising `TypeError`.

    Neither `hasattr` nor plain presence on the MRO answers this.  The operator is looked up on the
    type, so a `__getattr__` on the instance answers `hasattr` for a subscript the object does not
    have, and `__getitem__ = None` in a subclass shadows a working parent while still being present.

    The descriptor step is not decoration: a `__getitem__` written as a `property` really is resolved
    and really does work, measured against CPython.
    """
    return _reachable_call(_bound_special(candidate, "__getitem__", 3))


def mapping_shaped(
    candidate: object, *, check_keys: bool = True, check_values: bool = True, check_getitem: bool = True
) -> bool:
    """Whether *candidate* has the requested dict-like attributes.

    Deliberately structural rather than `isinstance(..., Mapping)`: the package accepts anything that
    answers `keys()`/`values()`/`[]`, which is what a config object or a lightweight row wrapper does.
    """
    if type(candidate) is dict:  # fast path: a real dict satisfies every check, skip the ABC isinstance
        return True
    if not isinstance(candidate, collections.abc.Iterable):
        return False
    if check_keys and not carries_callable(candidate, "keys"):
        return False
    if check_values and not carries_callable(candidate, "values"):
        return False
    return not check_getitem or supports_subscript(candidate)


def values_differ(value: object, other: object, config: _CompareConfig | None, *, at_root: bool = False) -> bool:
    """Whether two non-mapping values differ, delegating to the shared structural walker.

    Asking the walker keeps the equality *decision* and the rendered *diff* in agreement: every shape it
    can decompose (dataclass, attrs, namedtuple, model, sequence) is then compared under the compare
    config, instead of falling back to plain equality and silently dropping that config.  Without a
    config there is nothing to honour, so the plain check is kept exactly as it was.
    """
    if value is other and not at_root:
        # identity first, as Python's containers do.  Not at the root, where `nan` made `strict_types` the weaker rule
        return False
    if config is None:
        return _guarded_not_equal(value, other)
    entries = _sub_diff_entries(value, other, _ROOT, config=config)
    if entries is None:
        # a leaf the walker does not decompose: `strict_types` asked here called two equal sets unequal
        if config.tolerance is not None or config.comparators:
            return _node_decision(value, other, config) != "equal"
        return _guarded_not_equal(value, other)
    return bool(entries)


class IncludeKeysMissingError(LookupError):
    """An ``include`` naming a key the mapping does not have, at whatever depth it was found.

    Not a difference and not a refusal of types, so neither answer fits: the builder reports it as a
    failure in its own wording, and a matcher treats it as a non-match.  Carried as an exception because
    the recursion finds it several levels down, where the verdict `True`/`False` has no room for it.
    """

    def __init__(self, mapping: object, includes: list, missing: list) -> None:
        super().__init__(f"include names {missing}, which {mapping} does not have")
        self.mapping = mapping
        self.includes = includes
        self.missing = missing


def missing_include_keys(mapping: MappingLike, includes: list) -> list:
    """Include-keys naming something the mapping does not have."""
    return [key for key in includes if not isinstance(key, (re.Pattern, type)) and key not in mapping]


def mapping_differs(
    actual: object,
    expected: object,
    *,
    ignore: object = None,
    include: object = None,
    config: _CompareConfig | None = None,
    seen: frozenset | None = None,
) -> bool:
    """Whether two dict-like values differ under the given filtering and compare config.

    Normalization happens here rather than at the call sites, because the two spellings differ and the
    difference is easy to get wrong: at one level an `include` of `("user", "session")` selects `user`,
    while the recursion into `user` needs the whole path to strip its first segment from.
    """
    # one cast at the top beats a suppression on each of the six lookups below
    left = cast("MappingLike", actual)
    right = cast("MappingLike", expected)
    seen = frozenset() if seen is None else seen
    pair = (id(actual), id(expected))
    if pair in seen:
        return False
    seen = seen | {pair}

    if not (ignore or include or config is not None):
        return _guarded_not_equal(actual, expected)

    ignores = ignore_specs(ignore) if ignore else []
    if ignore or include:
        includes = include_specs(include) if include else []
        if include:
            missing = missing_include_keys(left, includes)
            if missing:
                raise IncludeKeysMissingError(left, includes, missing)
        keys_in_actual = {
            key
            for key in left
            if (not ignore or not _spec_matches(key, left[key], ignores))
            and (not include or _spec_matches(key, left[key], includes))
        }
        keys_in_expected = {
            key
            for key in right
            if (not ignore or not _spec_matches(key, right[key], ignores))
            and (not include or _spec_matches(key, right[key], includes))
        }
    else:
        keys_in_actual = set(left)
        keys_in_expected = set(right)

    if keys_in_actual != keys_in_expected:
        return True
    if config is not None and config.strict_types and _keyed_types_differ(actual, expected):
        # `{True: "a"}` and `{1: "a"}` are equal to Python and not under strict types; the walk below sees only values
        return True
    for key in keys_in_actual:
        nested_left, nested_right = left[key], right[key]
        if config is not None:
            decision = _node_decision(nested_left, nested_right, config, field=key)
            if decision == "equal":
                continue
            if decision == "leaf":
                return True
        nested_ignore = [entry[1:] for entry in ignores if type(entry) is tuple and entry[0] == key] if ignore else None
        # the nested half of an include keeps whole paths, and the level above already consumed the first segment
        nested_include = (
            [entry[1:] for entry in ignore_specs(include) if type(entry) is tuple and entry[0] == key]
            if include
            else None
        )
        if mapping_shaped(nested_left, check_values=False) and mapping_shaped(nested_right, check_values=False):
            if mapping_differs(
                nested_left, nested_right, ignore=nested_ignore, include=nested_include, config=config, seen=seen
            ):
                return True
        elif values_differ(nested_left, nested_right, config):
            return True
    return False
