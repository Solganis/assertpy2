"""The diagnostic line under a failure message.

Two things are being pinned here, and the second is the one that decides whether the feature is worth
having.  The first is that a hint appears when the whole difference has one explanation.  The second
is that it stays away otherwise: a hint that fires on an ordinary wrong value is noise, and noise is
what teaches people to stop reading the line at all, taking the useful ones down with it.
"""

from __future__ import annotations

import dataclasses
import enum

import pytest

from assertpy2 import assert_that
from assertpy2._engine._path import _ROOT
from assertpy2._hints import _explains, diagnose, identity_candidate
from assertpy2.errors import AssertionFailure, DiffEntry, DiffResult


@dataclasses.dataclass
class _User:
    name: str
    city: str


class _State(enum.Enum):
    CLOSED = "closed"


class _UserId(int):
    """A domain wrapper over a value it compares equal to, so only `strict_types` calls it a difference."""


def _message(actual, expected, **kwargs):
    with pytest.raises(AssertionFailure) as failure:
        assert_that(actual).is_equal_to(expected, **kwargs)
    return str(failure.value)


def _hint(actual, expected, **kwargs):
    """The diagnostic line alone, or ``None``, without the message it would be printed under."""
    with pytest.raises(AssertionFailure) as failure:
        assert_that(actual).is_equal_to(expected, **kwargs)
    return diagnose(failure.value.diff, actual, expected, identity=identity_candidate(actual, expected))


class TestTheHintNamesTheWholeDifference:
    def test_surrounding_whitespace_nested_in_a_structure(self):
        # the nastiest failure of the lot: the diff shows two values that render the same
        message = _message({"user": {"name": "bob "}}, {"user": {"name": "bob"}})
        assert_that(message).contains("every difference here is one of surrounding whitespace")

    def test_line_endings(self):
        assert_that(_message("one\r\ntwo", "one\ntwo")).contains("every difference here is one of line endings")

    def test_line_endings_win_over_whitespace_when_both_would_serve(self):
        # stripping also hides a trailing "\r\n", so without an order the broader claim would be made
        message = _message("a\r\n", "a\n")
        assert_that(message).contains("one of line endings")
        assert_that(message).does_not_contain("surrounding whitespace")

    def test_two_explanations_when_neither_alone_accounts_for_it(self):
        # the line ending is in the middle, so stripping cannot reach it, and the trailing space is
        # outside it, so normalising newlines cannot either. it takes both
        message = _message("a\r\nb ", "a\nb")
        assert_that(message).contains("one of line endings and surrounding whitespace")

    def test_every_entry_has_to_be_covered_not_merely_some(self):
        # one field is whitespace, the other is a different word. explaining half of a failure sends
        # the reader to fix the half that was never the problem
        message = _message({"a": "x ", "b": "one"}, {"a": "x", "b": "two"})
        assert_that(message).does_not_contain("every difference here")


class TestKeysTheExpectedSideDoesNotHave:
    def test_extra_keys_and_nothing_else(self):
        message = _message({"a": 1, "b": 2}, {"a": 1})
        assert_that(message).contains("every shared key matches, and actual carries keys")

    def test_nested_extra_keys(self):
        message = _message({"user": {"a": 1, "b": 2}}, {"user": {"a": 1}})
        assert_that(message).contains("carries keys the expected side does not")


class TestTheShapeRatherThanTheValues:
    def test_a_dto_against_the_payload_it_was_built_from(self):
        # the reviewer's standing case: a model compared with raw JSON. before this there was no
        # signal at all that the contents were identical
        message = _message({"name": "a", "city": "b"}, _User("a", "b"))
        assert_that(message).contains("the contents match field for field")

    def test_the_same_nested(self):
        message = _message({"data": [{"name": "a", "city": "b"}]}, {"data": [_User("a", "b")]})
        assert_that(message).contains("only the type of the two sides differs")

    def test_a_field_that_actually_differs_stays_silent(self):
        message = _message({"name": "a", "city": "X"}, _User("a", "b"))
        assert_that(message).does_not_contain("the contents match")


