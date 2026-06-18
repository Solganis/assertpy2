import collections
import dataclasses
import datetime
import math
import numbers

from assertpy2.errors import DiffEntry, DiffResult

from ._mixin_base import _MixinBase

__tracebackhide__ = True


class HelpersMixin(_MixinBase):
    """Helpers mixin.  For internal use only."""

    def _fmt_items(self, i):
        """Helper to format the given items."""
        if len(i) == 0:
            return "<>"
        elif len(i) == 1 and hasattr(i, "__getitem__"):
            return f"<{i[0]}>"
        else:
            s = str(i)
            if s[0] in "([":
                s = s[1:]
            if s[-1] in ")]":
                s = s[:-1]
            return f"<{s}>"

    def _fmt_args_kwargs(self, *some_args, **some_kwargs):
        """Helper to convert the given args and kwargs into a string."""
        if some_args:
            out_args = str(some_args).lstrip("(").rstrip(",)")
        if some_kwargs:
            out_kwargs = ", ".join(
                [
                    str(i).lstrip("(").rstrip(")").replace(", ", ": ")
                    for i in [(k, some_kwargs[k]) for k in sorted(some_kwargs.keys())]
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
                raise TypeError(f"given high arg must be <{val_type.__name__}>, but was <{low_type.__name__}>")
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

        if not isinstance(val, numbers.Number) and type(val) is not datetime.datetime:
            raise TypeError("val is not numeric or datetime")

        if type(val) is datetime.datetime:
            if type(other) is not datetime.datetime:
                raise TypeError(f"given arg must be datetime, but was <{type(other).__name__}>")
            if type(tolerance) is not datetime.timedelta:
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

    def _check_dict_like(
        self, d, check_keys=True, check_values=True, check_getitem=True, name="val", return_as_bool=False
    ):
        """Helper to check if given val has various dict-like attributes."""
        if not isinstance(d, collections.abc.Iterable):
            if return_as_bool:
                return False
            else:
                raise TypeError(f"{name} <{type(d).__name__}> is not dict-like: not iterable")
        if check_keys and (not hasattr(d, "keys") or not callable(d.keys)):
            if return_as_bool:
                return False
            else:
                raise TypeError(f"{name} <{type(d).__name__}> is not dict-like: missing keys()")
        if check_values and (not hasattr(d, "values") or not callable(d.values)):
            if return_as_bool:
                return False
            else:
                raise TypeError(f"{name} <{type(d).__name__}> is not dict-like: missing values()")
        if check_getitem and not hasattr(d, "__getitem__"):
            if return_as_bool:
                return False
            else:
                raise TypeError(f"{name} <{type(d).__name__}> is not dict-like: missing [] accessor")
        if return_as_bool:
            return True

    def _check_iterable(self, val, check_getitem=True, name="val"):
        """Helper to check if given val is iterable with optional item access."""
        if not isinstance(val, collections.abc.Iterable):
            raise TypeError(f"{name} <{type(val).__name__}> is not iterable")
        if check_getitem and not hasattr(val, "__getitem__"):
            raise TypeError(f"{name} <{type(val).__name__}> does not have [] accessor")

    def _dict_not_equal(self, val, other, ignore=None, include=None, _seen=None):
        """Helper to compare dicts."""
        if _seen is None:
            _seen = set()
        pair = (id(val), id(other))
        if pair in _seen:
            return False
        _seen = _seen | {pair}

        if ignore or include:
            ignores = self._dict_ignore(ignore)
            includes = self._dict_include(include)

            if include:
                missing = []
                for i in includes:
                    if i not in val:
                        missing.append(i)
                if missing:
                    keys_suffix = "" if len(includes) == 1 else "s"
                    missing_suffix = "" if len(missing) == 1 else "s"
                    includes_fmt = self._fmt_items(
                        [".".join([str(s) for s in i]) if type(i) is tuple else i for i in includes]
                    )
                    missing_fmt = self._fmt_items(missing)
                    return self.error(
                        f"Expected <{val}> to include key{keys_suffix} {includes_fmt},"
                        f" but did not include key{missing_suffix} {missing_fmt}."
                    )

            if ignore and include:
                k1 = {k for k in val if k not in ignores and k in includes}
            elif ignore:
                k1 = {k for k in val if k not in ignores}
            else:  # include
                k1 = {k for k in val if k in includes}

            if ignore and include:
                k2 = {k for k in other if k not in ignores and k in includes}
            elif ignore:
                k2 = {k for k in other if k not in ignores}
            else:  # include
                k2 = {k for k in other if k in includes}

            if k1 != k2:
                return True
            else:
                for k in k1:
                    if self._check_dict_like(val[k], check_values=False, return_as_bool=True) and self._check_dict_like(
                        other[k], check_values=False, return_as_bool=True
                    ):
                        subdicts_not_equal = self._dict_not_equal(
                            val[k],
                            other[k],
                            ignore=[i[1:] for i in ignores if type(i) is tuple and i[0] == k] if ignore else None,
                            include=[i[1:] for i in self._dict_ignore(include) if type(i) is tuple and i[0] == k]
                            if include
                            else None,
                            _seen=_seen,
                        )
                        if subdicts_not_equal:
                            return True
                    elif val[k] != other[k]:
                        return True
            return False
        else:
            return val != other

    @staticmethod
    def _dict_ignore(ignore):
        """Helper to make list for given ignore kwarg values."""
        return [i[0] if type(i) is tuple and len(i) == 1 else i for i in (ignore if type(ignore) is list else [ignore])]

    @staticmethod
    def _dict_include(include):
        """Helper to make a list from given include kwarg values."""
        return [i[0] if type(i) is tuple else i for i in (include if type(include) is list else [include])]

    def _dict_err(self, val, other, ignore=None, include=None):
        """Helper to construct error message for dict comparison."""

        def _dict_repr(d, other, _seen=None):
            if _seen is None:
                _seen = set()
            if id(d) in _seen:
                return "{<circular ref>}"
            _seen = _seen | {id(d)}
            parts = []
            ellip = False
            for k, v in sorted(d.items()):
                if k not in other:
                    parts.append(f"{k!r}: {v!r}")
                elif v != other[k]:
                    val_repr = (
                        _dict_repr(v, other[k], _seen)
                        if self._check_dict_like(v, check_values=False, return_as_bool=True)
                        and self._check_dict_like(other[k], check_values=False, return_as_bool=True)
                        else repr(v)
                    )
                    parts.append(f"{k!r}: {val_repr}")
                else:
                    ellip = True
            out = ", ".join(parts)
            ellip_prefix = ".." if ellip and not parts else ".., " if ellip else ""
            return f"{{{ellip_prefix}{out}}}"

        def _build_diff(actual_dict, expected_dict, prefix="", _seen=None):
            if _seen is None:
                _seen = set()
            pair = (id(actual_dict), id(expected_dict))
            if pair in _seen:
                return [DiffEntry(path=prefix or ".", actual="<circular ref>", expected="<circular ref>")]
            _seen = _seen | {pair}

            entries = []
            all_keys = sorted(set(actual_dict) | set(expected_dict))
            for k in all_keys:
                path = f"{prefix}.{k}" if prefix else str(k)
                if k not in expected_dict:
                    entries.append(DiffEntry(path=path, actual=actual_dict[k], expected=None))
                elif k not in actual_dict:
                    entries.append(DiffEntry(path=path, actual=None, expected=expected_dict[k]))
                elif actual_dict[k] != expected_dict[k]:
                    a_val = actual_dict[k]
                    e_val = expected_dict[k]
                    if self._check_dict_like(a_val, check_values=False, return_as_bool=True) and self._check_dict_like(
                        e_val, check_values=False, return_as_bool=True
                    ):
                        entries.extend(_build_diff(a_val, e_val, prefix=path, _seen=_seen))
                    elif isinstance(a_val, (list, tuple)) and isinstance(e_val, (list, tuple)):
                        entries.extend(_build_list_diff(a_val, e_val, prefix=path, _seen=_seen))
                    else:
                        entries.append(DiffEntry(path=path, actual=a_val, expected=e_val))
            return entries

        def _build_list_diff(actual_list, expected_list, prefix="", _seen=None):
            if _seen is None:  # pragma: no cover - only called from _build_diff which always passes _seen
                _seen = set()
            entries = []
            max_len = max(len(actual_list), len(expected_list))
            for i in range(max_len):
                path = f"{prefix}[{i}]"
                if i >= len(actual_list):
                    entries.append(DiffEntry(path=path, actual=None, expected=expected_list[i]))
                elif i >= len(expected_list):
                    entries.append(DiffEntry(path=path, actual=actual_list[i], expected=None))
                elif actual_list[i] != expected_list[i]:
                    a_item = actual_list[i]
                    e_item = expected_list[i]
                    if self._check_dict_like(a_item, check_values=False, return_as_bool=True) and self._check_dict_like(
                        e_item, check_values=False, return_as_bool=True
                    ):
                        entries.extend(_build_diff(a_item, e_item, prefix=path, _seen=_seen))
                    else:
                        entries.append(DiffEntry(path=path, actual=a_item, expected=e_item))
            return entries

        if ignore:
            ignores = self._dict_ignore(ignore)
            ignore_fmt = self._fmt_items([".".join([str(s) for s in i]) if type(i) is tuple else i for i in ignores])
            ignore_err = f" ignoring keys {ignore_fmt}"
        if include:
            includes = self._dict_ignore(include)
            include_fmt = self._fmt_items([".".join([str(s) for s in i]) if type(i) is tuple else i for i in includes])
            include_err = f" including keys {include_fmt}"

        diff_entries = _build_diff(val, other)
        diff = DiffResult(kind="dict", entries=diff_entries) if diff_entries else None

        val_repr = _dict_repr(val, other)
        other_repr = _dict_repr(other, val)
        ignore_part = ignore_err if ignore else ""
        include_part = include_err if include else ""
        return self.error(
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
            return dataclasses.asdict(obj)
        if isinstance(obj, tuple) and hasattr(obj, "_fields"):
            return dict(obj._asdict())
        if hasattr(obj, "model_dump") and callable(obj.model_dump):
            return obj.model_dump()
        if hasattr(obj, "__attrs_attrs__"):
            return {a.name: getattr(obj, a.name) for a in obj.__attrs_attrs__}
        if hasattr(obj, "__dict__") and not isinstance(obj, type):
            return dict(vars(obj))
        return None
