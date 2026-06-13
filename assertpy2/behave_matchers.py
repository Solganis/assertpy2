from __future__ import annotations

_BOOL_TRUE = frozenset({"true", "yes", "1", "on"})
_BOOL_FALSE = frozenset({"false", "no", "0", "off"})


def _with_pattern(pattern):
    def decorator(func):
        func.pattern = pattern
        return func

    return decorator


@_with_pattern(r"\d+")
def _positive_int(text):
    value = int(text)
    if value <= 0:
        raise ValueError(f"expected positive integer, got {value}")
    return value


@_with_pattern(r"\d+")
def _non_negative_int(text):
    return int(text)


@_with_pattern(r"\d+\.?\d*")
def _positive_float(text):
    value = float(text)
    if value <= 0:
        raise ValueError(f"expected positive float, got {value}")
    return value


@_with_pattern(r".+?")
def _non_empty_string(text):
    stripped = text.strip()
    if not stripped:
        raise ValueError("expected non-empty string, got blank")
    return stripped


@_with_pattern(r"\w+")
def _bool_like(text):
    lower = text.strip().lower()
    if lower in _BOOL_TRUE:
        return True
    if lower in _BOOL_FALSE:
        return False
    raise ValueError(f"expected boolean-like value, got {text!r}")


ASSERTPY_TYPES = {
    "PositiveInt": _positive_int,
    "NonNegativeInt": _non_negative_int,
    "PositiveFloat": _positive_float,
    "NonEmptyString": _non_empty_string,
    "BoolLike": _bool_like,
}


def register_assertpy_types() -> None:
    """Register assertpy2 parameter types for Behave step definitions.

    Registers the following types for use in step patterns:

    - ``{param:PositiveInt}`` - positive integer (> 0)
    - ``{param:NonNegativeInt}`` - non-negative integer (>= 0)
    - ``{param:PositiveFloat}`` - positive float (> 0)
    - ``{param:NonEmptyString}`` - non-empty, stripped string
    - ``{param:BoolLike}`` - boolean from true/false/yes/no/1/0/on/off

    Requires ``behave`` to be installed (``pip install assertpy2[behave]``).

    Raises:
        ImportError: if behave is not installed
    """
    try:
        from behave import register_type  # ty: ignore[unresolved-import]  # optional dependency
    except ImportError:
        raise ImportError(
            "behave is required for register_assertpy_types(). Install it with: pip install assertpy2[behave]"
        ) from None
    register_type(**ASSERTPY_TYPES)