class TestNormalisationsAddedInTheSecondSlice:
    @pytest.mark.parametrize(
        ("actual", "expected", "phrase"),
        [
            ('{"a": 1}', {"a": 1}, "unparsed JSON text"),
            (b"hello", "hello", "bytes against decoded text"),
            (_State.CLOSED, "closed", "enum members against their values"),
        ],
        ids=["json", "bytes", "enum"],
    )
    def test_each_form(self, actual, expected, phrase):
        assert_that(_message(actual, expected)).contains(phrase)

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ('{"a": 2}', {"a": 1}),
            (b"hello", "world"),
            (_State.CLOSED, "open"),
        ],
        ids=["json parsing to something else", "bytes decoding to other text", "enum of another value"],
    )
    def test_each_near_miss(self, actual, expected):
        assert_that(_message(actual, expected)).does_not_contain("every difference here")

    def test_two_json_documents_are_not_called_unparsed(self):
        # both sides are text here, so neither is the one that was left unparsed. one normalisation,
        # two causes, and only the wording can tell them apart
        message = _message('{"a": 1}', '{"a":1}')
        assert_that(message).contains("the same JSON written differently")
        assert_that(message).does_not_contain("unparsed")


class TestRearrangementIsOnlySaidWhereOrderExists:
    @pytest.mark.parametrize(
        ("actual", "expected"),
        [([1, 2, 3], [3, 1, 2]), ({"x": {"y": [1, 2, 3]}}, {"x": {"y": [3, 1, 2]}})],
        ids=["list", "nested list"],
    )
    def test_a_reordered_sequence(self, actual, expected):
        assert_that(_message(actual, expected)).contains("the same elements, in a different order")

    def test_two_fields_holding_each_other_s_value_is_not_a_rearrangement(self):
        # the check that keeps this from being noise. with two boolean fields, any failure where both
        # flip holds "the same values elsewhere", which was one generated failure in five: every one
        # of those statements true, not one of them useful
        assert_that(_message({"read": True, "write": False}, {"read": False, "write": True})).does_not_contain(
            "different order"
        )

    def test_a_single_difference_is_never_a_rearrangement(self):
        assert_that(_message([1, 2], [1, 3])).does_not_contain("different order")

    def test_elements_that_cannot_be_hashed_take_the_slower_route(self):
        # counting is the fast path and needs hashable values. driven through built entries because
        # the diff decomposes a reordered list of dicts into per-key entries, so the pairs that do
        # reach here holding an unhashable value come from a leaf the walk stopped at
        entries = [
            _ROOT.index(0).entry(actual={"a": 1}, expected={"b": 2}),
            _ROOT.index(1).entry(actual={"b": 2}, expected={"a": 1}),
        ]
        assert_that(diagnose(DiffResult(kind="sequence", entries=entries))).contains("in a different order")

    def test_a_hash_that_raises_something_other_than_type_error_is_left_alone(self):
        # an unhashable value raises TypeError and has a slower route waiting for it. anything else
        # coming out of a user __hash__ is not a shape this understands, so it says nothing
        class Hostile:
            def __hash__(self):
                raise ValueError("boom")

        entries = [
            _ROOT.index(0).entry(actual=Hostile(), expected=1),
            _ROOT.index(1).entry(actual=2, expected=Hostile()),
        ]
        assert_that(diagnose(DiffResult(kind="sequence", entries=entries))).is_none()

    def test_elements_that_can_be_neither_hashed_nor_reprd_are_left_alone(self):
        class Awkward:
            __hash__ = None

            def __repr__(self):
                raise ValueError("boom")

        entries = [
            _ROOT.index(0).entry(actual=Awkward(), expected=1),
            _ROOT.index(1).entry(actual=2, expected=Awkward()),
        ]
        assert_that(diagnose(DiffResult(kind="sequence", entries=entries))).is_none()


