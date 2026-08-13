import contextlib

import pytest

from assertpy2 import AssertionFailure, assert_that, fail, soft_assertions, soft_fail


def test_success():
    with soft_assertions():
        assert_that("foo").is_length(3)
        assert_that("foo").is_not_empty()
        assert_that("foo").is_true()
        assert_that("foo").is_alpha()
        assert_that("123").is_digit()
        assert_that("foo").is_lower()
        assert_that("FOO").is_upper()
        assert_that("foo").is_equal_to("foo")
        assert_that("foo").is_not_equal_to("bar")
        assert_that("foo").is_equal_to_ignoring_case("FOO")
        assert_that({"a": 1}).has_a(1)


def test_failure():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that("foo").is_length(4)
        assert_that("foo").is_empty()
        assert_that("foo").is_false()
        assert_that("foo").is_digit()
        assert_that("123").is_alpha()
        assert_that("foo").is_upper()
        assert_that("FOO").is_lower()
        assert_that("foo").is_equal_to("bar")
        assert_that("foo").is_not_equal_to("foo")
        assert_that("foo").is_equal_to_ignoring_case("BAR")
        assert_that({"a": 1}).has_a(2)
        assert_that({"a": 1}).has_foo(1)
    out = str(exc_info.value)
    assert_that(out).contains("Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).contains("Expected <foo> to be empty string, but was not.")
    assert_that(out).contains("Expected <foo> to be <False>, but was not.")
    assert_that(out).contains("Expected <foo> to contain only digits, but did not.")
    assert_that(out).contains("Expected <123> to contain only alphabetic chars, but did not.")
    assert_that(out).contains("Expected <foo> to contain only uppercase chars, but did not.")
    assert_that(out).contains("Expected <FOO> to contain only lowercase chars, but did not.")
    assert_that(out).contains("Expected <foo> to be equal to <bar>, but was not.")
    assert_that(out).contains("Expected <foo> to be not equal to <foo>, but was.")
    assert_that(out).contains("Expected <foo> to be case-insensitive equal to <BAR>, but was not.")
    assert_that(out).contains("Expected <1> to be equal to <2> on key <a>, but was not.")
    assert_that(out).contains("Expected key <foo>, but val has no key <foo>.")


def test_failure_chain():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that("foo").is_length(4).is_empty().is_false().is_digit().is_upper().is_equal_to("bar").is_not_equal_to(
            "foo"
        ).is_equal_to_ignoring_case("BAR")
    out = str(exc_info.value)
    assert_that(out).contains("Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).contains("Expected <foo> to be empty string, but was not.")
    assert_that(out).contains("Expected <foo> to be <False>, but was not.")
    assert_that(out).contains("Expected <foo> to contain only digits, but did not.")
    assert_that(out).contains("Expected <foo> to contain only uppercase chars, but did not.")
    assert_that(out).contains("Expected <foo> to be equal to <bar>, but was not.")
    assert_that(out).contains("Expected <foo> to be not equal to <foo>, but was.")
    assert_that(out).contains("Expected <foo> to be case-insensitive equal to <BAR>, but was not.")


def test_expected_exception_success():
    with soft_assertions():
        assert_that(func_err).raises(RuntimeError).when_called_with("foo").is_equal_to("err")


def test_expected_exception_failure():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that(func_err).raises(RuntimeError).when_called_with("foo").is_equal_to("bar")
        assert_that(func_ok).raises(RuntimeError).when_called_with("baz")
    out = str(exc_info.value)
    assert_that(out).contains("Expected <err> to be equal to <bar>, but was not.")
    assert_that(out).contains("Expected <func_ok> to raise <RuntimeError> when called with ('baz').")


def func_ok(arg):
    pass


def func_err(arg):
    raise RuntimeError("err")


def test_fail():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        fail()
    out = str(exc_info.value)
    assert_that(out).is_equal_to("Fail!")


def test_fail_with_msg():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        fail("foobar")
    out = str(exc_info.value)
    assert_that(out).is_equal_to("Fail: foobar!")


def test_fail_with_soft_failing_asserts():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that("foo").is_length(4)
        assert_that("foo").is_empty()
        fail("foobar")
        assert_that("foo").is_not_equal_to("foo")
        assert_that("foo").is_equal_to_ignoring_case("BAR")
    out = str(exc_info.value)
    assert_that(out).is_equal_to("Fail: foobar!")
    assert_that(out).does_not_contain("Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).does_not_contain("Expected <foo> to be empty string, but was not.")
    assert_that(out).does_not_contain("Expected <foo> to be not equal to <foo>, but was.")
    assert_that(out).does_not_contain("Expected <foo> to be case-insensitive equal to <BAR>, but was not.")


def test_double_fail():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        fail()
        fail("foobar")
    out = str(exc_info.value)
    assert_that(out).is_equal_to("Fail!")


def test_nested():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that("a").is_equal_to("A")
        with soft_assertions():
            assert_that("b").is_equal_to("B")
            with soft_assertions():
                assert_that("c").is_equal_to("C")
            assert_that("b").is_equal_to("B2")
        assert_that("a").is_equal_to("A2")
    out = str(exc_info.value)
    assert_that(out).contains("1. Expected <a> to be equal to <A>, but was not.")
    assert_that(out).contains("2. Expected <b> to be equal to <B>, but was not.")
    assert_that(out).contains("3. Expected <c> to be equal to <C>, but was not.")
    assert_that(out).contains("4. Expected <b> to be equal to <B2>, but was not.")
    assert_that(out).contains("5. Expected <a> to be equal to <A2>, but was not.")


def test_raises_no_exception_chaining():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that(lambda x: 1 / x).raises(ZeroDivisionError).when_called_with(1).is_equal_to("dog").matches("cat")
    out = str(exc_info.value)
    assert_that(out).contains("Expected <<lambda>> to raise <ZeroDivisionError> when called with (1).")
    assert_that(out).does_not_contain("TypeError")


def test_raises_wrong_exception_chaining():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that({}.__getitem__).raises(RuntimeError).when_called_with("a").contains("dog")
    out = str(exc_info.value)
    assert_that(out).contains("Expected <__getitem__> to raise <RuntimeError>")
    assert_that(out).contains("but raised <KeyError>")
    assert_that(out).does_not_contain("TypeError")


def test_raises_mixed_chaining():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that(lambda x: 1 / x).raises(ZeroDivisionError).when_called_with(1).is_equal_to("dog")
        assert_that({}.__getitem__).raises(RuntimeError).when_called_with("a").contains("dog")
        assert_that(lambda x: 1 / x).raises(ZeroDivisionError).when_called_with(0).matches("dog")
    out = str(exc_info.value)
    assert_that(out).contains("1.")
    assert_that(out).contains("2.")
    assert_that(out).contains("3.")
    assert_that(out).does_not_contain("TypeError")


def test_recursive_nesting():
    def recurs(i):
        if i <= 0:
            return
        with soft_assertions():
            recurs(i - 1)
            assert_that(i).is_equal_to(7)

    try:
        recurs(10)
    except AssertionError as exc:
        out = str(exc)
        assert_that(out).contains("1. Expected <1> to be equal to <7>, but was not.")
        assert_that(out).contains("2. Expected <2> to be equal to <7>, but was not.")
        assert_that(out).contains("3. Expected <3> to be equal to <7>, but was not.")
        assert_that(out).contains("4. Expected <4> to be equal to <7>, but was not.")
        assert_that(out).contains("5. Expected <5> to be equal to <7>, but was not.")
        assert_that(out).contains("6. Expected <6> to be equal to <7>, but was not.")


class TestSoftFailuresCarryTheirDiff:
    """A collected failure keeps the paths its hard counterpart would have shown."""

    def test_nested_difference_names_its_path(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that({"a": {"b": 1}}).is_equal_to({"a": {"b": 2}})
        assert_that(str(exc_info.value)).contains("a.b: 1 != 2")

    def test_missing_item_is_named_without_its_empty_counterpart(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that([1, 2]).contains(3)
        message = str(exc_info.value)
        assert_that(message).contains("missing: 3")
        assert_that(message).does_not_contain("None")

    def test_extra_item_is_named_without_its_empty_counterpart(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that({1, 2, 3}).is_equal_to({1, 2})
        message = str(exc_info.value)
        assert_that(message).contains("extra: 3")
        assert_that(message).does_not_contain("None")

    def test_many_differences_are_capped(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that({f"k{i}": i for i in range(9)}).is_equal_to({f"k{i}": -i for i in range(9)})
        # asserted on the indented diff lines, not on a substring: the headline carries a cap of its
        # own whose wording is identical, so a plain contains() would pass without this code running
        diff_lines = [line for line in str(exc_info.value).splitlines() if line.startswith("   ")]
        # k0 matches (0 == -0), so eight paths differ: five are named and three stay counted
        assert_that(diff_lines).is_length(6)
        assert_that(diff_lines[-1].strip()).is_equal_to("... and 3 more")

    def test_a_scalar_failure_adds_no_line(self):
        # the header already carries both values, so a path of "." would only repeat them
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(1).is_equal_to(2)
        assert_that(str(exc_info.value).splitlines()).is_length(2)


class TestTheAggregateHandsBackWhatItCollected:
    """A soft block used to flatten every failure into one string at its boundary: the collector held
    tuples of (group, location, message, diff) and the raise turned them into a numbered list. The text
    is unchanged, and the parts it was rendered from now ride on the exception."""

    def test_the_aggregate_carries_one_record_per_collected_failure(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that({"a": 1}).is_equal_to({"a": 2})
            assert_that("foo").is_length(4)
        assert_that(failure.value.failures).is_length(2)
        assert_that([outcome.message for outcome in failure.value.failures]).is_equal_to(
            [
                "Expected <{'a': 1}> to be equal to <{'a': 2}>, but was not.",
                "Expected <foo> to be of length <4>, but was <3>.",
            ]
        )

    def test_each_record_keeps_the_structure_the_message_had_flattened(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that({"a": 1}).is_equal_to({"a": 2})
        collected = failure.value.failures[0]
        assert_that(collected.actual).is_equal_to({"a": 1})
        assert_that(collected.expected).is_equal_to({"a": 2})
        assert_that(collected.diff.kind).is_equal_to("dict")
        assert_that([step.value for step in collected.diff.entries[0].steps]).is_equal_to(["a"])

    def test_a_record_knows_where_it_was_collected(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
        location = failure.value.failures[0].location
        assert_that(location[0]).ends_with("test_soft.py")
        assert_that(location[1]).is_instance_of(int)

    def test_a_grouped_failure_keeps_its_label(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions() as sa:
            with sa.group("Body"):
                assert_that(1).is_equal_to(2)
            assert_that(3).is_equal_to(4)
        assert_that([outcome.group for outcome in failure.value.failures]).is_equal_to(["Body", None])

    def test_a_negated_failure_is_collected_as_a_record_too(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(5).not_.is_positive()
        collected = failure.value.failures[0]
        assert_that(collected.message).is_equal_to("Expected <5> to NOT satisfy: is_positive()")
        assert_that(collected.actual).is_equal_to(5)

    def test_soft_fail_is_collected_as_a_record_too(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            soft_fail("manual")
        assert_that(failure.value.failures[0].message).is_equal_to("Fail: manual!")

    def test_a_failure_that_was_raised_carries_no_collection(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(1).is_equal_to(2)
        assert_that(failure.value.failures).is_empty()

    def test_a_negation_that_held_leaves_nothing_behind(self):
        # the rollback is a slice of the collected list, which only works while the sink stays an append
        with soft_assertions():
            assert_that(-5).not_.is_positive()


class TestAnErrorOutOfTheBlockKeepsWhatWasCollected:
    """An exception from inside the block still wins, and the failures gathered before it survive.

    They used to be dropped on the floor. A soft block exists to gather failures, so a timeout three
    assertions in took all three with it, and the reader saw only the timeout. Reported by an external
    review of the shipped library.

    A note rather than a replacement or an `ExceptionGroup`: the type and the message stay exactly what
    the block raised, so `except TimeoutError` around it keeps working and the traceback still points at
    what actually stopped the test.
    """

    def test_the_exception_is_unchanged(self):
        with pytest.raises(ValueError, match="service did not answer") as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            raise ValueError("service did not answer")
        assert_that(type(failure.value)).is_equal_to(ValueError)
        assert_that(str(failure.value)).is_equal_to("service did not answer")

    def test_the_note_is_part_of_what_pytest_matches_against(self):
        """A consequence worth stating rather than discovering: `pytest.raises(match=...)` searches the
        notes as well as the message, so an anchored pattern that used to end at the message no longer
        matches. The message itself is untouched, which is what `str(exc)` and every handler sees.
        """
        with pytest.raises(ValueError, match="soft assertion failures") as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            raise ValueError("boom")
        assert_that(str(failure.value)).described_as("the message stays the message").is_equal_to("boom")

    def test_the_collected_failures_travel_with_it(self):
        with pytest.raises(ValueError) as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            assert_that("a").is_equal_to("b")
            raise ValueError("boom")
        notes = getattr(failure.value, "__notes__", [])
        assert_that(notes).is_length(1)
        assert_that(notes[0]).contains("soft assertion failures:")
        assert_that(notes[0]).contains("<1> to be equal to <2>").contains("<a> to be equal to <b>")

    def test_a_block_that_collected_nothing_adds_no_note(self):
        with pytest.raises(ValueError) as failure, soft_assertions():
            assert_that(1).is_equal_to(1)
            raise ValueError("boom")
        assert_that(getattr(failure.value, "__notes__", [])).is_empty()

    def test_the_next_block_starts_clean(self):
        with contextlib.suppress(ValueError), soft_assertions():
            assert_that(1).is_equal_to(2)
            raise ValueError("boom")
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that("x").is_equal_to("y")
        assert_that(str(failure.value)).does_not_contain("<1> to be equal to <2>")

    def test_python_310_keeps_them_reachable_without_add_note(self):
        """`add_note` arrived in 3.11 and this package supports 3.10.

        There the note cannot be printed by the interpreter's own traceback, but the failures can still
        travel on the exception, and losing them is the thing this whole branch exists to stop. The
        absence is emulated rather than skipped, so the branch is covered on every interpreter.
        """

        class WithoutAddNoteError(ValueError):
            add_note = None  # what 3.10 looks like to `getattr`

        with pytest.raises(WithoutAddNoteError) as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            raise WithoutAddNoteError("boom")
        notes = getattr(failure.value, "__notes__", [])
        assert_that(notes).is_length(1)
        assert_that(notes[0]).contains("<1> to be equal to <2>")
        assert_that(str(failure.value)).described_as("the message is still the message").is_equal_to("boom")

    def test_only_the_outermost_block_annotates(self):
        # a nested block hands its failures upward, so annotating on the way out of the inner one would
        # report them twice and empty the outer block's own collection
        with pytest.raises(ValueError) as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            with soft_assertions():
                assert_that(3).is_equal_to(4)
            raise ValueError("boom")
        notes = getattr(failure.value, "__notes__", [])
        assert_that(notes).is_length(1)
        assert_that(notes[0]).contains("<1> to be equal to <2>").contains("<3> to be equal to <4>")
