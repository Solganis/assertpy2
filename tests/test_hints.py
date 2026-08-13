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
from assertpy2._hints import _explains, diagnose
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


def _hint(actual, expected):
    """The diagnostic line alone, or ``None``, without the message it would be printed under."""
    with pytest.raises(AssertionFailure) as failure:
        assert_that(actual).is_equal_to(expected)
    return diagnose(failure.value.diff, actual, expected)


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