class TestNaNIsSaidBeforeAnythingElse:
    def test_a_comparison_that_can_never_pass(self):
        # `Expected <nan:float> to be equal to <nan:float>` reads as a bug in the library until the
        # line below explains that this is what NaN does
        assert_that(_message(float("nan"), float("nan"))).contains("a NaN is equal to nothing, not even itself")

    def test_nan_nested_among_other_differences(self):
        # it comes first because no change to the other fields could make this pass
        message = _message({"score": float("nan"), "name": "a"}, {"score": 1.0, "name": "b"})
        assert_that(message).contains("a NaN takes part in this comparison")


class TestSilenceOnEverythingElse:
    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ({"a": 1}, {"a": 2}),
            ("name ", "nickname"),
            ("a b", "ab"),
            ([1, 2, 3], [3, 1, 4]),
            ({"a": "x"}, {"a": "y "}),
        ],
        ids=["plain value", "whitespace plus a word", "inner space", "different elements", "different word"],
    )
    def test_an_ordinary_failure_gets_no_line(self, actual, expected):
        assert_that(_message(actual, expected)).does_not_contain("every difference here")

    def test_a_value_that_really_is_none_is_not_read_as_an_absent_key(self):
        # the whole reason `absent` exists. both leave the field at None, and before the marker this
        # was reported as a key the expected side does not have, which was simply untrue
        message = _message({"a": 1}, {"a": None})
        assert_that(message).does_not_contain("carries keys the expected side does not")

    def test_a_mixture_of_absent_and_differing_has_no_single_statement(self):
        entries = [
            DiffEntry(path="b", actual=2, expected=None, absent="expected"),
            DiffEntry(path="a", actual=1, expected=9),
        ]
        assert_that(diagnose(DiffResult(kind="dict", entries=entries))).is_none()

    @pytest.mark.parametrize("kind", ["match", "openapi", "contains"])
    def test_a_predicate_description_is_never_treated_as_a_value(self, kind):
        # a `match` entry holds the actual value against a description of a predicate, not against a
        # value. without the kind gate this pair equalises under stripping and the reader is told,
        # with some authority, that a predicate differs from a value by whitespace
        entries = [DiffEntry(path="role", actual="guest ", expected="guest")]
        assert_that(diagnose(DiffResult(kind=kind, entries=entries))).is_none()

    def test_a_sequence_is_not_told_it_has_extra_keys(self):
        # a set or a list reports its extras the same way, and "keys" is the wrong word for both
        entries = [DiffEntry(path="extra", actual=5, expected=None, absent="expected")]
        assert_that(diagnose(DiffResult(kind="set", entries=entries))).is_none()

    def test_no_diff_at_all(self):
        assert_that(diagnose(None)).is_none()

    def test_a_diff_with_nothing_in_it(self):
        assert_that(diagnose(DiffResult(kind="dict", entries=[]))).is_none()

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ("{not json at all", "{something else"),
            (b"\xff\xfe raw", "raw"),
        ],
        ids=["a string that only looks like json", "bytes that are not utf-8"],
    )
    def test_a_normalisation_that_cannot_be_applied_explains_nothing(self, actual, expected):
        assert_that(_message(actual, expected)).does_not_contain("every difference here")

    def test_a_model_and_an_attrs_instance_are_both_read_as_their_fields(self):
        pydantic = pytest.importorskip("pydantic")
        attr = pytest.importorskip("attrs")

        class Model(pydantic.BaseModel):
            name: str

        @attr.define
        class Attrs:
            name: str

        for built in (Model(name="a"), Attrs(name="a")):
            assert_that(_message({"name": "a"}, built)).contains("the contents match field for field")

    def test_a_field_read_that_raises_cannot_break_the_failure(self):
        # a model whose dump explodes is the caller's business, and their assertion error has to
        # survive this line trying to describe it
        class BrokenModel:
            def model_dump(self):
                raise ValueError("boom")

        entries = [DiffEntry(path="x", actual={"name": "a"}, expected=BrokenModel())]
        assert_that(diagnose(DiffResult(kind="dict", entries=entries))).is_none()

    def test_values_that_cannot_be_sorted_cannot_break_the_failure(self):
        class Unreprable:
            def __repr__(self):
                raise ValueError("boom")

        entries = [
            _ROOT.index(0).entry(actual=Unreprable(), expected=1),
            _ROOT.index(1).entry(actual=2, expected=Unreprable()),
        ]
        assert_that(diagnose(DiffResult(kind="sequence", entries=entries))).is_none()

    def test_a_value_whose_comparison_raises_cannot_break_the_failure(self):
        # numpy arrays and anything else with an opinionated __eq__ raise from `!=`. this runs while
        # an assertion error is already on its way out, and swallowing the real failure to report a
        # crash from the helpful line would be the worst outcome available
        class Ambiguous:
            def __ne__(self, other):
                raise ValueError("ambiguous")

            def __hash__(self):
                return 0

        entries = [DiffEntry(path="a", actual=Ambiguous(), expected=Ambiguous())]
        assert_that(diagnose(DiffResult(kind="dict", entries=entries))).is_none()


