"""What a polling chain declares over a value beyond that value's own view, and why it reaches it.

Read by `test_poll_parity.py`, which fails on any difference in either direction.  A name appearing is
a new leak; a name disappearing means one was closed, and the record has to say so.

Every entry is a call the chain type-checks and the same value's own view refuses.  Whether it also
raises when it runs is not measured here: `is_positive()` on a string does, and `starts_with` on a
mapping does not, since it accepts any iterable.  They are not defects of one assertion but of one
shape.  Overload resolution cannot say "only if no earlier rung matched", so a chain reaches every rung
whose receiver it satisfies: a `str` reaches the ordering rung by ordering and the open rung by being
a value the umbrella claims.  The generator's header records the three shapes measured against this question and
why the flat protocol is the one that ships.

`is_positive()` on a polled string was the first of these noticed.  It is one of eighteen for text,
thirty for a mapping, thirty-eight for bytes, and seventy for a frame carrying every capability.
"""

from __future__ import annotations

WITNESSED_BY: dict[str, tuple[str, ...]] = {
    "str": ("str",),
    "bool": ("bool",),
    "int": ("int",),
    "float": ("float",),
    "complex": ("complex",),
    "dict[_K, _V]": ("dict[str, int]",),
    "list[_E] | tuple[_E, ...]": (
        "list[int]",
        "tuple[int, ...]",
    ),
    "set[_E] | frozenset[_E]": (
        "set[int]",
        "frozenset[int]",
    ),
    "datetime.datetime": ("datetime.datetime",),
    "datetime.date": ("datetime.date",),
    "pathlib.Path": ("pathlib.Path",),
    "bytes": ("bytes",),
    "bytearray": ("bytearray",),
    "_FrameT_co": (
        "_FrameShaped",
        "_FrameThatWalks",
        "_FrameCarryingEverything",
    ),
    "_ArrayT_co": (
        "_ArrayShaped",
        "_ArrayThatWalks",
        "_ArrayCarryingEverything",
    ),
    "Callable[..., _P]": ("Callable[..., int]",),
    "_T": ("object",),
}
"""The concrete types each dispatched value is asked about as, in `poll_parity_cases.py`.

A spelling cannot always be handed to a checker as it stands, and one member is no witness for the
others: a `tuple` reaches the rung written for tuples and not the one written for lists, so both are
asked.  The two named by a bound get three witnesses each, and the spread is the point: a frame
reaches seven names its view lacks carrying only the bound, forty-three also walking, and seventy
carrying every capability any receiver asks about.  A real pandas frame sits inside that bracket,
which is why both ends are recorded rather than one library's answer.
"""

DISPATCHES_TO: dict[str, str] = {
    "str": "_StringAssertion",
    "bool": "_BoolAssertion",
    "int": "_NumericAssertion",
    "float": "_NumericAssertion",
    "complex": "_ComplexAssertion",
    "dict[str, int]": "_DictAssertion",
    "list[int]": "_IterableAssertion",
    "tuple[int, ...]": "_IterableAssertion",
    "set[int]": "_IterableAssertion",
    "frozenset[int]": "_IterableAssertion",
    "datetime.datetime": "_DateTimeAssertion",
    "datetime.date": "_DateAssertion",
    "pathlib.Path": "_PathAssertion",
    "bytes": "_BytesAssertion",
    "bytearray": "_BytesAssertion",
    "_FrameShaped": "_FrameAssertion",
    "_FrameThatWalks": "_FrameAssertion",
    "_FrameCarryingEverything": "_FrameAssertion",
    "_ArrayShaped": "_ArrayAssertion",
    "_ArrayThatWalks": "_ArrayAssertion",
    "_ArrayCarryingEverything": "_ArrayAssertion",
    "Callable[..., int]": "_CallableAssertion",
    "object": "_ObjectAssertion",
}
"""The view `assert_that()` hands each witness, derived again in `test_poll_parity.py` from the
overloads rather than trusted from here."""

