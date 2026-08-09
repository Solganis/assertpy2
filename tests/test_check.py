"""`check()` runs an assertion for its verdict instead of for its failure.

The library had three non-raising exits before this and none of them was a result: warn mode writes to
a logger and returns the builder, a soft block collects into a private contextvar, and a matcher's
`matches()` answers a bare bool with no message, values or diff. This is the one that hands the caller
what the assertion decided.
"""

import logging

import pytest

from assertpy2 import AssertionFailure, AssertionOutcome, assert_that, assert_warn, soft_assertions


class TestTheVerdictComesBackInsteadOfBeingRaised:
    def test_a_passing_assertion_answers_truthy(self):
        outcome = assert_that(5).check().is_positive()
        assert_that(outcome.passed).is_true()
        assert_that(bool(outcome)).is_true()

    def test_a_failing_assertion_answers_falsy_and_does_not_raise(self):
        outcome = assert_that(-5).check().is_positive()
        assert_that(outcome.passed).is_false()
        assert_that(bool(outcome)).is_false()

    def test_a_passing_outcome_carries_the_value_and_no_message(self):
        outcome = assert_that([1, 2]).check().is_not_empty()
        assert_that(outcome.actual).is_equal_to([1, 2])
        assert_that(outcome.message).is_empty()

    def test_a_failing_outcome_carries_everything_the_exception_would_have(self):
        outcome = assert_that({"a": 1}).check().is_equal_to({"a": 2})
        assert_that(outcome.message).is_equal_to("Expected <{'a': 1}> to be equal to <{'a': 2}>, but was not.")
        assert_that(outcome.actual).is_equal_to({"a": 1})
        assert_that(outcome.expected).is_equal_to({"a": 2})
        assert_that(outcome.diff.kind).is_equal_to("dict")
        assert_that([entry.path for entry in outcome.diff.entries]).is_equal_to(["a"])

    def test_the_description_prefixes_the_message_as_it_would_a_raised_one(self):
        outcome = assert_that(-5).described_as("the balance").check().is_positive()
        assert_that(outcome.message).starts_with("[the balance] ")

    def test_one_call_composes_one_failure_however_many_parts_it_names(self):
        # the invariant the sink rests on: every `self.error(...)` in the package returns immediately,
        # so an assertion that found several problems still reports them as one message
        outcome = assert_that([1, 2]).check().contains(9, 8)
        assert_that(outcome.passed).is_false()
        assert_that(outcome.message).contains("9")
        assert_that(outcome.message).contains("8")


class TestTheBuilderIsUnchangedAfterwards:
    def test_the_next_assertion_on_the_same_builder_still_raises(self):
        builder = assert_that(-5)
        builder.check().is_positive()
        with pytest.raises(AssertionFailure):
            builder.is_positive()

    def test_a_failed_check_does_not_taint_the_value(self):
        # soft and warn refuse `.value` after a failure, because a collected failure means the value was
        # never verified. a check was never an assertion about it: the caller asked a question
        builder = assert_that(-5)
        builder.check().is_positive()
        assert_that(builder.value).is_equal_to(-5)

    def test_a_bad_argument_still_raises_rather_than_becoming_a_verdict(self):
        # TypeError means the call itself is wrong, which is not something the value can be at fault for
        with pytest.raises(TypeError):
            assert_that([1]).check().all_fields_satisfy(42)

    def test_the_mode_is_put_back_even_when_the_call_raises(self):
        builder = assert_that([1])
        with pytest.raises(TypeError):
            builder.check().all_fields_satisfy(42)
        assert_that(builder.kind).is_none()


class TestCheckInsideTheOtherModes:
    def test_a_check_inside_a_soft_block_collects_nothing(self):
        with soft_assertions():
            outcome = assert_that(-5).check().is_positive()
            assert_that(outcome.passed).is_false()

    def test_a_soft_assertion_after_a_check_still_collects(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(-5).check().is_positive()
            assert_that(-5).is_positive()
        assert_that(str(failure.value)).contains("to be greater than <0>")

    def test_a_check_in_warn_mode_answers_instead_of_logging(self, caplog):
        with caplog.at_level(logging.WARNING, logger="assertpy2"):
            outcome = assert_warn(-5).check().is_positive()
        assert_that(outcome.passed).is_false()
        assert_that(caplog.text).is_empty()


class TestNegationIsProxiedRatherThanRefused:
    def test_a_negation_that_holds_answers_truthy(self):
        assert_that(assert_that(-5).check().not_.is_positive().passed).is_true()

    def test_a_negation_that_fails_carries_its_own_message(self):
        outcome = assert_that(5).check().not_.is_positive()
        assert_that(outcome.passed).is_false()
        assert_that(outcome.message).is_equal_to("Expected <5> to NOT satisfy: is_positive()")
        assert_that(outcome.actual).is_equal_to(5)

    def test_a_negation_leaves_no_collected_failure_behind(self):
        # the inner assertion lands in the sink before the negation reads it, and a negation that held
        # has to clear it or the next check would report a failure that already answered
        builder = assert_that(-5)
        builder.check().not_.is_positive()
        assert_that(builder.check().is_negative().passed).is_true()


class TestTheReturnedRecordIsThePublicType:
    def test_it_is_the_exported_outcome(self):
        assert_that(assert_that(5).check().is_positive()).is_instance_of(AssertionOutcome)

    def test_a_non_callable_attribute_is_handed_straight_back(self):
        assert_that(assert_that(5).check().val).is_equal_to(5)