class TestTheMessageStaysUsableAsAPrefix:
    def test_the_original_sentence_is_untouched(self):
        # the line goes below, so `pytest.raises(match=...)` and `startswith` written against the
        # original message keep working
        message = _message("bob ", "bob")
        assert_that(message).starts_with("Expected <bob > to be equal to <bob>, but was not.")

    def test_a_description_still_leads(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that("bob ").described_as("the name").is_equal_to("bob")
        assert_that(str(failure.value)).starts_with("[the name] Expected")
        assert_that(str(failure.value)).contains("surrounding whitespace")


class TestOnlyTheTypesDiffer:
    """The failure a REST payload produces more than any other: the ids came back as text."""

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ({"id": 7}, {"id": "7"}),
            ({"id": 7, "qty": 3, "n": 9}, {"id": "7", "qty": "3", "n": "9"}),
            ({"user": {"id": 7}}, {"user": {"id": "7"}}),
            ([1, 2], ["1", "2"]),
            ({"total": 1.5}, {"total": "1.5"}),
            ({"a": None}, {"a": "None"}),
        ],
        ids=["one field", "every field", "nested", "list", "float", "none"],
    )
    def test_a_payload_that_came_back_as_text(self, actual, expected):
        assert_that(_message(actual, expected)).contains("the same text against a value of another type")

    def test_a_scalar_says_nothing_because_the_headline_already_did(self):
        # `<7:int>` / `<7:str>` names both types outright, which is more than the line could say
        message = _message(7, "7")
        assert_that(message).contains("<7:int>").contains("<7:str>")
        assert_that(message).does_not_contain("another type")

    def test_a_mixture_of_type_and_value_differences_says_nothing(self):
        # one pair differs in type and the other in value, so no single statement covers the failure
        assert_that(_message({"a": 7, "b": 1}, {"a": "7", "b": 2})).does_not_contain("another type")

    def test_a_scalar_whose_two_sides_read_differently_still_gets_the_line(self):
        # the headline names both types only where the two render alike, and `1` against `1.0` does not
        assert_that(_hint(1, 1.0, strict_types=True)).is_equal_to(
            "the values on both sides are equal, and only their types differ"
        )


class TestStrictTypesNoLongerBlamesJson:
    """The first invariant of the ladder: a normalisation explains a pair only if the pair differed.

    Under `strict_types` the two sides of an entry compare equal and are a difference anyway, so every
    normalisation "resolves" them by doing nothing and the first step took the credit. A comparison
    holding no JSON at all was reported as one of unparsed JSON text.
    """

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [({"id": _UserId(7)}, {"id": 7}), ({"n": 1}, {"n": 1.0}), ({"n": True}, {"n": 1})],
        ids=["subclass", "int against float", "bool against int"],
    )
    def test_the_line_names_the_types_rather_than_json(self, actual, expected):
        message = _message(actual, expected, strict_types=True)
        assert_that(message).contains("only their types differ")
        assert_that(message).does_not_contain("JSON")

    def test_a_strict_failure_that_also_differs_in_value_says_nothing(self):
        message = _message({"n": 1, "m": 2}, {"n": 1.0, "m": 3}, strict_types=True)
        assert_that(message).does_not_contain("only their types differ")


