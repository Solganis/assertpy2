import logging
from io import StringIO

import pytest

from assertpy2 import WarningLoggingAdapter, assert_that, assert_warn, match, soft_assertions


class TestNotBasic:
    def test_not_is_none(self):
        assert_that(5).not_.is_none()

    def test_not_is_empty(self):
        assert_that([1, 2]).not_.is_empty()

    def test_not_is_equal_to(self):
        assert_that(5).not_.is_equal_to(10)

    def test_not_is_positive_on_negative(self):
        assert_that(-5).not_.is_positive()

    def test_not_is_alpha(self):
        assert_that("abc123").not_.is_alpha()

    def test_not_is_sorted(self):
        assert_that([3, 1, 2]).not_.is_sorted()

    def test_not_contains(self):
        assert_that([1, 2, 3]).not_.contains(5)

    def test_not_is_in(self):
        assert_that(42).not_.is_in(1, 2, 3)

    def test_not_is_instance_of(self):
        assert_that("hello").not_.is_instance_of(int)

    def test_not_has_length(self):
        assert_that([1, 2]).not_.has_length(5)


class TestNotFailure:
    def test_not_is_positive_on_positive(self):
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            assert_that(5).not_.is_positive()

    def test_not_is_none_on_none(self):
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            assert_that(None).not_.is_none()

    def test_not_is_equal_to_on_equal(self):
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            assert_that(5).not_.is_equal_to(5)

    def test_not_is_empty_on_empty(self):
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            assert_that([]).not_.is_empty()

    def test_not_contains_on_present(self):
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            assert_that([1, 2, 3]).not_.contains(2)

    def test_failure_message_format(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(5).not_.is_positive()
        assert_that(str(exc_info.value)).contains("Expected <5> to NOT satisfy: is_positive()")


class TestNotDescribedAs:
    def test_description_in_error(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(5).described_as("my check").not_.is_positive()
        assert_that(str(exc_info.value)).starts_with("[my check]")

    def test_description_preserved_on_success(self):
        result = assert_that(-5).described_as("my check").not_.is_positive()
        assert_that(result.description).is_equal_to("my check")


class TestNotChaining:
    def test_chain_after_not(self):
        assert_that(5).not_.is_none().is_positive()

    def test_chain_after_not_with_description(self):
        assert_that(5).described_as("val").not_.is_none().is_positive()

    def test_chain_multiple_assertions_after_not(self):
        assert_that("hello").not_.is_empty().is_length(5).is_alpha()


class TestNotSoftAssertions:
    def test_soft_not_collects_error(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(5).not_.is_positive()
            assert_that(None).not_.is_none()
        msg = str(exc_info.value)
        assert_that(msg).contains("is_positive()")
        assert_that(msg).contains("is_none()")

    def test_soft_not_success_does_not_add_error(self):
        with soft_assertions():
            assert_that(-5).not_.is_positive()
            assert_that(5).not_.is_none()

    def test_soft_passing_negation_returns_value(self):
        with soft_assertions():
            builder = assert_that(5).not_.is_equal_to(6)  # negation passes
            value = builder.value  # must not raise on a passing negation
        assert_that(value).is_equal_to(5)

    def test_soft_failing_negation_taints_value(self):
        with pytest.raises(AssertionError), soft_assertions():
            builder = assert_that(5).not_.is_equal_to(5)  # negation fails, error collected
            with pytest.raises(TypeError):
                _ = builder.value

    def test_soft_prior_failure_taint_survives_passing_negation(self):
        with pytest.raises(AssertionError), soft_assertions():
            builder = assert_that(5).is_equal_to(6)  # prior real failure taints .value
            passed = builder.not_.is_equal_to(7)  # a later passing negation keeps the taint
            with pytest.raises(TypeError):
                _ = passed.value

    def test_soft_prior_failure_then_failing_negation_keeps_first_taint(self):
        with pytest.raises(AssertionError), soft_assertions():
            builder = assert_that(5).is_equal_to(6)  # prior failure already taints .value
            failed = builder.not_.is_equal_to(5)  # failing negation: taint already set, guard skips
            with pytest.raises(TypeError):
                _ = failed.value


class TestNotWarnMode:
    def test_warn_not_logs_warning(self):
        capture = StringIO()
        logger = logging.getLogger("test_not_warn")
        handler = logging.StreamHandler(capture)
        logger.addHandler(handler)

        adapted = WarningLoggingAdapter(logger, None)
        assert_warn("hello", logger=adapted).not_.is_alpha()

        out = capture.getvalue()
        capture.close()
        assert_that(out).contains("to NOT satisfy: is_alpha()")

    def test_warn_passing_negation_returns_value(self):
        assert_that(assert_warn(5).not_.is_equal_to(6).value).is_equal_to(5)

    def test_warn_failing_negation_taints_value(self):
        builder = assert_warn(5).not_.is_equal_to(5)  # negation fails, warning logged
        with pytest.raises(TypeError):
            _ = builder.value

    def test_warn_prior_failure_then_failing_negation_keeps_first_taint(self):
        builder = assert_warn(5).is_equal_to(6)  # prior warn failure already taints .value
        failed = builder.not_.is_equal_to(5)  # failing negation: taint already set, guard skips
        with pytest.raises(TypeError):
            _ = failed.value

    def test_warn_not_success_does_not_log(self):
        capture = StringIO()
        logger = logging.getLogger("test_not_warn_success")
        handler = logging.StreamHandler(capture)
        logger.addHandler(handler)

        adapted = WarningLoggingAdapter(logger, None)
        assert_warn("abc123", logger=adapted).not_.is_alpha()

        out = capture.getvalue()
        capture.close()
        assert_that(out).is_empty()


class TestNotAttributes:
    def test_non_callable_attr_passthrough(self):
        builder = assert_that(5).described_as("test")
        negated = builder.not_
        assert_that(negated.val).is_equal_to(5)
        assert_that(negated.description).is_equal_to("test")


class TestNotWithMatchers:
    def test_not_satisfies(self):
        assert_that(-5).not_.satisfies(match.is_positive())

    def test_not_satisfies_failure(self):
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            assert_that(5).not_.satisfies(match.is_positive())

    def test_not_each(self):
        assert_that([1, -2, 3]).not_.each(match.is_positive())


def test_not_rejects_eventually_with_clear_error():
    with pytest.raises(TypeError, match="cannot be negated"):
        assert_that(lambda: 1).not_.eventually()


def test_not_rejects_eventually_sync_with_clear_error():
    with pytest.raises(TypeError, match="cannot be negated"):
        assert_that(lambda: 1).not_.eventually_sync()


def test_not_rejects_described_as_with_clear_error():
    # described_as() configures the chain; negating it produced a bogus "to NOT satisfy" failure
    with pytest.raises(TypeError, match=r"call described_as\(\) before not_"):
        assert_that(1).not_.described_as("desc")


def test_described_as_before_not_keeps_working():
    with pytest.raises(AssertionError, match=r"\[desc\] Expected <1> to NOT satisfy: is_equal_to\(\)"):
        assert_that(1).described_as("desc").not_.is_equal_to(1)


def test_not_rejects_extracting_with_clear_error():
    # extracting() pivots to a new value; negating it raised on success instead of asserting anything
    with pytest.raises(TypeError, match=r"negate the assertion after extracting\(\)"):
        assert_that([{"a": 1}]).not_.extracting("a")


def test_extracting_before_not_keeps_working():
    assert_that([{"a": 1}]).extracting("a").not_.contains(2)


@pytest.mark.parametrize(
    "step", ["filtered_on", "mapped", "flat_mapped", "first", "last", "element", "single", "decoded_as", "at_json_path"]
)
def test_not_rejects_pipeline_transformers_with_clear_error(step):
    # transformers never raise AssertionError, so negating them could only produce a bogus failure
    with pytest.raises(TypeError, match=f"negate the assertion after {step}"):
        getattr(assert_that([1]).not_, step)


def test_pipeline_transformer_before_not_keeps_working():
    assert_that([1, -2, 3]).filtered_on(lambda x: x > 0).not_.is_empty()
    assert_that([10, 20]).first().not_.is_equal_to(20)


def test_hybrid_pivots_stay_negatable():
    # extracting_group / matches_with_groups both assert (pattern must match) and pivot,
    # so negating them is meaningful and stays allowed
    assert_that("abc").not_.matches_with_groups(r"(\d+)")
    assert_that("abc").not_.extracting_group(r"(\d+)", 1)
