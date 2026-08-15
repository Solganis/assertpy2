"""Which checkers reject which relation in `typing_cases.py`, and with which diagnostic, as measured.

Read by `test_typing_negative.py`, which fails on any difference in either direction.  A case that
starts being caught is as much a change as one that stops: the first says a signature was tightened,
the second says one was loosened by accident.

**The diagnostic code is part of the record, not decoration.** An earlier version stored only "these
checkers rejected it", and a counter-example whose fixture lacked an import reported an undefined name
rather than a type error: green, and the relation it existed for was never checked.

The rejections fall into families, and the split is the useful reading: the argument does not fit
(`invalid-argument-type` / `arg-type` / `reportArgumentType`), the method is not there
(`unresolved-attribute` / `attr-defined` / `reportAttributeAccessIssue`), the keyword does not exist,
and the argument is missing.  `ty` sometimes answers `no-matching-overload` where the others name the
argument: same family, different route through an overload set.

**What stays uncaught, and why.** `assert_that(Person()).is_positive()` type-checks, because a value
with no protocol of its own gets the generic builder, which carries every method there is.  `.not_`
returns a proxy resolving any name, so the negated branch accepts what the protocol refuses.  Closing
the second means a second protocol per type, doubling the typed surface for one inverted call.

**The trap this file exists to catch.** A numeric comparison is bound to `SupportsFloat` rather than to
a list of types: the first attempt named `float | Decimal | Fraction` and rejected `numpy.int64`, a
false rejection on a library this project documents support for.  A capability covers what a list of
types cannot, and the valid half of this file is what went red to say so.
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
    # each view says what a superset is for it: characters, a mapping, byte values
    "mapping-subset-of-a-sequence": _ARGUMENT,
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
    # --- a type parameter substituted by a wider one -----------------------------------------------
    # the element of `_RepeatableAssertion` is invariant on purpose, and this line is what that buys.
    # Declaring it contravariant, which pyright suggests and `pyright_baseline.py` records as refused,
    # makes this substitution legal in both pyright and mypy, and a matcher for the narrower element
    # then reaches an assertion over the wider one
    "repeats-of-a-wider-element-substituted": _ARGUMENT,
    # --- the shape at a json path is unknowable statically, so the view carries no shape -----------
    # each of these used to type-check and raise at runtime, which is the pairing this file exists for
    "numeric-assertion-after-a-json-path": _MISSING,
    "mapping-assertion-after-a-json-path": _MISSING,
    "membership-assertion-after-a-json-path": _MISSING,
    "reading-a-json-path-value-as-a-type": _MISSING,
    # --- the two extraction mistakes the runtime refuses by name, refused before the run now -------
    # the verdict is `object`, but the input is the element: a predicate may only ask the element what
    # the element has
    "predicate-reading-a-field-the-element-lacks": _MISSING,
    "mapping-predicate-reading-a-missing-field": _MISSING,
    "quantifier-reading-a-missing-field": _MISSING,
    "byte-predicate-reading-a-missing-field": _MISSING,
    "each-reading-a-missing-field": _MISSING,
    "all-satisfy-reading-a-missing-field": _MISSING,
    "extracting-with-no-selector": {
        "ty": frozenset({"missing-argument"}),
        "mypy": frozenset({"call-arg"}),
        "pyright": frozenset({"reportCallIssue"}),
    },
    "extracting-with-an-unknown-option": {
        "ty": frozenset({"unknown-argument"}),
        "mypy": frozenset({"call-arg"}),
        "pyright": frozenset({"reportCallIssue"}),
    },
    # mypy adds `misc` beside `arg-type` on a callable of the wrong arity, which is its way of saying
    # the lambda itself does not fit rather than only its result
    "extracting-filter-of-wrong-arity": {
        "ty": frozenset({"invalid-argument-type"}),
        "mypy": frozenset({"arg-type", "misc"}),
        "pyright": frozenset({"reportArgumentType"}),
    },
    # the arity, not the verdict: `sort` and `filter` are handed one item each, so a two-parameter
    # callable is refused before the run rather than during it
    "extracting-sort-of-wrong-arity": {
        "ty": frozenset({"invalid-argument-type"}),
        "mypy": frozenset({"arg-type", "misc"}),
        "pyright": frozenset({"reportArgumentType"}),
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
        "valid-subset-of-loose-items",
        "valid-subset-of-characters",
        "valid-subset-of-a-mapping",
        "valid-subset-of-byte-values",
        "valid-subset-of-text-items",
        "valid-subset-of-a-wider-number",
        "valid-subset-of-mixed-items",
        "valid-sorted-matcher",
        "valid-sorted-by-key",
        "valid-equal-to-tolerance",
        "valid-equal-to-ignore",
        "valid-membership-in-a-union-collection",
        "valid-membership-in-a-wide-collection",
        "valid-membership-of-a-subclass",
        "valid-repeats-of-the-exact-element",
        "valid-equality-after-a-json-path",
        "valid-narrowed-json-path",
        "valid-matcher-after-json-path",
        "valid-extracting-one-name",
        "valid-extracting-several-names",
        "valid-extracting-filter-by-key",
        "valid-extracting-filter-by-mapping",
        "valid-extracting-filter-callable",
        "valid-extracting-sort-by-key",
        "valid-extracting-sort-by-keys",
        "valid-extracting-sort-callable",
        "valid-extracting-filter-and-sort",
        "valid-extracting-filter-from-a-variable",
        "valid-extracting-filter-from-a-mapping",
        "valid-extracting-a-slice",
        "valid-filter-option-verdict-not-a-bool",
        "valid-quantifier-predicate-returning-an-int",
        "valid-filter-predicate-returning-an-int",
        "valid-quantifier-predicate-returning-a-numpy-bool",
        "valid-extracting-an-unhashable-selector",
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