class TestTheNarrowerExplanationStillWins:
    """The second invariant: a named encoding outranks the general claim that the types differ.

    The type line is the broad statement, so a step that says which encoding the two sides differ in
    has to be reached first, or every one of those failures would be reported as a bare type mismatch.
    """

    def test_text_that_parses_as_json_is_still_called_json(self):
        # both sides read alike under `str()`, which is exactly what the type line looks for
        message = _message({"a": [1, 2]}, {"a": "[1, 2]"})
        assert_that(message).contains("unparsed JSON text")
        assert_that(message).does_not_contain("another type")

    @pytest.mark.parametrize(
        ("actual", "expected", "expected_line"),
        [
            ({"a": b"x", "b": b"y"}, {"a": "x", "b": "y"}, "bytes against decoded text"),
            ({"a": _State.CLOSED}, {"a": "closed"}, "enum members against their values"),
        ],
        ids=["bytes", "enum"],
    )
    def test_a_type_difference_the_ladder_already_explains(self, actual, expected, expected_line):
        # both of these differ in type too, and both have a better answer than saying so
        assert_that(_message(actual, expected)).contains(expected_line)


class TestTheContractOfTheExplanationLadder:
    """The two rules a new step in `_STEPS` has to respect, stated where a change will trip on them.

    Both are written next to the ladder as comments as well. A comment can be read past a year from
    now; a test cannot.
    """

    def test_a_normalisation_never_explains_a_pair_that_already_matches(self):
        # the first rule, at the level it lives on rather than through the failure it produced. a pair
        # whose sides already agree is a difference for some other reason, and a step that leaves it
        # alone has not accounted for anything
        assert_that(_explains([(1, 1)], (lambda value: value,))).is_false()
        assert_that(_explains([("a ", "a")], (str.strip,))).is_true()

    def test_a_named_encoding_outranks_the_general_claim_that_types_differ(self):
        # the second rule. both sides read alike under `str()`, which is what the type branch looks
        # for, and the ladder has the better answer
        message = _message({"a": [1, 2]}, {"a": "[1, 2]"})
        assert_that(message).contains("unparsed JSON text")
        assert_that(message).does_not_contain("another type")

    def test_a_step_is_paired_only_with_the_steps_under_it(self):
        """A pair runs in ladder order, so a bytes payload against the document it holds gets no line."""
        assert_that(_hint(b'{"a": 1}', {"a": 1})).is_none()


class TestBytesReadTheSameAsText:
    """A difference of whitespace or line endings is the same difference in either type.

    It was not: the string branch demanded two `str` and returned nothing for anything else, so a
    payload compared as bytes got no hint at all while the identical comparison on text got one. Found
    on a live suite whose failures were all bytes, where the summary of that run said nothing that the
    individual failures did not already say - and the reason turned out to be here, not there.
    """

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ("payload\n", "payload"),
            ("  x  ", "x"),
            ("a\r\nb", "a\nb"),
            ("line1\nline2\n", "line1\nline2"),
            ("a\r\n b", "a\nb"),
            ("one", "two"),
            ("x\ty", "x y"),
        ],
        ids=["trailing newline", "surrounding spaces", "line endings", "multiline", "both at once", "plain", "tab"],
    )
    def test_the_same_pair_reads_the_same_in_both_types(self, actual, expected):
        # including the shapes that must stay silent: a rule that only fires is half a rule
        assert_that(_hint(actual.encode(), expected.encode())).is_equal_to(_hint(actual, expected))

    def test_bytes_that_do_not_decode_are_read_too(self):
        # the pair a decode-first route would miss, and binary payloads are where bytes get compared
        assert_that(_message(b"\xd7\xd8\n", b"\xd7\xd8")).contains("surrounding whitespace")

    def test_two_bytes_are_not_called_a_difference_of_encoding(self):
        # `_decoded` sits above `_stripped` in the ladder and would take the credit through a pair of
        # steps, telling a reader about decoded text when both sides are bytes and nothing was decoded
        assert_that(_message(b"payload\n", b"payload")).does_not_contain("decoded text")

    def test_one_side_bytes_still_reads_as_encoding(self):
        assert_that(_message(b"x", "x")).contains("bytes against decoded text")

    def test_a_bytearray_on_the_other_side_is_not_read_as_text(self):
        # what this branch is handed is the two values the assertion compared, and a `bytearray` is
        # neither of the two types the steps under it know how to normalise
        assert_that(_hint(b"payload\n", bytearray(b"payload"))).is_none()


