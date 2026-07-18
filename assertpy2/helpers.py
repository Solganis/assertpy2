import collections.abc
import dataclasses
import datetime
import math
import numbers
import re

try:
    import attrs
except ImportError:  # pragma: no cover - optional dependency; the attrs branch runs only when present
    attrs = None  # ty: ignore[invalid-assignment]  # sentinel for the absent optional module

from assertpy2.errors import DiffResult, _safe_repr, _truncated

from ._engine._compare import _CompareConfig, _guarded_not_equal, _node_decision, _spec_matches
from ._engine._diff import _sub_diff_entries
from ._engine._introspection import is_attrs_instance, is_model_dump_object, is_namedtuple
from ._engine._mixin_base import _MixinBase

__tracebackhide__ = True


class HelpersMixin(_MixinBase):
    """Helpers mixin.  For internal use only."""

    def _fmt_items(self, items):
        """Helper to format the given items."""
        if len(items) == 0:
            return "<>"
        elif len(items) == 1 and hasattr(items, "__getitem__"):
            return f"<{items[0]}>"
        else:
            formatted = str(items)
            if formatted[0] in "([":
                formatted = formatted[1:]
            if formatted[-1] in ")]":
                formatted = formatted[:-1]
            return f"<{formatted}>"

    def _fmt_args_kwargs(self, *some_args, **some_kwargs):
        """Helper to convert the given args and kwargs into a string."""
        out_args = out_kwargs = ""
        if some_args:
            out_args = str(some_args).lstrip("(").rstrip(",)")
        if some_kwargs:
            out_kwargs = ", ".join(
                [
                    str(pair).lstrip("(").rstrip(")").replace(", ", ": ")
                    for pair in [(key, some_kwargs[key]) for key in sorted(some_kwargs.keys())]
                ]
            )

        if some_args and some_kwargs:
            return out_args + ", " + out_kwargs
        elif some_args:
            return out_args
        elif some_kwargs:
            return out_kwargs
        else:
            return ""

    def _validate_between_args(self, val_type, low, high):
        """Helper to validate given range args."""
        low_type = type(low)
        high_type = type(high)

        if val_type in self._NUMERIC_NON_COMPAREABLE:
            raise TypeError(f"ordering is not defined for type <{val_type.__name__}>")

        if val_type in self._NUMERIC_COMPAREABLE:
            if low_type is not val_type:
                raise TypeError(f"given low arg must be <{val_type.__name__}>, but was <{low_type.__name__}>")
            if high_type is not val_type:
                raise TypeError(f"given high arg must be <{val_type.__name__}>, but was <{high_type.__name__}>")
        elif isinstance(self.val, numbers.Number):
            if not isinstance(low, numbers.Number):
                raise TypeError(f"given low arg must be numeric, but was <{low_type.__name__}>")
            if not isinstance(high, numbers.Number):
                raise TypeError(f"given high arg must be numeric, but was <{high_type.__name__}>")
        else:
            raise TypeError(f"ordering is not defined for type <{val_type.__name__}>")

        if low > high:
            raise ValueError("given low arg must be less than given high arg")

    def _validate_close_to_args(self, val, other, tolerance):
        """Helper for validate given arg and delta."""
        if type(val) is complex or type(other) is complex or type(tolerance) is complex:
            raise TypeError("ordering is not defined for complex numbers")

        if not isinstance(val, numbers.Number) and not isinstance(val, datetime.datetime):
            raise TypeError("val is not numeric or datetime")

        if isinstance(val, datetime.datetime):
            if not isinstance(other, datetime.datetime):
                raise TypeError(f"given arg must be datetime, but was <{type(other).__name__}>")
            if not isinstance(tolerance, datetime.timedelta):
                raise TypeError(f"given tolerance arg must be timedelta, but was <{type(tolerance).__name__}>")
        else:
            if not isinstance(other, numbers.Number):
                raise TypeError("given arg must be numeric")
            if not isinstance(tolerance, numbers.Number):
                raise TypeError("given tolerance arg must be numeric")
            if math.isnan(tolerance):
                raise ValueError("given tolerance arg must not be NaN")
            if tolerance < 0:
                raise ValueError("given tolerance arg must be positive")

    def _is_dict_like(self, candidate, check_keys=True, check_values=True, check_getitem=True):
        """Return whether *candidate* has the requested dict-like attributes."""
        if type(candidate) is dict:  # fast path: a real dict satisfies every check, skip the ABC isinstance
            return True
        if not isinstance(candidate, collections.abc.Iterable):
            return False
        if check_keys and not callable(getattr(candidate, "keys", None)):
            return False
        if check_values and not callable(getattr(candidate, "values", None)):
            return False
        return not (check_getitem and not hasattr(candidate, "__getitem__"))

    def _require_dict_like(self, candidate, check_keys=True, check_values=True, check_getitem=True, name="val"):
        """Raise ``TypeError`` unless *candidate* has the requested dict-like attributes."""
        if not isinstance(candidate, collections.abc.Iterable):
            raise TypeError(f"{name} <{type(candidate).__name__}> is not dict-like: not iterable")
        if check_keys and not callable(getattr(candidate, "keys", None)):
            raise TypeError(f"{name} <{type(candidate).__name__}> is not dict-like: missing keys()")
        if check_values and not callable(getattr(candidate, "values", None)):
            raise TypeError(f"{name} <{type(candidate).__name__}> is not dict-like: missing values()")
        if check_getitem and not hasattr(candidate, "__getitem__"):
            raise TypeError(f"{name} <{type(candidate).__name__}> is not dict-like: missing [] accessor")

    def _check_iterable(self, val, check_getitem=True, name="val"):
        """Helper to check if given val is iterable with optional item access."""
        if not isinstance(val, collections.abc.Iterable):
            raise TypeError(f"{name} <{type(val).__name__}> is not iterable")
        if check_getitem and not hasattr(val, "__getitem__"):
            raise TypeError(f"{name} <{type(val).__name__}> does not have [] accessor")

    def _dict_not_equal(self, val, other, ignore=None, include=None, config: _CompareConfig | None = None, _seen=None):
        """Helper to compare dicts, optionally honoring ignore/include key-specs and a compare ``config``."""
        if _seen is None:
            _seen = set()
        pair = (id(val), id(other))
        if pair in _seen:
            return False
        _seen = _seen | {pair}

        if not (ignore or include or config is not None):
            return _guarded_not_equal(val, other)

        ignores = []  # bound for the nested-recursion use below; only read when ``ignore`` is set
        if ignore or include:
            ignores = self._dict_ignore(ignore)
            includes = self._dict_include(include)

            if include:
                missing = [
                    include_key
                    for include_key in includes
                    if not isinstance(include_key, (re.Pattern, type)) and include_key not in val
                ]
                if missing:
                    keys_suffix = "" if len(includes) == 1 else "s"
                    missing_suffix = "" if len(missing) == 1 else "s"
                    includes_fmt = self._fmt_items(
                        [
                            ".".join([str(segment) for segment in include_key])
                            if type(include_key) is tuple
                            else include_key
                            for include_key in includes
                        ]
                    )
                    missing_fmt = self._fmt_items(missing)
                    return self.error(
                        f"Expected <{val}> to include key{keys_suffix} {includes_fmt},"
                        f" but did not include key{missing_suffix} {missing_fmt}."
                    )

            keys_in_val = {
                key
                for key in val
                if (not ignore or not _spec_matches(key, val[key], ignores))
                and (not include or _spec_matches(key, val[key], includes))
            }
            keys_in_other = {
                key
                for key in other
                if (not ignore or not _spec_matches(key, other[key], ignores))
                and (not include or _spec_matches(key, other[key], includes))
            }
        else:
            keys_in_val = set(val)
            keys_in_other = set(other)

        if keys_in_val != keys_in_other:
            return True
        for key in keys_in_val:
            if config is not None:
                decision = _node_decision(val[key], other[key], config, field=key)
                if decision == "equal":
                    continue
                if decision == "leaf":
                    return True
            if self._is_dict_like(val[key], check_values=False) and self._is_dict_like(other[key], check_values=False):
                subdicts_not_equal = self._dict_not_equal(
                    val[key],
                    other[key],
                    ignore=[entry[1:] for entry in ignores if type(entry) is tuple and entry[0] == key]
                    if ignore
                    else None,
                    include=[
                        entry[1:] for entry in self._dict_ignore(include) if type(entry) is tuple and entry[0] == key
                    ]
                    if include
                    else None,
                    config=config,
                    _seen=_seen,
                )
                if subdicts_not_equal:
                    return True
            elif _guarded_not_equal(val[key], other[key]):
                return True
        return False

    @staticmethod
    def _normalize_key_specs(specs, param):
        """Normalize an ``ignore``/``include`` kwarg into a flat list of key-specs.

        A ``list``, ``set`` or ``frozenset`` is treated as a collection of key-specs and
        expanded.  A ``str``/``bytes``/``tuple`` (a single key or a nested-path key) or any
        non-iterable hashable key is wrapped as a single key-spec.  Any other iterable
        (generator, iterator, ``dict_keys``, ...) is rejected, since it is one-shot or
        ambiguous and would otherwise be silently mishandled as one opaque key.
        """
        if isinstance(specs, (list, set, frozenset)):
            return list(specs)
        if isinstance(specs, (str, bytes, tuple)) or not isinstance(specs, collections.abc.Iterable):
            return [specs]
        raise TypeError(
            f"{param} must be a key, a nested-path tuple, or a list/set/frozenset of them,"
            f" but was <{type(specs).__name__}>"
        )

    @staticmethod
    def _dict_ignore(ignore):
        """Helper to make list for given ignore kwarg values."""
        return [
            entry[0] if type(entry) is tuple and len(entry) == 1 else entry
            for entry in HelpersMixin._normalize_key_specs(ignore, "ignore")
        ]

    @staticmethod
    def _dict_include(include):
        """Helper to make a list from given include kwarg values."""
        return [
            entry[0] if type(entry) is tuple else entry
            for entry in HelpersMixin._normalize_key_specs(include, "include")
        ]

    def _dict_err(
        self,
        val: object,
        other: object,
        ignore: object = None,
        include: object = None,
        config: _CompareConfig | None = None,
    ) -> None:
        """Helper to construct error message for dict comparison.

        A compare ``config`` is routed through both the textual repr (a tolerated / comparator-equal leaf is
        ellipsized, never shown) and the structured diff, so the message and diff agree on what differs.
        """

        def _dict_repr(mapping, counterpart, _seen=None):
            if _seen is None:
                _seen = set()
            if id(mapping) in _seen:
                return "{<circular ref>}"
            _seen = _seen | {id(mapping)}
            parts = []
            ellip = False
            # build items by iterating keys + [] (the dict-likeness gate guarantees those, not items())
            mapping_items = ((key, mapping[key]) for key in mapping)
            for key, value in sorted(mapping_items, key=lambda item: _safe_repr(item[0])):
                if key not in counterpart:
                    parts.append(f"{_safe_repr(key)}: {_safe_repr(value)}")
                else:
                    decision = _node_decision(value, counterpart[key], config, field=key)
                    if decision == "equal":
                        ellip = True
                    elif decision == "leaf":
                        parts.append(f"{_safe_repr(key)}: {_safe_repr(value)}")
                    else:  # recurse
                        other_value = counterpart[key]
                        if self._is_dict_like(value, check_values=False) and self._is_dict_like(
                            other_value, check_values=False
                        ):
                            value_repr = _dict_repr(value, other_value, _seen)
                        elif _both_list_like(value, other_value):
                            value_repr = _list_repr(value, other_value, _seen)
                        else:
                            value_repr = _safe_repr(value)
                        parts.append(f"{_safe_repr(key)}: {value_repr}")
            out = ", ".join(parts)
            ellip_prefix = ".." if ellip and not parts else ".., " if ellip else ""
            return f"{{{ellip_prefix}{out}}}"

        def _both_list_like(left, right):
            return (
                isinstance(left, (list, tuple))
                and isinstance(right, (list, tuple))
                and not is_namedtuple(left)
                and not is_namedtuple(right)
            )

        def _list_repr(seq, counterpart, _seen):
            """List counterpart of ``_dict_repr``: collapse equal elements to ``..`` and drill only into
            the differing ones, so a one-element change in a long list reads as ``[.., {.., 'v': 'y'}]``
            instead of dumping the whole list.  Always reached through ``_dict_repr`` (a list is only ever
            a nested value), so ``_seen`` is passed in, never defaulted."""
            if id(seq) in _seen:
                return "[<circular ref>]"
            _seen = _seen | {id(seq)}
            parts = []
            ellip = False
            for index, value in enumerate(seq):
                if index >= len(counterpart):
                    parts.append(_safe_repr(value))  # extra element beyond the counterpart's length
                    continue
                other_value = counterpart[index]
                decision = _node_decision(value, other_value, config, field=None)
                if decision == "equal":
                    ellip = True
                elif decision == "leaf":
                    parts.append(_safe_repr(value))
                elif self._is_dict_like(value, check_values=False) and self._is_dict_like(
                    other_value, check_values=False
                ):
                    parts.append(_dict_repr(value, other_value, _seen))
                elif _both_list_like(value, other_value):
                    parts.append(_list_repr(value, other_value, _seen))
                else:
                    parts.append(_safe_repr(value))
            opener, closer = ("(", ")") if isinstance(seq, tuple) else ("[", "]")  # keep tuples looking like tuples
            ellip_prefix = ".." if ellip and not parts else ".., " if ellip else ""
            return f"{opener}{ellip_prefix}{', '.join(parts)}{closer}"

        ignore_err = include_err = ""
        if ignore:
            ignores = self._dict_ignore(ignore)
            ignore_fmt = self._fmt_items(
                [".".join([str(segment) for segment in entry]) if type(entry) is tuple else entry for entry in ignores]
            )
            ignore_err = f" ignoring keys {ignore_fmt}"
        if include:
            includes = self._dict_ignore(include)
            include_fmt = self._fmt_items(
                [".".join([str(segment) for segment in entry]) if type(entry) is tuple else entry for entry in includes]
            )
            include_err = f" including keys {include_fmt}"

        diff_entries = _sub_diff_entries(val, other, "", config=config) or []
        diff = DiffResult(kind="dict", entries=diff_entries) if diff_entries else None

        val_repr = _truncated(_dict_repr(val, other))
        other_repr = _truncated(_dict_repr(other, val))
        ignore_part = ignore_err if ignore else ""
        include_part = include_err if include else ""
        self.error(
            f"Expected <{val_repr}> to be equal to <{other_repr}>{ignore_part}{include_part}, but was not.",
            actual=val,
            expected=other,
            diff=diff,
        )

    @staticmethod
    def _to_comparable_dict(obj):
        """Convert an object with introspectable fields to a dict for comparison.

        Returns None if the object cannot be converted.
        """
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            # like dataclasses.asdict but keeps leaf values by reference; asdict deep-copies every leaf,
            # which crashes on un-copyable fields (locks, sockets) and breaks identity equality even for
            # fields the caller ignores
            def as_shallow(node):
                if dataclasses.is_dataclass(node) and not isinstance(node, type):
                    return {field.name: as_shallow(getattr(node, field.name)) for field in dataclasses.fields(node)}
                if isinstance(node, tuple) and hasattr(node, "_fields"):
                    return type(node)(*[as_shallow(item) for item in node])
                if isinstance(node, (list, tuple)):
                    return type(node)(as_shallow(item) for item in node)
                if isinstance(node, dict):
                    return {as_shallow(key): as_shallow(value) for key, value in node.items()}
                return node

            return as_shallow(obj)
        if is_namedtuple(obj):
            return dict(obj._asdict())
        if is_model_dump_object(obj):
            return obj.model_dump()
        if is_attrs_instance(obj):
            # attrs is importable whenever an attrs instance exists, so the guarded import bound it;
            # asdict recurses like dataclasses.asdict, flattening nested attrs for ignore/include
            return attrs.asdict(obj)
        if hasattr(obj, "__dict__") and not isinstance(obj, type):
            return dict(vars(obj))
        return None
