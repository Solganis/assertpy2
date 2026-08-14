"""One shape for every refusal of a wrong type, and one place that decides how it reads.

An assertion refuses a value or an argument in two situations, and until now each site worded its own:
ninety-three different phrasings across a hundred and fifty-nine sites, for about ten actual
situations.  Ten of them said "not a number" and eleven said "not a string", differing in whether the
offending value appeared at all, whether its type did, and in what order.  The reader could not learn
the format once, because there was no format.

The shape here is::

    <subject> must be <expectation>, but was <value> (<type>)

`subject` is `val` for the value under assertion and `given <name> arg` for an argument, which is the
wording the package already used where it named the operand at all.  The value is shown because that is
the question a reader actually has: not *that* the type was wrong, but *what arrived* instead.  A
payload field that came back as the string ``"12"`` rather than the number ``12`` is invisible in
"val is not numeric" and obvious in ``but was <'12'> (str)``.

The type is printed next to the value even when `repr` already implies it.  `'12'` and `12` are told
apart by their quotes, but `Decimal("1")`, a numpy scalar and any class with a hand-written `__repr__`
are not, and a rule with an exception is a rule nobody can rely on.
"""

from __future__ import annotations

from collections.abc import Sized
from typing import NoReturn, TypeVar

from ..errors import _safe_repr, _truncated

_T = TypeVar("_T")

# a refusal is read on one terminal line next to the traceback, so the value is capped well below the
# limit a diff row uses: what matters here is which value arrived, not all of it
_SHOWN = 60


# a type name is written by whoever defined the type and can be as long as they liked; the refusal is
# still one line
_NAMED = 40
# `repr` output is arbitrary text: it can carry escape sequences that repaint the terminal, and newlines
# that turn one refusal into what looks like several
_CONTROL = {code: "\\x{:02x}".format(code) for code in [*range(0x20), 0x7F, 0x85]} | {  # noqa: UP032  # an f-string cannot hold this escape
    # line and paragraph separators, plus the bidi overrides: those reorder the printed line without
    # changing the string, so a value can be made to read as something it is not
    code: "\\u{:04x}".format(code)  # noqa: UP032  # same
    for code in [0x2028, 0x2029, *range(0x202A, 0x2030), *range(0x2066, 0x206A)]
}


def _one_line(text: str) -> str:
    """*text* with control characters spelled out, so a refusal stays one readable line."""
    return text.translate(_CONTROL)


def _shown(value: object) -> str:
    """The value and its type, both capped, both safe to print next to a traceback.

    `_safe_repr` already answers `<unreprable X>` for a `__repr__` that raises, returns a non-string or
    recurses.  What it does not do is make the result printable: an object is free to return escape
    sequences or newlines from `__repr__`, and a diagnostic that repaints the terminal or spreads over
    four lines is worse than the mistake it reports.
    """
    # escaped before it is capped, not after: an escape is four characters where the original was one,
    # so capping first let a value of sixty control characters render as two hundred and forty
    shown = _truncated(_one_line(_safe_repr(value)), _SHOWN)
    return f"<{shown}> ({_truncated(type(value).__name__, _NAMED)})"


def raised_inside(exc: BaseException) -> bool:
    """Whether *exc* came out of somebody else's code rather than from the operation itself.

    `len(42)` and `1 < "a"` are refusals by the operation: the traceback stops at the frame that tried
    it.  A `__len__` or a `__lt__` that raises `TypeError` of its own adds a frame, and that error is a
    bug in the value being tested, not a wrong operand.  Answering it with "val must be a sized object"
    is a lie that sends the reader looking in the wrong file, so those are re-raised untouched.
    """
    traceback = exc.__traceback__
    return traceback is not None and traceback.tb_next is not None


def refuse(value: object, expectation: str, *, subject: str = "val") -> NoReturn:
    """Raise the refusal for *value*, for a check the caller has already made."""
    raise TypeError(f"{subject} must be {expectation}, but was {_shown(value)}")


def require_type(
    value: object, types: type[_T] | tuple[type[_T], ...], expectation: str, *, subject: str = "val"
) -> _T:
    """Refuse *value* unless it is an instance of *types*, which is what most of these checks are.

    The value is handed back so a caller can bind it and keep the narrowing: a type checker cannot see
    through a function that only raises, and the alternative at each site was a second `isinstance` or a
    cast written purely for the checker.
    """
    if not isinstance(value, types):
        refuse(value, expectation, subject=subject)
    return value


def argument(name: str) -> str:
    """The subject for an argument of the assertion, as opposed to the value under assertion."""
    return f"given {name} arg"


def sized_len(value: object, *, subject: str = "val") -> int:
    """The length of *value*, refusing it in the shared shape when it has none.

    Left to `len()` alone, the refusal reads "object of type 'int' has no len()": true, and about the
    builtin rather than about the assertion, with no mention of which operand was wrong.
    """
    if not isinstance(value, Sized):
        refuse(value, "a sized object", subject=subject)
    # past the protocol check there is nothing left to diagnose: a `__len__` that exists and still
    # raises is a bug in the value, and it travels out as its author wrote it. This is stricter than
    # asking where the error came from, and it does not depend on a Python frame being pushed: a
    # `__len__` implemented in C adds no frame, so the origin check alone would have mislabelled it
    return len(value)
