"""Which checkers reject which relation in `typing_cases.py`, and with which diagnostic, as measured.

Read by `test_typing_negative.py`, which fails on any difference in either direction.  A case that
starts being caught is as much a change as one that stops: the first says a signature was tightened and
this file needs updating, the second says one was loosened by accident.

**The diagnostic code is part of the record, not decoration.** An earlier version stored only "these
checkers rejected it", and a counter-example whose fixture lacked an import reported an undefined name
rather than a type error.  The test was green and the relation it existed for was never checked.  The
codes also make a disagreement between checkers visible instead of comfortable.

**What the measurement says today.** Twenty-one of the twenty-five incompatible relations are rejected,
and all three checkers agree on every one of them.

The four that are not split into **three** boundaries, and the two numbers are worth keeping apart: the
numeric approximation accounts for two of the four cases on its own.

**The numeric bound is an approximation, and the direction of its error is the point.** The runtime asks
`isinstance(other, numbers.Number)`, and a numeric tower built on registration is invisible to a
checker: `numpy.int64` is a `numbers.Number` at runtime and inherits nothing static.  `SupportsFloat` is
the closest thing a checker can read, so two shapes pass it and the runtime refuses them by name, a
value convertible to a float that is not a number, and an array where a scalar belongs.  That is the
tolerable direction: the first attempt erred the other way, naming a list of types and rejecting
`numpy.int64` outright, which breaks a working suite rather than delaying a clear message.

A value ordered against anything but convertible to nothing is refused by both, which is the half of
the approximation that works.

**Two more remain, and both are the same thing: a surface reached through `__getattr__`.** A value with no
protocol of its own gets the generic builder, which carries every method there is.  And `.not_` returns
a proxy that resolves any name, so the negated branch accepts what the protocol refuses - the runtime
still says `ordering is not defined for type <complex>`, only later.  Closing the second means a second
protocol per type, doubling the typed surface for one inverted call.

They fall into two families, and the split is the useful reading:

* **the argument does not fit** (`invalid-argument-type` / `arg-type` / `reportArgumentType`) - the
  relation between the two values is impossible.  This family grew from two rows to ten when the
  arguments stopped being declared `object` and were bound to the value's own type;
* **the method is not there** (`unresolved-attribute` / `attr-defined` / `reportAttributeAccessIssue`) -
  the value's protocol never carried it.  `complex` and `bool` joined this family once they stopped
  sharing the numeric protocol: the runtime already refused ordering on a complex number and parity on
  a bool, and now the type says so first.

`matcher-for-another-type` is the one case `ty` answers with `no-matching-overload` where the others say
the argument does not fit.  Same family, different route through an overload set.

**The one that remains is not about arguments.** `assert_that(Person()).is_positive()` type-checks
because a value with no protocol of its own gets the generic builder, and the generic builder carries
every method there is.  Nothing about a signature can catch that.  It closes when the runtime builder is
split, or not at all.

**The traps this file exists to catch.** A numeric comparison is bound to `SupportsFloat` rather than to
the value's own numeric type, because comparing an `int` against a `float` is ordinary and had to keep
working.  The first attempt named a list of types, `float | Decimal | Fraction`, and rejected
`numpy.int64`: a false rejection on a library this project documents support for, found by probing
ordinary third-party usage rather than by review.  A capability covers what a list of types cannot.

Membership takes `_E | Matcher[_E]`, since a matcher stands in for an item wherever one is accepted.
Both traps were found by the valid half of this file going red, which is what it is for.
"""

from __future__ import annotations

_ARGUMENT: dict[str, frozenset[str]] = {
    "ty": frozenset({"invalid-argument-type"}),
    "mypy": frozenset({"arg-type"}),
    "pyright": frozenset({"reportArgumentType"}),
}

_MISSING: dict[str, frozenset[str]] = {
    "ty": frozenset({"unresolved-attribute"}),
    "mypy": frozenset({"attr-defined"}),
    "pyright": frozenset({"reportAttributeAccessIssue"}),
}