REACHES: dict[str, frozenset[str]] = {
    "str": frozenset(
        {
            "Iterable[_E]",
            "_CapableT",
            "_Indexed[_E]",
            "_Orderable",
            "_T",
            "_U",
            "str",
        }
    ),
    "bool": frozenset(
        {
            "SupportsFloat",
            "SupportsIndex",
            "_Orderable",
            "_T",
            "_U",
            "bool",
            "complex",
            "float",
            "int",
        }
    ),
    "int": frozenset(
        {
            "SupportsFloat",
            "SupportsIndex",
            "_Orderable",
            "_T",
            "_U",
            "complex",
            "float",
            "int",
        }
    ),
    "float": frozenset(
        {
            "SupportsFloat",
            "_Orderable",
            "_T",
            "_U",
            "complex",
            "float",
        }
    ),
    "complex": frozenset(
        {
            "_T",
            "_U",
            "complex",
        }
    ),
    "dict[str, int]": frozenset(
        {
            "Iterable[_E]",
            "_CapableT",
            "_Keyed",
            "_KeyedWithItems",
            "_KeyedWithValues",
            "_T",
            "_U",
            "dict[_K, _V]",
        }
    ),
    "list[int]": frozenset(
        {
            "Iterable[_E]",
            "_CapableT",
            "_Indexed[_E]",
            "_Orderable",
            "_T",
            "_U",
            "list[_E]",
        }
    ),
    "tuple[int, ...]": frozenset(
        {
            "Iterable[_E]",
            "_CapableT",
            "_Indexed[_E]",
            "_Orderable",
            "_T",
            "_U",
            "tuple[_E, ...]",
        }
    ),
    "set[int]": frozenset(
        {
            "Iterable[_E]",
            "_CapableT",
            "_Orderable",
            "_T",
            "_U",
            "set[_E]",
        }
    ),
    "frozenset[int]": frozenset(
        {
            "Iterable[_E]",
            "_CapableT",
            "_Orderable",
            "_T",
            "_U",
            "frozenset[_E]",
        }
    ),
    "datetime.datetime": frozenset(
        {
            "_Orderable",
            "_T",
            "_U",
            "datetime.date",
            "datetime.datetime",
        }
    ),
    "datetime.date": frozenset(
        {
            "_Orderable",
            "_T",
            "_U",
            "datetime.date",
        }
    ),
    "pathlib.Path": frozenset(
        {
            "Path",
            "_Orderable",
            "_PathLike",
            "_T",
            "_U",
            "pathlib.Path",
        }
    ),
    "bytes": frozenset(
        {
            "Iterable[_E]",
            "_CapableT",
            "_Indexed[_E]",
            "_Orderable",
            "_T",
            "_U",
            "bytes",
        }
    ),
    "bytearray": frozenset(
        {
            "Iterable[_E]",
            "_CapableT",
            "_Indexed[_E]",
            "_Orderable",
            "_T",
            "_U",
            "bytearray",
        }
    ),
    "_FrameShaped": frozenset(
        {
            "_FrameT_co",
            "_T",
            "_U",
        }
    ),
    "_FrameThatWalks": frozenset(
        {
            "Iterable[_E]",
            "_CapableT",
            "_FrameT_co",
            "_T",
            "_U",
        }
    ),
    "_FrameCarryingEverything": frozenset(
        {
            "Callable[..., _P]",
            "Callable[..., object]",
            "Iterable[_E]",
            "SupportsFloat",
            "SupportsIndex",
            "_Callable",
            "_CapableT",
            "_FrameT_co",
            "_Indexed[_E]",
            "_Keyed",
            "_KeyedWithItems",
            "_KeyedWithValues",
            "_Orderable",
            "_PathLike",
            "_T",
            "_U",
        }
    ),
    "_ArrayShaped": frozenset(
        {
            "_ArrayT_co",
            "_T",
            "_U",
        }
    ),
    "_ArrayThatWalks": frozenset(
        {
            "Iterable[_E]",
            "_ArrayT_co",
            "_CapableT",
            "_T",
            "_U",
        }
    ),
    "_ArrayCarryingEverything": frozenset(
        {
            "Callable[..., _P]",
            "Callable[..., object]",
            "Iterable[_E]",
            "SupportsFloat",
            "SupportsIndex",
            "_ArrayT_co",
            "_Callable",
            "_CapableT",
            "_Indexed[_E]",
            "_Keyed",
            "_KeyedWithItems",
            "_KeyedWithValues",
            "_Orderable",
            "_PathLike",
            "_T",
            "_U",
        }
    ),
    "Callable[..., int]": frozenset(
        {
            "Callable[..., _P]",
            "Callable[..., object]",
            "_Callable",
            "_T",
            "_U",
        }
    ),
    "object": frozenset(
        {
            "_T",
            "_U",
        }
    ),
}
"""Which receiver arms a chain over each witness reaches, measured with pyright.

Not reasoned about, and the reasoning was wrong twice before it was measured: the chain is covariant
in what it polls, so a rung named for a value is not reachable by that value alone.  `bool` reaches
the three rungs written for `int`, and a `datetime` reaches those written for `date`.

`test_poll_parity.py` re-derives this from `poll_parity_cases.py` wherever pyright is installed, and
holds that file to the whole grid, so an arm nobody measured cannot quietly contribute nothing.
"""

