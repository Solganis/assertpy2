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

**What stays uncaught, and why.** A value with no protocol of its own now gets the core surface, so
`assert_that(Person()).is_positive()` is refused by all four.  What is left is the ordering matchers,
which take and judge anything, and the entries below say why every spelling that closes that trades a
correct call for an incorrect one.

`.not_` used to belong here for the same reason as the first: it returns a proxy resolving any name.
It is declared as the protocol it was reached from instead, which costs nothing, and what remains is
the other direction: the fourteen names the proxy refuses at runtime are still spelled as available.

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
    "pyrefly": frozenset({"bad-argument-type"}),
}

_CLASS_INFO_MEMBER: dict[str, frozenset[str]] = {
    "ty": frozenset({"no-matching-overload"}),
    "mypy": frozenset({"arg-type"}),
    "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
    "pyrefly": frozenset({"no-matching-overload"}),
}

_MISSING: dict[str, frozenset[str]] = {
    "ty": frozenset({"unresolved-attribute"}),
    "mypy": frozenset({"attr-defined"}),
    "pyright": frozenset({"reportAttributeAccessIssue"}),
    "pyrefly": frozenset({"missing-attribute"}),
}

_NOT_THE_VALUES_VIEW: dict[str, frozenset[str]] = {
    "ty": frozenset(),
    "mypy": frozenset({"misc"}),
    "pyright": frozenset({"reportAttributeAccessIssue"}),
    "pyrefly": frozenset({"no-matching-overload"}),
}

_NOT_THE_VALUES_KIND: dict[str, frozenset[str]] = {
    "ty": frozenset({"invalid-argument-type"}),
    "mypy": frozenset({"misc"}),
    "pyright": frozenset({"reportAttributeAccessIssue"}),
    "pyrefly": frozenset({"bad-argument-type"}),
}

_NOT_THE_CHAINS_VALUE: dict[str, frozenset[str]] = {
    "ty": frozenset({"no-matching-overload"}),
    "mypy": frozenset({"misc"}),
    "pyright": frozenset({"reportAttributeAccessIssue"}),
    "pyrefly": frozenset({"no-matching-overload"}),
}

_PREDICATE_OVER_THE_SUBJECT: dict[str, frozenset[str]] = {
    "ty": frozenset(),
    "mypy": frozenset({"arg-type"}),
    "pyright": frozenset({"reportAttributeAccessIssue"}),
    "pyrefly": frozenset({"missing-attribute"}),
}

_NO_EXPECTATION_YET: dict[str, frozenset[str]] = {
    "ty": frozenset({"call-non-callable"}),
    "mypy": frozenset(),
    "pyright": frozenset({"reportCallIssue"}),
    "pyrefly": frozenset({"not-callable"}),
}

_NOT_CALLABLE: dict[str, frozenset[str]] = {
    "ty": frozenset({"call-non-callable"}),
    "mypy": frozenset({"operator"}),
    "pyright": frozenset({"reportCallIssue"}),
    "pyrefly": frozenset({"not-callable"}),
}

