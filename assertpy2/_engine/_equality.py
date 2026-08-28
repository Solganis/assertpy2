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
from typing import TYPE_CHECKING, cast

from ._compare import _guarded_not_equal, _keyed_types_differ, _node_decision, _spec_matches
from ._diff import _sub_diff_entries
from ._path import _ROOT
from ._require import refuse

if TYPE_CHECKING:
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
    if check_keys and not callable(getattr(candidate, "keys", None)):
        return False
    if check_values and not callable(getattr(candidate, "values", None)):
        return False
    return not (check_getitem and not hasattr(candidate, "__getitem__"))


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