CAUGHT: dict[str, dict[str, frozenset[str]]] = {
    # --- the argument cannot be what the value would have to hold ---------------------------------
    "contains-item-of-another-type": _ARGUMENT,
    "numeric-compared-to-text": _ARGUMENT,
    "mapping-key-of-another-type": _ARGUMENT,
    "mapping-value-of-another-type": _ARGUMENT,
    "numeric-range-of-text": _ARGUMENT,
    "exact-items-of-another-type": _ARGUMENT,
    "collection-subset-of-text": _ARGUMENT,
    "date-compared-to-number": _ARGUMENT,
    "ordered-but-not-convertible": _ARGUMENT,
    "length-given-text": _ARGUMENT,
    "bytes-prefixed-with-text": _ARGUMENT,
    # a matcher for another type: ty reads it as no overload matching, the others as a bad argument
    "matcher-for-another-type": {
        "ty": frozenset({"no-matching-overload"}),
        "mypy": frozenset({"arg-type"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
    },
    # the four membership and ordering matchers judge a collection, so a scalar is the wrong subject for
    # them. Recorded separately from the text matcher above because they were added later and their
    # binding is the new part: without it they would have resolved to `Matcher[Any]` and matched anything
    "membership-matcher-for-a-scalar": {
        "ty": frozenset({"no-matching-overload"}),
        "mypy": frozenset({"arg-type"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
    },
    "only-matcher-for-a-scalar": {
        "ty": frozenset({"no-matching-overload"}),
        "mypy": frozenset({"arg-type"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
    },
    "subset-matcher-for-a-scalar": {
        "ty": frozenset({"no-matching-overload"}),
        "mypy": frozenset({"arg-type"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
    },
    "sorted-matcher-for-a-scalar": {
        "ty": frozenset({"no-matching-overload"}),
        "mypy": frozenset({"arg-type"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
    },
    # --- the method is not on this value's protocol ------------------------------------------------
    "complex-ordered": _MISSING,
    "complex-signed": _MISSING,
    "complex-nan": _MISSING,
    "bool-parity": _MISSING,
    "bool-divisibility": _MISSING,
    "numeric-assertion-on-text": _MISSING,
    "dynamic-attribute-on-a-mapping": _MISSING,
    # --- a step hands back `Self`, so the narrowing holds for the whole chain ----------------------
    "complex-widened-by-chaining": _MISSING,
    "bool-widened-by-chaining": _MISSING,
    # --- still open, both for the same reason: a surface reached through `__getattr__` -------------
    # the generic builder carries every method there is, and `.not_` resolves any name through a proxy
    "numeric-assertion-on-an-object": {},
    "negation-widens-the-protocol": {},
    # --- and the third: `SupportsFloat` is wider than the runtime's `numbers.Number` ----------------
    # both are refused at runtime by name, which is the tolerable direction for an approximation to err
    "convertible-but-not-a-number": {},
    "array-as-a-scalar-operand": {},
}

VALID: frozenset[str] = frozenset(
    {
        "valid-contains-an-item",
        "valid-contains-a-matcher",
        "valid-int-compared-to-float",
        "valid-mapping-key",
        "valid-substring",
        "valid-bytes-prefix",
        "valid-predicate",
        "valid-length",
        "valid-date-order",
        "valid-dynamic-attribute",
        "valid-int-against-float",
        "valid-float-against-int",
        "valid-decimal-order",
        "valid-fraction-order",
        "valid-complex-zero",
        "valid-bool-compared",
        "valid-int-equals-bool",
        "valid-complex-equality",
        "valid-complex-instance",
        "valid-complex-predicate",
        "valid-bool-truth",
        "valid-membership-matcher",
        "valid-membership-matcher-of-text",
        "valid-membership-matcher-on-mapping",
        "valid-only-matcher",
        "valid-subset-from-collection",
        "valid-subset-from-items",
        "valid-sorted-matcher",
        "valid-sorted-by-key",
        "valid-equal-to-tolerance",
        "valid-equal-to-ignore",
        "valid-membership-in-a-union-collection",
        "valid-membership-in-a-wide-collection",
        "valid-membership-of-a-subclass",
        "valid-subset-of-a-wide-collection",
        "valid-only-in-a-union-collection",
        "valid-numpy-integer",
        "valid-numpy-float",
        "valid-numpy-tolerance",
        "valid-numpy-int32",
        "valid-numpy-uint64",
        "valid-numpy-float32",
        "valid-typed-dict-key",
        "valid-mapping-protocol-key",
        "valid-counter-key",
        "valid-enum-key",
        "valid-union-element",
        "valid-heterogeneous-tuple",
        "valid-set-member",
        "valid-nested-payload",
        "valid-list-subclass",
        "valid-any-element",
        "valid-datetime-against-datetime",
        "valid-date-from-datetime",
    }
)
"""Ordinary usage, which must stay accepted by all three.

A checker rejecting one of these is a defect in the typing, not a win.  They are the half of the
measurement that decides whether a tightened signature can ship: `contains` has to keep taking a
matcher, comparing an `int` against a `float` has to keep working, and a `Decimal` has to keep ordering
against a `Decimal`.
"""
