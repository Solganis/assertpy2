from __future__ import annotations

import base64
import datetime
import decimal
import enum
import json
import os
import sys
import uuid
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable

__tracebackhide__ = True


class _Serializer(NamedTuple):
    cls: type
    encode: Callable[[object], object]
    decode: Callable[[object], object]
    tag: str


# user-registered serializers, checked before the built-in codec (last registered wins)
_SERIALIZERS: list[_Serializer] = []


class _Encoder(json.JSONEncoder):
    def default(self, o):
        for entry in _SERIALIZERS:
            if isinstance(o, entry.cls):
                return {"__type__": "custom", "__tag__": entry.tag, "__data__": entry.encode(o)}
        if isinstance(o, set):
            return {"__type__": "set", "__data__": list(o)}
        elif isinstance(o, complex):
            return {"__type__": "complex", "__data__": [o.real, o.imag]}
        elif isinstance(o, datetime.datetime):
            # the sub-second and offset suffixes are used only when needed, so snapshots without
            # microseconds/tzinfo keep the historical format and stay readable by older versions
            fmt = "%Y-%m-%d %H:%M:%S.%f" if o.microsecond else "%Y-%m-%d %H:%M:%S"
            if o.tzinfo is not None:
                fmt += "%z"
            return {"__type__": "datetime", "__data__": o.strftime(fmt)}
        elif isinstance(o, datetime.date):
            return {"__type__": "date", "__data__": o.isoformat()}
        elif isinstance(o, datetime.time):
            return {"__type__": "time", "__data__": o.isoformat()}
        elif isinstance(o, decimal.Decimal):
            return {"__type__": "decimal", "__data__": str(o)}
        elif isinstance(o, (bytes, bytearray)):
            return {"__type__": "bytes", "__data__": base64.b64encode(bytes(o)).decode("ascii")}
        elif isinstance(o, uuid.UUID):
            return {"__type__": "uuid", "__data__": str(o)}
        elif isinstance(o, enum.Enum):
            return {
                "__type__": "enum",
                "__class__": o.__class__.__name__,
                "__module__": o.__class__.__module__,
                "__data__": o.value,
            }
        elif "__dict__" in dir(o) and type(o) is not type:
            return {
                "__type__": "instance",
                "__class__": o.__class__.__name__,
                "__module__": o.__class__.__module__,
                "__data__": o.__dict__,
            }
        return json.JSONEncoder.default(self, o)


class _Decoder(json.JSONDecoder):
    def __init__(self):
        json.JSONDecoder.__init__(self, object_hook=self._object_hook)

    def _object_hook(self, decoded):
        if "__type__" in decoded and "__data__" in decoded:
            if decoded["__type__"] == "set":
                return set(decoded["__data__"])
            elif decoded["__type__"] == "complex":
                return complex(decoded["__data__"][0], decoded["__data__"][1])
            elif decoded["__type__"] == "datetime":
                raw = decoded["__data__"]
                tail = raw[len("0000-00-00 00:00:00") :]  # the date part contains "-", so probe past the seconds
                fmt = "%Y-%m-%d %H:%M:%S"
                if "." in tail:
                    fmt += ".%f"
                if "+" in tail or "-" in tail:
                    fmt += "%z"
                return datetime.datetime.strptime(raw, fmt)
            elif decoded["__type__"] == "date":
                return datetime.date.fromisoformat(decoded["__data__"])
            elif decoded["__type__"] == "time":
                return datetime.time.fromisoformat(decoded["__data__"])
            elif decoded["__type__"] == "decimal":
                return decimal.Decimal(decoded["__data__"])
            elif decoded["__type__"] == "bytes":
                return base64.b64decode(decoded["__data__"])
            elif decoded["__type__"] == "uuid":
                return uuid.UUID(decoded["__data__"])
            elif decoded["__type__"] == "custom":
                tag = decoded.get("__tag__")
                for entry in _SERIALIZERS:
                    if entry.tag == tag:
                        return entry.decode(decoded["__data__"])
                return decoded  # no serializer registered for this tag this run - leave the marker as-is
            elif decoded["__type__"] == "enum":
                target_class = _resolve_class(decoded["__module__"], decoded["__class__"])
                return target_class(decoded["__data__"]) if target_class is not None else decoded
            elif decoded["__type__"] == "instance":
                target_class = _resolve_class(decoded["__module__"], decoded["__class__"])
                if target_class is None:
                    return decoded
                instance = target_class.__new__(target_class)
                instance.__dict__ = decoded["__data__"]
                return instance
        return decoded


def _resolve_class(module_name, class_name):
    """Resolve a class by module+name without importing anything (never runs arbitrary imports, per the
    snapshot security model); returns ``None`` if the module is not already imported or the name is absent."""
    if module_name not in sys.modules:
        return None
    return getattr(sys.modules[module_name], class_name, None)


def _save(name, val):
    tmp = f"{name}.{os.getpid()}.tmp"
    with open(tmp, "w") as file_handle:
        json.dump(val, file_handle, indent=2, separators=(",", ": "), sort_keys=True, cls=_Encoder)
    os.replace(tmp, name)


def _load(name):
    with open(name) as file_handle:
        return json.load(file_handle, cls=_Decoder)
