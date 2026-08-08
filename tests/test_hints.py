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
from assertpy2._hints import diagnose
from assertpy2.errors import AssertionFailure, DiffEntry, DiffResult


@dataclasses.dataclass
class _User:
    name: str
    city: str


class _State(enum.Enum):
    CLOSED = "closed"


def _message(actual, expected):
    with pytest.raises(AssertionFailure) as failure:
        assert_that(actual).is_equal_to(expected)
    return str(failure.value)


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
            DiffEntry(path="[0]", actual={"a": 1}, expected={"b": 2}),
            DiffEntry(path="[1]", actual={"b": 2}, expected={"a": 1}),
        ]
        assert_that(diagnose(DiffResult(kind="sequence", entries=entries))).contains("in a different order")

    def test_a_hash_that_raises_something_other_than_type_error_is_left_alone(self):
        # an unhashable value raises TypeError and has a slower route waiting for it. anything else
        # coming out of a user __hash__ is not a shape this understands, so it says nothing
        class Hostile:
            def __hash__(self):
                raise ValueError("boom")

        entries = [
            DiffEntry(path="[0]", actual=Hostile(), expected=1),
            DiffEntry(path="[1]", actual=2, expected=Hostile()),
        ]
        assert_that(diagnose(DiffResult(kind="sequence", entries=entries))).is_none()

    def test_elements_that_can_be_neither_hashed_nor_reprd_are_left_alone(self):
        class Awkward:
            __hash__ = None

            def __repr__(self):
                raise ValueError("boom")

        entries = [
            DiffEntry(path="[0]", actual=Awkward(), expected=1),
            DiffEntry(path="[1]", actual=2, expected=Awkward()),
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
            DiffEntry(path="[0]", actual=Unreprable(), expected=1),
            DiffEntry(path="[1]", actual=2, expected=Unreprable()),
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