class _NoEq:
    """A class that leaves equality alone, which is what every class does until it does not."""

    def __init__(self, name, city):
        self.name, self.city = name, city


class _AlwaysUnequal:
    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return False

    __hash__ = None


@dataclasses.dataclass(eq=False)
class _OptedOut:
    name: str


class TestEqualityDecidedByIdentity:
    """The failure that can never pass, and whose message gives the reader nothing to act on.

    A type that leaves ``==`` to ``object`` is equal only to itself, so an expected value a test built
    is not equal to the one the code returned however well the two agree. Said before anything about
    the values, like the NaN fact, because no value on the other side would have helped.
    """

    def test_two_objects_of_a_type_that_defines_no_equality(self):
        assert_that(_message(_NoEq("ada", "london"), _NoEq("ada", "london"))).contains("compare with object's __eq__")

    def test_it_is_said_where_the_values_differ_too(self):
        # the reader would otherwise fix the field and fail again on the same line
        assert_that(_hint(_NoEq("ada", "london"), _NoEq("ada", "paris"))).contains("equality is identity")

    def test_a_dataclass_that_opted_out_of_equality(self):
        # the diff has no entries at all here: every field agrees and the walk has nothing to report
        assert_that(_message(_OptedOut("ada"), _OptedOut("ada"))).contains("equality is identity")

    def test_a_dataclass_that_opted_out_and_whose_fields_differ(self):
        # the diff does show the field, and fixing it would still not make the comparison pass
        assert_that(_message(_OptedOut("ada"), _OptedOut("grace"))).contains("equality is identity")

    def test_two_exceptions_of_one_class(self):
        # the everyday form of this trap: exceptions carry identity equality and tests compare them
        assert_that(_hint(ValueError("boom"), ValueError("boom"))).contains("equality is identity")

    def test_an_object_nested_in_a_structure_is_left_alone(self):
        # what decided the comparison above the pair is the enclosing type's own `__eq__`, which may be
        # anything, so a difference found under one says nothing about why the comparison failed
        left, right = {"user": _NoEq("ada", "london")}, {"user": _NoEq("ada", "london")}
        assert_that(_message(left, right)).does_not_contain("identity")

    def test_a_type_that_defines_equality_is_not_blamed_for_identity(self):
        assert_that(_hint(_AlwaysUnequal(1), _AlwaysUnequal(1))).is_none()

    def test_a_type_deciding_its_own_inequality_is_not_blamed_either(self):
        # the comparison a failing assertion runs is `actual != expected`, which this type answers
        class Contrary:
            def __init__(self, value):
                self.value = value

            def __ne__(self, other):
                return True

            __hash__ = None

        assert_that(_hint(Contrary(1), Contrary(1))).is_none()

    @pytest.mark.parametrize(
        "options",
        [
            {"comparators": {_NoEq: lambda actual, expected: False}},
            {"tolerance": 0.1},
            {"strict_types": True},
            {"ignore_null": True},
            {"ignore": "nothing"},
            {"include": "city"},
        ],
        ids=["comparators", "tolerance", "strict types", "ignore null", "ignore", "include"],
    )
    def test_a_walked_comparison_is_not_blamed_on_identity(self, options):
        # every option replaces `==` with a walk over keys or fields, under which two separate instances
        # of this type do compare equal, so nothing here is decided by identity
        message = _message(_NoEq("ada", "london"), _NoEq("ada", "paris"), **options)
        assert_that(message).does_not_contain("identity")

    def test_a_mapping_of_its_own_is_walked_and_so_is_not_blamed_either(self):
        # a duck-typed mapping goes down the key walk rather than to `==`
        class Headers:
            def __init__(self, data):
                self._data = data

            def keys(self):
                return self._data.keys()

            def items(self):
                return self._data.items()

            def __getitem__(self, key):
                return self._data[key]

            def __iter__(self):
                return iter(self._data)

            def __len__(self):
                return len(self._data)

        assert_that(_message(Headers({"a": 1}), Headers({"a": 2}))).does_not_contain("identity")

    def test_a_containment_failure_over_the_same_values_is_not_it(self):
        # the items are the same objects and only their order differs, which the message already says,
        # and identity had nothing to do with it
        left, right = _NoEq("ada", "london"), _NoEq("grace", "london")
        with pytest.raises(AssertionFailure) as failure:
            assert_that([left, right]).contains_exactly(right, left)
        assert_that(str(failure.value)).does_not_contain("identity")

    def test_a_mixture_with_an_ordinary_difference_says_nothing(self):
        left = {"user": _NoEq("ada", "london"), "id": 1}
        right = {"user": _NoEq("ada", "london"), "id": 2}
        assert_that(_message(left, right)).does_not_contain("identity")

    def test_two_sides_of_different_types_are_not_it(self):
        assert_that(_hint(_NoEq("ada", "london"), _AlwaysUnequal(1))).is_none()

    def test_the_same_object_on_both_sides_is_not_it(self):
        # it compares equal under identity, so a failure can never be about that
        value = _NoEq("ada", "london")
        assert_that(identity_candidate(value, value)).is_false()

    def test_a_type_that_rewrites_its_own_equality_mid_comparison_is_not_it(self):
        # the question is asked before the comparison runs, so the type that decided the failure is the
        # one answering it, not the one it left behind
        class Sneaky:
            def __init__(self, value):
                self.value = value

            def __ne__(self, other):
                Sneaky.__ne__ = object.__ne__
                return True

            __hash__ = None

        assert_that(_message(Sneaky(1), Sneaky(1))).does_not_contain("identity")

    def test_a_descriptor_answering_for_the_class_is_not_believed(self):
        # what an operator runs is the definition the class tree carries, and a descriptor can answer
        # one way for the class and another for an instance
        class Deceptive:
            class Equality:
                def __get__(self, instance, owner=None):
                    return object.__eq__ if instance is None else (lambda other: False)

            __eq__ = Equality()
            __hash__ = None

            def __init__(self, value):
                self.value = value

        assert_that(_hint(Deceptive(1), Deceptive(1))).is_none()

    def test_a_type_inheriting_its_equality_is_still_read(self):
        # the walk stops at the first class that defines the name, which may be a base
        class Base:
            def __eq__(self, other):
                return False

            __hash__ = None

        class Child(Base):
            def __init__(self, value):
                self.value = value

        assert_that(_hint(Child(1), Child(1))).is_none()

    def test_the_operator_is_asked_about_rather_than_the_class_attribute(self):
        # a metaclass can answer for `__eq__` with something other than what the operator runs, so the
        # lookup is static: this type compares by value and must not be called identity-based
        class Sneaky(type):
            def __getattribute__(cls, name):
                if name in ("__eq__", "__ne__"):
                    return getattr(object, name)
                return super().__getattribute__(name)

        class ByValue(metaclass=Sneaky):
            def __init__(self, value):
                self.value = value

            def __eq__(self, other):
                return isinstance(other, ByValue) and self.value == other.value

            __hash__ = None

        assert_that(_hint(ByValue(1), ByValue(2))).is_none()

    def test_a_type_that_cannot_be_asked_about_its_equality_is_survived(self):
        # the failure is already on its way out, and a diagnostic that raises would replace it
        class Hostile(type):
            def __getattribute__(cls, name):
                if name == "__eq__":
                    raise RuntimeError("no lookups here")
                return super().__getattribute__(name)

        class Guarded(metaclass=Hostile):
            def __init__(self, value):
                self.value = value

        assert_that(_message(Guarded(1), Guarded(1))).contains("to be equal to")

    def test_a_class_tree_that_names_no_equality_at_all_is_not_read_as_identity(self):
        # the walk answers "not object's" when it finds no definition anywhere, which is the safe
        # direction: a line claiming identity is worse than no line
        class Meta(type):
            @property
            def __mro__(cls):
                return ()

        class Blank(metaclass=Meta):
            def __init__(self, value):
                self.value = value

        assert_that(identity_candidate(Blank(1), Blank(1))).is_false()

    def test_a_metaclass_descriptor_raising_on_the_equality_lookup_is_survived(self):
        # a data descriptor on the metaclass is read before the class tree is, so the cheap look does
        # run code of the caller's and can raise, and the failure has to survive that
        class Raising:
            def __get__(self, instance, owner=None):
                raise RuntimeError("no lookups here")

            def __set__(self, instance, value):
                raise RuntimeError("no lookups here")

        class Meta(type):
            __eq__ = Raising()

        class Guarded(metaclass=Meta):
            def __init__(self, value):
                self.value = value

        assert_that(identity_candidate(Guarded(1), Guarded(1))).is_false()