CAUGHT: dict[str, dict[str, frozenset[str]]] = {
    "contains-item-of-another-type": _ARGUMENT,
    "numeric-compared-to-text": _ARGUMENT,
    "mapping-key-of-another-type": _ARGUMENT,
    "mapping-value-of-another-type": _ARGUMENT,
    "numeric-range-of-text": _ARGUMENT,
    "exact-items-of-another-type": _ARGUMENT,
    # each view says what a superset is for it: characters, a mapping, byte values
    "mapping-subset-of-a-sequence": _ARGUMENT,
    # the chronological nine live on the datetime view, so a bad operand became a method the value has not got
    "zip-reads-the-wrong-side": _MISSING,
    "date-compared-to-number": _MISSING,
    "date-ordered-as-a-datetime": _MISSING,
    "date-taken-from-a-datetime": _MISSING,
    "ordered-but-not-convertible": _ARGUMENT,
    "length-given-text": _ARGUMENT,
    "bytes-prefixed-with-text": _ARGUMENT,
    # a matcher for another type: ty reads it as no overload matching, the others as a bad argument
    "matcher-for-another-type": {
        "ty": frozenset({"no-matching-overload"}),
        "mypy": frozenset({"arg-type"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
        "pyrefly": frozenset({"no-matching-overload"}),
    },
    # the four membership and ordering matchers judge a collection, so a scalar is the wrong subject. Kept
    # apart from the text matcher because their binding is the new part: without it, `Matcher[Any]`
    "membership-matcher-for-a-scalar": {
        "ty": frozenset({"no-matching-overload"}),
        "mypy": frozenset({"arg-type"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
        "pyrefly": frozenset({"no-matching-overload"}),
    },
    "only-matcher-for-a-scalar": {
        "ty": frozenset({"no-matching-overload"}),
        "mypy": frozenset({"arg-type"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
        "pyrefly": frozenset({"no-matching-overload"}),
    },
    "subset-matcher-for-a-scalar": {
        "ty": frozenset({"no-matching-overload"}),
        "mypy": frozenset({"arg-type"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
        "pyrefly": frozenset({"no-matching-overload"}),
    },
    "sorted-matcher-for-a-scalar": {
        "ty": frozenset({"no-matching-overload"}),
        "mypy": frozenset({"arg-type"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
        "pyrefly": frozenset({"no-matching-overload"}),
    },
    "repeats-of-a-wider-element-substituted": _ARGUMENT,
    "numeric-assertion-after-a-json-path": _MISSING,
    "mapping-assertion-after-a-json-path": _MISSING,
    "membership-assertion-after-a-json-path": _MISSING,
    "reading-a-json-path-value-as-a-type": _MISSING,
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
        "pyrefly": frozenset({"bad-argument-count"}),
    },
    "extracting-with-an-unknown-option": {
        "ty": frozenset({"unknown-argument"}),
        "mypy": frozenset({"call-arg"}),
        "pyright": frozenset({"reportCallIssue"}),
        "pyrefly": frozenset({"unexpected-keyword"}),
    },
    # mypy adds `misc` beside `arg-type` to say the lambda itself does not fit, not only its result
    "extracting-filter-of-wrong-arity": {
        "ty": frozenset({"invalid-argument-type"}),
        "mypy": frozenset({"arg-type", "misc"}),
        "pyright": frozenset({"reportArgumentType"}),
        "pyrefly": frozenset({"bad-argument-type"}),
    },
    # the arity, not the verdict: `sort` and `filter` hand over one item, so a two-parameter callable is refused
    "extracting-sort-of-wrong-arity": {
        "ty": frozenset({"invalid-argument-type"}),
        "mypy": frozenset({"arg-type", "misc"}),
        "pyright": frozenset({"reportArgumentType"}),
        "pyrefly": frozenset({"bad-argument-type"}),
    },
    "complex-ordered": _MISSING,
    "complex-signed": _MISSING,
    "complex-nan": _MISSING,
    "bool-parity": _MISSING,
    "bool-divisibility": _MISSING,
    "numeric-assertion-on-text": _MISSING,
    # the same four through `check()`, which answered every one with a callable: its `__getattr__` typed any
    # name as available, so a typo was invisible. Each view now hands back its own verdict twin
    "text-assertion-on-a-number-through-check": _MISSING,
    "numeric-assertion-on-text-through-check": _MISSING,
    "mapping-assertion-on-a-list-through-check": _MISSING,
    "a-name-that-exists-nowhere-through-check": _MISSING,
    "dynamic-attribute-on-a-mapping": _MISSING,
    "complex-widened-by-chaining": _MISSING,
    "bool-widened-by-chaining": _MISSING,
    # `.not_` is the protocol it was reached from, so what it still allows is the non-negatable names
    "negation-widens-the-protocol": _MISSING,
    "numeric-assertion-on-an-object": _MISSING,
    # the hook lives on the builder, so the narrowing takes `has_<attr>` off a plain class. Deliberate, and
    # the docs guard has carried a marker for it since before: a dynamic assertion is outside the typed surface
    "dynamic-attribute-on-an-object": _MISSING,
    # the umbrella's own protocol asks the value for an ordering; both used to type-check and raise `TypeError`
    "numeric-assertion-on-a-capable-value": _NOT_THE_VALUES_KIND,
    # the object fallback carries four of the numeric assertions, so a value that converts neither way is
    # refused, and so is the family behind `numbers.Real`, which no structural key can name
    "conversion-assertion-on-an-object": _NOT_THE_VALUES_KIND,
    "real-only-assertion-on-a-registered-number": _MISSING,
    "numeric-assertion-on-a-polled-capable-value": _NOT_THE_CHAINS_VALUE,
    # the five numeric assertions for which `float()` is necessary, measured; the other five stay open
    "nan-assertion-on-a-capable-value": _NOT_THE_VALUES_KIND,
    # the dict family split three ways: keys and the walk, plus a lookup for entries, plus values
    "key-assertion-on-a-value-with-no-keys": _NOT_THE_VALUES_KIND,
    "entry-assertion-on-a-value-with-no-keys": _NOT_THE_VALUES_KIND,
    "value-assertion-on-a-value-with-no-values": _NOT_THE_VALUES_KIND,
    "closeness-assertion-on-a-capable-value": _NOT_THE_VALUES_KIND,
    "nan-assertion-on-a-polled-capable-value": _NOT_THE_CHAINS_VALUE,
    # a polling chain: the declaration wins over `__getattr__`, which is what makes a typed chain worth having
    "text-assertion-on-a-polled-number": _NOT_THE_CHAINS_VALUE,
    # ty reads a chain over an `async def` probe as `Unknown`, measured, and so refuses nothing on it
    "text-assertion-on-an-async-probe": {**_NOT_THE_CHAINS_VALUE, "ty": frozenset()},
    # the same rung from the other end: no capability matches neither, so the core narrowing follows onto the chain
    "numeric-assertion-on-a-polled-object": _NOT_THE_CHAINS_VALUE,
    # the view binds the predicate to its own value, so a lambda reading a missing name is refused. ty
    # resolves the parameter through an overload set less precisely and says nothing, measured here
    "predicate-reading-a-missing-string-method": _PREDICATE_OVER_THE_SUBJECT,
    "predicate-reading-a-missing-numeric-method": _PREDICATE_OVER_THE_SUBJECT,
    "text-verdict-on-a-pivoted-number": _NOT_THE_VALUES_VIEW,
    "text-assertion-after-a-dynamic-one": _NOT_THE_CHAINS_VALUE,
    # ty was silent on both until 0.0.82, which reads a recursive alias to every depth
    "a-tuple-member-that-is-not-a-class": _CLASS_INFO_MEMBER,
    "a-nested-member-that-is-not-a-class": _CLASS_INFO_MEMBER,
    # narrowing `is_close_to` on `self` moved this from a bad argument to no rung matching: an `int` fits
    # both rungs and `"x"` fits neither, where the wide rung used to take the receiver and refuse the operand
    "bad-operand-on-a-polled-number": {
        "ty": frozenset({"no-matching-overload"}),
        "mypy": frozenset({"call-overload"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
        "pyrefly": frozenset({"no-matching-overload"}),
    },
    "wrong-element-after-a-polled-pivot": {
        "ty": frozenset({"no-matching-overload"}),
        "mypy": frozenset({"call-overload"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
        "pyrefly": frozenset({"no-matching-overload"}),
    },
    # the negation twins carry only what reaches a verdict, so the fourteen names that transform,
    # configure or describe are now refused statically as well as at run time
    "negation-allows-a-non-negatable-name": {
        "ty": frozenset({"unresolved-attribute"}),
        "mypy": frozenset({"attr-defined"}),
        "pyright": frozenset({"reportAttributeAccessIssue"}),
        "pyrefly": frozenset({"missing-attribute"}),
    },
    "umbrella-negation-allows-a-non-negatable-name": {
        "ty": frozenset({"unresolved-attribute"}),
        "mypy": frozenset({"attr-defined"}),
        "pyright": frozenset({"reportAttributeAccessIssue"}),
        "pyrefly": frozenset({"missing-attribute"}),
    },
    "negated-element-of-another-type": _ARGUMENT,
    # the hook has to stay: `has_status("PAID")` can be declared nowhere. With it there an unknown name is
    # the runtime's to name, and a `str` reaches the umbrella rung of an assertion the string view lacks
    "a-name-that-exists-nowhere-on-a-chain": {},
    "numeric-assertion-on-polled-text": {},
    "text-assertion-on-a-polled-mapping": {},
    "json-pivot-on-polled-bytes": {},
    "called-with-on-a-chain-over-a-number": _NOT_CALLABLE,
    # mypy alone is silent: it reads `assert_that()` over a probe that returns a callable as `Any`, so
    # there is no chain for it to refuse the name on.  The other three read the declared refusal
    "called-with-on-a-chain-over-a-callable": _NO_EXPECTATION_YET,
    "called-with-on-an-async-chain": _NO_EXPECTATION_YET,
    # declared as a member with a type nothing can call, which is what beats `__getattr__`
    "value-on-a-sync-poll": _MISSING,
    "value-on-an-async-poll": _MISSING,
    "check-on-a-sync-poll": _NOT_CALLABLE,
    "check-on-an-async-poll": _NOT_CALLABLE,
    "describe-on-a-negated-poll": _NOT_CALLABLE,
    "pivot-on-a-negated-poll": _NOT_CALLABLE,
    "expectation-on-a-negated-poll": _NOT_CALLABLE,
    "poll-on-a-sync-poll": _NOT_THE_CHAINS_VALUE,
    "poll-on-an-async-poll": _NOT_THE_CHAINS_VALUE,
    # the call ladder: the expectation views carry `when_called_with()`, and each landing carries what
    # the run time lets it be asked.  All four checkers read a missing declaration the same way
    "called-with-no-expectation": _MISSING,
    # the facade answers a name it lacks through `__getattr__`, so the refusal is declared instead
    "called-with-no-expectation-on-a-capable-callable": _NOT_CALLABLE,
    "returned-after-raises": _MISSING,
    "raised-after-no-raise": _MISSING,
    "raised-after-warns": _MISSING,
    "caused-by-after-warns": _MISSING,
    "errors-after-warns": _MISSING,
    "text-after-no-raise": _MISSING,
    "contains-after-no-warn": _MISSING,
    # the rung the chain reaches for a text probe now carries `str` operands rather than a free element,
    # so two of the three refuse the number.  ty and pyrefly still bind the element off the argument
    "element-of-another-type-on-a-polled-string": {
        "ty": frozenset(),
        "mypy": frozenset({"call-overload"}),
        "pyright": frozenset({"reportArgumentType", "reportCallIssue"}),
        "pyrefly": frozenset(),
    },
    "ordering-matcher-takes-any-boundary": {},
    "ordering-matcher-judges-any-subject": {},
    "convertible-but-not-a-number": {},
    "array-as-a-scalar-operand": {},
}

SPLIT: frozenset[str] = frozenset(
    {
        "predicate-reading-a-missing-string-method",
        "predicate-reading-a-missing-numeric-method",
        "called-with-on-a-chain-over-a-callable",
        "called-with-on-an-async-chain",
        "text-verdict-on-a-pivoted-number",
        "element-of-another-type-on-a-polled-string",
        "text-assertion-on-an-async-probe",
    }
)
"""The cases the four do not agree on, named so a new one has to be decided about.

Seven relations.  ty is silent in five.  The two predicates are a lambda over the subject reading a
name the value has not got, where ty resolves the parameter through the overload set less precisely.
The pivoted number is a verdict asked of a value the builder holds, refused through the ``self``
annotation of a rung on its twin, which ty does not read.  The polled string is handed an element of
another type, where the rung that matches carries `str` operands and only mypy and pyright say so.  The
async probe is a chain ty reads as `Unknown`.  In the two `when_called_with()` calls made before any
expectation, mypy is the silent one.

Each row records that silence as an empty set of codes rather than by leaving the checker out, since a
missing checker would read as the dialects agreeing.
"""

VALID: frozenset[str] = frozenset(
    {
        "valid-call-after-an-expectation",
        "valid-async-call-after-an-expectation",
        "valid-verdict-after-a-pivot",
        "valid-text-verdict-after-a-pivot",
        "valid-verdict-after-a-loose-pivot",
        "valid-predicate-over-the-subject",
        "valid-numeric-predicate-over-the-subject",
        "valid-polled-refinement",
        "valid-polled-pivot",
        "valid-poll-over-an-async-probe",
        "valid-polled-dynamic-then-typed",
        "valid-polled-dynamic-on-an-object",
        "valid-polled-capable-callable",
        "valid-call-on-a-capable-callable",
        "valid-builder-pivot-off-the-umbrella",
        "valid-contains-an-item",
        "valid-contains-a-matcher",
        "valid-int-compared-to-float",
        "valid-mapping-key",
        "valid-substring",
        "valid-bytes-prefix",
        "valid-predicate",
        "valid-length",
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
        # a value the umbrella claims that converts, which is what the float restriction must not refuse
        "valid-capable-nan",
        "valid-capable-key",
        "valid-capable-entry",
        "valid-capable-value",
        "valid-capable-closeness",
        # and the object fallback's half: a registered number no overload names
        "valid-fraction-closeness",
        "valid-decimal-closeness",
        "valid-decimal-zero",
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
    }
)
"""Ordinary usage, which must stay accepted by all four.

A checker rejecting one of these is a defect in the typing, not a win.  They are the half of the
measurement that decides whether a tightened signature can ship: `contains` has to keep taking a
matcher, comparing an `int` against a `float` has to keep working, and a `Decimal` has to keep ordering
against a `Decimal`.
"""