RECORDED: dict[str, frozenset[str]] = {
    "str": frozenset(
        {
            "at_json_path",
            "conforms_to_openapi",
            "does_not_have_json_path",
            "extracting",
            "has_json_path",
            "is_array_close_to",
            "is_array_equal",
            "is_between",
            "is_frame_equal",
            "is_negative",
            "is_not_between",
            "is_not_close_to",
            "is_not_zero",
            "is_positive",
            "is_zero",
            "matches_json_schema",
            "matches_json_schema_from_file",
            "matches_structure",
        }
    ),
    "bool": frozenset(
        {
            "is_divisible_by",
            "is_even",
            "is_odd",
            "matches_structure",
        }
    ),
    "int": frozenset(
        {
            "matches_structure",
        }
    ),
    "float": frozenset(
        {
            "matches_structure",
        }
    ),
    "complex": frozenset(
        {
            "is_between",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_not_between",
            "matches_structure",
        }
    ),
    "dict[str, int]": frozenset(
        {
            "any_satisfy",
            "contains_any_of",
            "contains_duplicates",
            "contains_exactly",
            "contains_exactly_in_any_order",
            "contains_ignoring_case",
            "contains_in_order",
            "contains_none_of",
            "contains_only_once",
            "contains_sequence",
            "does_not_contain_duplicates",
            "ends_with",
            "is_array_close_to",
            "is_array_equal",
            "is_between",
            "is_frame_equal",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_not_between",
            "is_not_close_to",
            "is_not_zero",
            "is_unicode",
            "is_zero",
            "none_satisfy",
            "satisfies_exactly",
            "satisfies_exactly_in_any_order",
            "starts_with",
            "zip_satisfies",
        }
    ),
    "list[int]": frozenset(
        {
            "contains_any_of",
            "contains_ignoring_case",
            "contains_none_of",
            "is_array_close_to",
            "is_array_equal",
            "is_between",
            "is_frame_equal",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_negative",
            "is_not_between",
            "is_not_close_to",
            "is_not_zero",
            "is_positive",
            "is_unicode",
            "is_zero",
            "matches_structure",
        }
    ),
    "tuple[int, ...]": frozenset(
        {
            "contains_any_of",
            "contains_ignoring_case",
            "contains_none_of",
            "is_array_close_to",
            "is_array_equal",
            "is_between",
            "is_frame_equal",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_negative",
            "is_not_between",
            "is_not_close_to",
            "is_not_zero",
            "is_positive",
            "is_unicode",
            "is_zero",
            "matches_structure",
        }
    ),
    "set[int]": frozenset(
        {
            "contains_any_of",
            "contains_ignoring_case",
            "contains_none_of",
            "is_array_close_to",
            "is_array_equal",
            "is_between",
            "is_frame_equal",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_negative",
            "is_not_between",
            "is_not_close_to",
            "is_not_zero",
            "is_positive",
            "is_unicode",
            "is_zero",
            "matches_structure",
        }
    ),
    "frozenset[int]": frozenset(
        {
            "contains_any_of",
            "contains_ignoring_case",
            "contains_none_of",
            "is_array_close_to",
            "is_array_equal",
            "is_between",
            "is_frame_equal",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_negative",
            "is_not_between",
            "is_not_close_to",
            "is_not_zero",
            "is_positive",
            "is_unicode",
            "is_zero",
            "matches_structure",
        }
    ),
    "datetime.datetime": frozenset(
        {
            "is_negative",
            "is_not_between",
            "is_positive",
            "matches_structure",
        }
    ),
    "datetime.date": frozenset(
        {
            "is_negative",
            "is_not_between",
            "is_positive",
            "matches_structure",
        }
    ),
    "pathlib.Path": frozenset(
        {
            "is_between",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_negative",
            "is_not_between",
            "is_positive",
            "matches_structure",
        }
    ),
    "bytes": frozenset(
        {
            "all_satisfy",
            "any_satisfy",
            "at_json_path",
            "conforms_to_openapi",
            "contains_any_of",
            "contains_duplicates",
            "contains_exactly",
            "contains_exactly_in_any_order",
            "contains_ignoring_case",
            "contains_in_order",
            "contains_none_of",
            "contains_only",
            "contains_only_once",
            "contains_sequence",
            "does_not_contain",
            "does_not_contain_duplicates",
            "does_not_have_json_path",
            "each",
            "extracting",
            "has_json_path",
            "is_array_close_to",
            "is_array_equal",
            "is_between",
            "is_frame_equal",
            "is_negative",
            "is_not_between",
            "is_not_close_to",
            "is_not_zero",
            "is_positive",
            "is_unicode",
            "is_zero",
            "matches_json_schema",
            "matches_json_schema_from_file",
            "matches_structure",
            "none_satisfy",
            "satisfies_exactly",
            "satisfies_exactly_in_any_order",
            "zip_satisfies",
        }
    ),
    "bytearray": frozenset(
        {
            "all_satisfy",
            "any_satisfy",
            "at_json_path",
            "conforms_to_openapi",
            "contains_any_of",
            "contains_duplicates",
            "contains_exactly",
            "contains_exactly_in_any_order",
            "contains_ignoring_case",
            "contains_in_order",
            "contains_none_of",
            "contains_only",
            "contains_only_once",
            "contains_sequence",
            "does_not_contain",
            "does_not_contain_duplicates",
            "does_not_have_json_path",
            "each",
            "extracting",
            "has_json_path",
            "is_array_close_to",
            "is_array_equal",
            "is_between",
            "is_frame_equal",
            "is_negative",
            "is_not_between",
            "is_not_close_to",
            "is_not_zero",
            "is_positive",
            "is_unicode",
            "is_zero",
            "matches_json_schema",
            "matches_json_schema_from_file",
            "matches_structure",
            "none_satisfy",
            "satisfies_exactly",
            "satisfies_exactly_in_any_order",
            "zip_satisfies",
        }
    ),
    "_FrameShaped": frozenset(
        {
            "is_between",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_not_between",
            "matches_structure",
        }
    ),
    "_FrameThatWalks": frozenset(
        {
            "any_satisfy",
            "at_json_path",
            "conforms_to_openapi",
            "contains_any_of",
            "contains_duplicates",
            "contains_exactly",
            "contains_exactly_in_any_order",
            "contains_ignoring_case",
            "contains_in_order",
            "contains_none_of",
            "contains_only_once",
            "contains_sequence",
            "does_not_contain",
            "does_not_contain_duplicates",
            "does_not_have_json_path",
            "element",
            "ends_with",
            "filtered_on",
            "first",
            "flat_mapped",
            "has_json_path",
            "is_between",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_not_between",
            "is_not_close_to",
            "is_not_zero",
            "is_sorted",
            "is_unicode",
            "is_zero",
            "last",
            "mapped",
            "matches_json_schema",
            "matches_json_schema_from_file",
            "matches_structure",
            "none_satisfy",
            "satisfies_exactly",
            "satisfies_exactly_in_any_order",
            "single",
            "starts_with",
            "zip_satisfies",
        }
    ),
    "_FrameCarryingEverything": frozenset(
        {
            "any_satisfy",
            "at_json_path",
            "conforms_to_openapi",
            "contains_any_of",
            "contains_duplicates",
            "contains_entry",
            "contains_exactly",
            "contains_exactly_in_any_order",
            "contains_ignoring_case",
            "contains_in_order",
            "contains_key",
            "contains_none_of",
            "contains_only_once",
            "contains_sequence",
            "contains_value",
            "does_not_contain",
            "does_not_contain_duplicates",
            "does_not_contain_entry",
            "does_not_contain_key",
            "does_not_contain_value",
            "does_not_exist",
            "does_not_have_json_path",
            "does_not_raise",
            "does_not_warn",
            # callable as well as everything else, so the rung a second poll restricts to matches
            "eventually",
            "eventually_sync",
            "element",
            "ends_with",
            "exists",
            "filtered_on",
            "first",
            "flat_mapped",
            "has_json_path",
            "is_between",
            "is_child_of",
            "is_close_to",
            "is_directory",
            "is_executable",
            "is_file",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_inf",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_named",
            "is_nan",
            "is_negative",
            "is_not_between",
            "is_not_close_to",
            "is_not_inf",
            "is_not_nan",
            "is_not_zero",
            "is_positive",
            "is_readable",
            "is_sorted",
            "is_unicode",
            "is_writable",
            "is_zero",
            "last",
            "mapped",
            "matches_json_schema",
            "matches_json_schema_from_file",
            "matches_structure",
            "none_satisfy",
            "raises",
            "satisfies_exactly",
            "satisfies_exactly_in_any_order",
            "single",
            "starts_with",
            "warns",
            "zip_satisfies",
        }
    ),
    "_ArrayShaped": frozenset(
        {
            "is_between",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_not_between",
            "matches_structure",
        }
    ),
    "_ArrayThatWalks": frozenset(
        {
            "any_satisfy",
            "at_json_path",
            "conforms_to_openapi",
            "contains_any_of",
            "contains_duplicates",
            "contains_exactly",
            "contains_exactly_in_any_order",
            "contains_ignoring_case",
            "contains_in_order",
            "contains_none_of",
            "contains_only_once",
            "contains_sequence",
            "does_not_contain",
            "does_not_contain_duplicates",
            "does_not_have_json_path",
            "element",
            "ends_with",
            "filtered_on",
            "first",
            "flat_mapped",
            "has_json_path",
            "is_between",
            "is_frame_equal",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_not_between",
            "is_not_close_to",
            "is_not_zero",
            "is_sorted",
            "is_unicode",
            "is_zero",
            "last",
            "mapped",
            "matches_json_schema",
            "matches_json_schema_from_file",
            "matches_structure",
            "none_satisfy",
            "satisfies_exactly",
            "satisfies_exactly_in_any_order",
            "single",
            "starts_with",
            "zip_satisfies",
        }
    ),
    "_ArrayCarryingEverything": frozenset(
        {
            "any_satisfy",
            "at_json_path",
            "conforms_to_openapi",
            "contains_any_of",
            "contains_duplicates",
            "contains_entry",
            "contains_exactly",
            "contains_exactly_in_any_order",
            "contains_ignoring_case",
            "contains_in_order",
            "contains_key",
            "contains_none_of",
            "contains_only_once",
            "contains_sequence",
            "contains_value",
            "does_not_contain",
            "does_not_contain_duplicates",
            "does_not_contain_entry",
            "does_not_contain_key",
            "does_not_contain_value",
            "does_not_exist",
            "does_not_have_json_path",
            "does_not_raise",
            "does_not_warn",
            # callable as well as everything else, so the rung a second poll restricts to matches
            "eventually",
            "eventually_sync",
            "element",
            "ends_with",
            "exists",
            "filtered_on",
            "first",
            "flat_mapped",
            "has_json_path",
            "is_between",
            "is_child_of",
            "is_close_to",
            "is_directory",
            "is_executable",
            "is_file",
            "is_frame_equal",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_inf",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_named",
            "is_nan",
            "is_negative",
            "is_not_between",
            "is_not_close_to",
            "is_not_inf",
            "is_not_nan",
            "is_not_zero",
            "is_positive",
            "is_readable",
            "is_sorted",
            "is_unicode",
            "is_writable",
            "is_zero",
            "last",
            "mapped",
            "matches_json_schema",
            "matches_json_schema_from_file",
            "matches_structure",
            "none_satisfy",
            "raises",
            "satisfies_exactly",
            "satisfies_exactly_in_any_order",
            "single",
            "starts_with",
            "warns",
            "zip_satisfies",
        }
    ),
    "Callable[..., int]": frozenset(
        {
            "is_between",
            "is_greater_than",
            "is_greater_than_or_equal_to",
            "is_less_than",
            "is_less_than_or_equal_to",
            "is_not_between",
            "matches_structure",
        }
    ),
    "object": frozenset(),
}
"""What those rungs put on a chain over each witness that its own view does not carry.

Measured on the sync chain, and the async chain is held to the same set: both are generated from one
set of declarations, so a name on one and not the other is a defect in itself.  The verdict twin is a
subset, since it drops the transforms.
"""
