"""Direct tests for the helpers that collapse a value before it goes into a failure message.

Everything here was reachable only through an assertion failure, and the messages those produce were
asserted whole, so the thresholds themselves were never pinned: shifting any of them by one still
produced a plausible-looking message. A value one element or one character either side of a boundary
is the only thing that tells them apart.
"""

import collections

import pytest

from assertpy2 import assert_that
from assertpy2.helpers import _both_list_like, _elided_seq_repr, _elided_text_repr, _joined_parts


class TestSequenceElisionBoundaries:
    """A short sequence is printed whole; past either cap only the differing elements are kept.

    Two caps, checked in order: at most 20 elements, and at most 60 characters once rendered. The
    element cap comes first so a long sequence is never rendered just to be measured, which on the
    failure path is the whole value.
    """

    def test_twenty_elements_rendering_to_sixty_characters_is_printed_whole(self):
        seq = [1] * 20
        assert_that(repr(seq)).is_length(60)
        assert_that(_elided_seq_repr(seq, [9] * 20)).is_equal_to(repr(seq))

    def test_twenty_one_elements_are_collapsed(self):
        # the counterpart matches everywhere but the last slot; 21 one-character elements never fit 60
        # characters anyway, so raising the element cap alone cannot change this answer
        assert_that(_elided_seq_repr([*[1] * 20, 2], [1] * 21)).is_equal_to("[.., 2]")

    def test_sixty_one_characters_are_collapsed(self):
        seq = [1] * 19 + [10]
        assert_that(repr(seq)).is_length(61)
        assert_that(_elided_seq_repr(seq, [*[1] * 19, 99])).is_equal_to("[.., 10]")

    def test_a_sequence_longer_than_its_counterpart_does_not_index_past_it(self):
        # the positional fallback pairs by index and has to stop at the shorter side
        assert_that(_elided_seq_repr([7] * 30, [7, 7])).contains("7")

    def test_a_tuple_keeps_its_own_brackets(self):
        actual = (*(1,) * 20, 2)
        assert_that(_elided_seq_repr(actual, (1,) * 21)).is_equal_to("(.., 2)")


class TestTextElisionBoundary:
    def test_three_lines_are_printed_whole(self):
        text = "a\nb\nc"
        assert_that(_elided_text_repr(text, "a\nb\nZ")).is_equal_to(text)

    def test_four_lines_are_collapsed_to_the_changed_ones(self):
        # the cost of a multi-line value is vertical, and the message prints the value twice
        collapsed = _elided_text_repr("a\nb\nc\nd", "a\nZ\nc\nd")
        assert_that(collapsed).is_equal_to(".., line 2: b")


class TestJoinedPartsCap:
    """Collapsing only removes what matched, so a value where nearly everything differs still prints
    in full. The cap on spelled-out parts is what keeps that from becoming a wall of text."""

    def test_five_parts_are_all_spelled_out(self):
        assert_that(_joined_parts([str(index) for index in range(5)], elided=False)).is_equal_to("0, 1, 2, 3, 4")

    def test_the_sixth_part_turns_into_a_count(self):
        assert_that(_joined_parts([str(index) for index in range(6)], elided=False)).is_equal_to(
            "0, 1, 2, 3, 4, ... and 1 more"
        )

    def test_the_count_names_how_many_were_dropped(self):
        assert_that(_joined_parts([str(index) for index in range(9)], elided=False)).is_equal_to(
            "0, 1, 2, 3, 4, ... and 4 more"
        )

    def test_an_elided_prefix_marks_what_matched(self):
        assert_that(_joined_parts(["x"], elided=True, opener="[", closer="]")).is_equal_to("[.., x]")

    def test_an_all_matching_value_is_just_the_marker(self):
        assert_that(_joined_parts([], elided=True, opener="{", closer="}")).is_equal_to("{..}")


class TestElisionReachesTheMessage:
    """The same thresholds, through the failure they exist for, so a change of caller wiring shows up
    here rather than only in the unit tests above."""

    def test_a_long_list_failure_names_only_the_differing_element(self):
        actual, expected = list(range(30)), [*range(29), 99]
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        message = str(exc_info.value)
        assert_that(message).contains("..").contains("29").contains("99")
        assert_that(message).does_not_contain("15")


class TestNamedtuplesAreNotTreatedAsPlainSequences:
    """A namedtuple carries field names, so it is compared and printed field-wise.  Dropping either
    side's guard would send a pair down the positional path, where the failure reads as a bare tuple
    and the field that changed is identified by index instead of by name."""

    _Point = collections.namedtuple("_Point", ["x", "y"])

    def test_a_namedtuple_pair_is_not_list_like(self):
        assert_that(_both_list_like(self._Point(1, 2), self._Point(1, 3))).is_false()

    def test_a_namedtuple_on_one_side_alone_is_enough(self):
        assert_that(_both_list_like(self._Point(1, 2), (1, 3))).is_false()
        assert_that(_both_list_like((1, 2), self._Point(1, 3))).is_false()

    def test_a_plain_tuple_pair_is_list_like(self):
        assert_that(_both_list_like((1, 2), (1, 3))).is_true()

    def test_the_failure_names_the_field_not_the_index(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(self._Point(1, 2)).is_equal_to(self._Point(1, 3))
        assert_that(str(exc_info.value)).contains("y=2").contains("y=3")