class _SameText:
    """Two instances that read alike and are never equal, so only their text could pass for a type difference."""

    def __repr__(self):
        return "<same>"

    def __eq__(self, other):
        return False

    __hash__ = None


@dataclasses.dataclass
class _MappingRow:
    """A dataclass that is also a mapping, so its fields match its own contents without a second type."""

    name: str

    def keys(self):
        return ("name",)

    def __iter__(self):
        return iter(("name",))

    def __getitem__(self, key):
        return getattr(self, key)


class TestATypeDifferenceIsClaimedOnlyWhereTheTypesDiffer:
    """Both lines about types read the two sides of one comparison, and one side is not enough."""

    def test_two_sides_of_one_type_that_read_alike_are_left_alone(self):
        # the pair the text branch looks at: same rendering, never equal, and one type between them
        assert_that(_hint({"a": _SameText()}, {"a": _SameText()})).is_none()

    def test_field_for_field_is_not_said_when_both_sides_are_the_same_type(self):
        # built rather than compared: the walk descends into two mappings, so a pair of them reaches
        # the leaf check only when it is handed one
        entry = DiffEntry(path="row", actual=_MappingRow("a"), expected=_MappingRow("a"))
        assert_that(diagnose(DiffResult(kind="dict", entries=[entry]))).is_none()


class TestEachLineIsStatedInFull:
    """The whole sentence rather than a phrase out of it, which is what the reader is left holding."""

    @pytest.mark.parametrize(
        ("actual", "expected", "line"),
        [
            ('{"a": 1}', '{"a":1}', "every difference here is one of the same JSON written differently"),
            ('{"a": 1}', {"a": 1}, "every difference here is one of unparsed JSON text"),
            ({"id": 7}, {"id": "7"}, "every difference here is the same text against a value of another type"),
            (
                {"name": "a", "city": "b"},
                _User("a", "b"),
                "the contents match field for field, and only the type of the two sides differs",
            ),
            ([1, 2, 3], [3, 1, 2], "both sides hold the same elements, in a different order"),
        ],
        ids=["json formatting", "unparsed json", "text against another type", "field for field", "reordered"],
    )
    def test_the_line_reads_exactly_as_written(self, actual, expected, line):
        assert_that(_hint(actual, expected)).is_equal_to(line)
