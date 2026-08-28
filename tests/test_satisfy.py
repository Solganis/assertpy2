import pytest

from assertpy2 import AssertionFailure, assert_that, match


class TestAnySatisfy:
    def test_any_satisfy_matcher(self):
        assert_that([1, -2, 3]).any_satisfy(match.is_negative())

    def test_any_satisfy_callable(self):
        assert_that([1, 2, 3]).any_satisfy(lambda x: x > 2)

    def test_any_satisfy_first_item(self):
        assert_that([10, 1, 2]).any_satisfy(match.greater_than(5))

    def test_any_satisfy_last_item(self):
        assert_that([1, 2, 10]).any_satisfy(match.greater_than(5))

    def test_any_satisfy_matcher_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).any_satisfy(match.is_negative())
        assert_that(str(exc_info.value)).contains("Expected any item to satisfy")

    def test_any_satisfy_callable_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).any_satisfy(lambda x: x > 10)
        assert_that(str(exc_info.value)).contains("Expected any item to satisfy")

    def test_any_satisfy_not_iterable_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).any_satisfy(match.is_positive())
        assert_that(str(exc_info.value)).is_equal_to("val must be iterable, but was <42> (int)")

    def test_any_satisfy_bad_matcher_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that([1, 2]).any_satisfy("not a matcher")
        assert_that(str(exc_info.value)).is_equal_to(
            "given matcher arg must be a Matcher or a callable, but was <'not a matcher'> (str)"
        )

    def test_any_satisfy_empty_iterable_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([]).any_satisfy(match.is_positive())
        assert_that(str(exc_info.value)).contains("Expected any item to satisfy")


class TestAllSatisfy:
    def test_all_satisfy_matcher(self):
        assert_that([1, 2, 3]).all_satisfy(match.is_positive())

    def test_all_satisfy_callable(self):
        assert_that([2, 4, 6]).all_satisfy(lambda x: x % 2 == 0)

    def test_all_satisfy_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, -2, 3]).all_satisfy(match.is_positive())
        assert_that(str(exc_info.value)).contains("Expected all items to satisfy")
        assert_that(str(exc_info.value)).contains("index 1")

    def test_all_satisfy_empty_iterable(self):
        assert_that([]).all_satisfy(match.is_positive())


class TestNoneSatisfy:
    def test_none_satisfy_matcher(self):
        assert_that([1, 2, 3]).none_satisfy(match.is_negative())

    def test_none_satisfy_callable(self):
        assert_that([1, 2, 3]).none_satisfy(lambda x: x < 0)

    def test_none_satisfy_matcher_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, -2, 3]).none_satisfy(match.is_negative())
        assert_that(str(exc_info.value)).contains("Expected no item to satisfy")
        assert_that(str(exc_info.value)).contains("index 1")
        assert_that(str(exc_info.value)).contains("-2")

    def test_none_satisfy_callable_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).none_satisfy(lambda x: x == 2)
        assert_that(str(exc_info.value)).contains("Expected no item to satisfy")
        assert_that(str(exc_info.value)).contains("index 1")

    def test_none_satisfy_not_iterable_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).none_satisfy(match.is_positive())
        assert_that(str(exc_info.value)).is_equal_to("val must be iterable, but was <42> (int)")

    def test_none_satisfy_bad_matcher_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that([1]).none_satisfy("not a matcher")
        assert_that(str(exc_info.value)).is_equal_to(
            "given matcher arg must be a Matcher or a callable, but was <'not a matcher'> (str)"
        )

    def test_none_satisfy_empty_iterable(self):
        assert_that([]).none_satisfy(match.is_positive())


class TestAnySatisfyShowsWhatItExamined:
    """The universal sibling lists every failure; "none did" left the reader to fetch the items."""

    def test_the_examined_items_reach_the_message(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2]).any_satisfy(match.greater_than(9))
        exc = exc_info.value
        assert_that(str(exc)).contains("none of the 2 did")
        assert_that([entry.path for entry in exc.diff.entries]).is_equal_to(["[0]", "[1]"])
        assert_that([entry.actual for entry in exc.diff.entries]).is_equal_to([1, 2])

    def test_a_callable_predicate_is_described_too(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2]).any_satisfy(lambda item: item > 9)
        assert_that(str(exc_info.value)).contains("a lambda predicate")

    def test_an_empty_subject_still_reports_cleanly(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([]).any_satisfy(lambda item: True)
        assert_that(str(exc_info.value)).contains("none of the 0 did")


class TestStructuredPayloadOfTheSatisfiesFamily:
    """`AssertionFailure` carries `actual`, `expected` and a `diff` for every assertion in this
    family, and it is a documented channel the pytest plugin and Allure both render.  Nothing read it
    here: every test asserted on the message text, so the whole payload could be built from the wrong
    values and no test would notice.
    """

    @staticmethod
    def _payload(fn):
        with pytest.raises(AssertionFailure) as exc_info:
            fn()
        failure = exc_info.value
        entries = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
        return failure.actual, failure.expected, failure.diff.kind, entries

    def test_satisfies_reports_the_value_and_the_description(self):
        actual, expected, kind, entries = self._payload(lambda: assert_that(5).satisfies(match.greater_than(10)))
        assert_that(actual).is_equal_to(5)
        assert_that(expected).is_equal_to("a value greater than <10>")
        assert_that(kind).is_equal_to("match")
        assert_that(entries).is_equal_to([(".", 5, "a value greater than <10>")])

    def test_all_fields_satisfy_names_the_offending_field(self):
        actual, expected, kind, entries = self._payload(
            lambda: assert_that({"a": 1, "b": -2}).all_fields_satisfy(match.is_positive())
        )
        assert_that(actual).is_equal_to({"a": 1, "b": -2})
        assert_that(expected).is_equal_to("a positive value")
        assert_that(kind).is_equal_to("match")
        assert_that(entries).is_equal_to([("b", -2, "a positive value")])

    def test_has_no_none_fields_names_the_none_field(self):
        actual, expected, _kind, entries = self._payload(lambda: assert_that({"a": 1, "b": None}).has_no_none_fields())
        assert_that(actual).is_equal_to({"a": 1, "b": None})
        assert_that(expected).is_equal_to("a non-None value")
        assert_that(entries).is_equal_to([("b", None, "a non-None value")])

    def test_each_reports_the_failing_item_not_the_whole_sequence(self):
        actual, expected, _kind, entries = self._payload(lambda: assert_that([1, -2, 3]).each(match.is_positive()))
        assert_that(actual).is_equal_to(-2)
        assert_that(expected).is_equal_to("a positive value")
        assert_that(entries).is_equal_to([("[1]", -2, "a positive value")])

    def test_all_satisfy_reports_the_failing_item(self):
        actual, _expected, _kind, entries = self._payload(lambda: assert_that([1, -2]).all_satisfy(match.is_positive()))
        assert_that(actual).is_equal_to(-2)
        assert_that(entries).is_equal_to([("[1]", -2, "a positive value")])

    def test_any_satisfy_lists_every_item_that_missed(self):
        actual, expected, _kind, entries = self._payload(
            lambda: assert_that([1, 2, 3]).any_satisfy(match.greater_than(10))
        )
        assert_that(actual).is_equal_to([1, 2, 3])
        assert_that(expected).is_equal_to("a value greater than <10>")
        assert_that(_kind).is_equal_to("match")
        assert_that(entries).is_equal_to(
            [
                ("[0]", 1, "a value greater than <10>"),
                ("[1]", 2, "a value greater than <10>"),
                ("[2]", 3, "a value greater than <10>"),
            ]
        )

    def test_any_satisfy_caps_the_listed_items(self):
        _actual, _expected, _kind, entries = self._payload(
            lambda: assert_that(list(range(9))).any_satisfy(match.greater_than(100))
        )
        assert_that(entries).is_length(5)
        assert_that([path for path, _, _ in entries]).is_equal_to(["[0]", "[1]", "[2]", "[3]", "[4]"])

    def test_matches_structure_reports_the_spec_as_expected(self):
        actual, expected, _kind, entries = self._payload(
            lambda: assert_that({"a": 1}).matches_structure({"a": match.greater_than(10)})
        )
        assert_that(actual).is_equal_to({"a": 1})
        assert_that(expected).contains_key("a")
        assert_that(entries).is_equal_to([("a", 1, "a value greater than <10>")])

    def test_satisfies_exactly_reports_every_matcher_as_expected(self):
        actual, expected, _kind, entries = self._payload(
            lambda: assert_that([1, 2]).satisfies_exactly(match.is_positive(), match.greater_than(10))
        )
        assert_that(actual).is_equal_to([1, 2])
        assert_that(expected).is_equal_to(["a positive value", "a value greater than <10>"])
        assert_that(entries).is_equal_to([("[1]", 2, "a value greater than <10>")])

    def test_satisfies_exactly_in_any_order_pairs_extra_with_missing(self):
        actual, expected, kind, entries = self._payload(
            lambda: assert_that([1, 2]).satisfies_exactly_in_any_order(match.greater_than(10), match.is_positive())
        )
        assert_that(actual).is_equal_to([1, 2])
        assert_that(expected).is_equal_to(["a value greater than <10>", "a positive value"])
        assert_that(kind).is_equal_to("contains")
        assert_that(entries).is_equal_to([("extra", 2, None), ("missing", None, "a value greater than <10>")])

    def test_zip_satisfies_reports_the_two_operands(self):
        actual, expected, _kind, entries = self._payload(
            lambda: assert_that([1, 2]).zip_satisfies([1, 99], lambda left, right: left == right)
        )
        assert_that(actual).is_equal_to([1, 2])
        assert_that(expected).is_equal_to([1, 99])
        assert_that(entries).is_equal_to([("[1]", 2, 99)])


class TestLengthMismatchIsItsOwnFailure:
    """The pairing walks are strict on length: a shorter sequence must be reported as a length
    problem, not silently truncated into a pass over the common prefix."""

    def test_satisfies_exactly_rejects_too_few_items(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1]).satisfies_exactly(match.is_positive(), match.is_positive())
        assert_that(exc_info.value.actual).is_equal_to([1])
        assert_that(exc_info.value.expected).is_length(2)

    def test_satisfies_exactly_rejects_too_many_items(self):
        with pytest.raises(AssertionFailure):
            assert_that([1, 2, 3]).satisfies_exactly(match.is_positive(), match.is_positive())

    def test_zip_satisfies_rejects_a_shorter_other(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, 2]).zip_satisfies([1], lambda left, right: left == right)
        assert_that(exc_info.value.actual).is_equal_to([1, 2])

    def test_zip_satisfies_rejects_a_longer_other(self):
        with pytest.raises(AssertionFailure):
            assert_that([1]).zip_satisfies([1, 2], lambda left, right: left == right)


class TestFailureMessagesDescribeTheRightThing:
    """Each message interpolates a description built from the matcher and the value that failed.
    Handing either call the wrong argument still produces a well-formed sentence, so only a test that
    reads the sentence catches it."""

    def test_satisfies_names_the_matcher_and_the_value(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(5).satisfies(match.greater_than(10))
        assert_that(str(exc_info.value)).contains("a value greater than <10>").contains("<5>")

    def test_satisfies_with_a_callable_names_the_predicate_and_the_value(self):
        # the callable branch raises a plain AssertionError: only the matcher branches carry the structured payload
        with pytest.raises(AssertionError) as exc_info:
            assert_that(5).satisfies(lambda value: value > 10)
        assert_that(str(exc_info.value)).contains("<5>").contains("lambda")

    def test_none_satisfy_names_the_matcher_and_the_offending_item(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 20]).none_satisfy(match.greater_than(10))
        message = str(exc_info.value)
        assert_that(message).contains("a value greater than <10>")
        assert_that(message).contains("index 1").contains("<20>")

    def test_each_names_the_matcher_and_the_offending_item(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, -2]).each(match.is_positive())
        message = str(exc_info.value)
        assert_that(message).contains("a positive value")
        assert_that(message).contains("<-2>")

    def test_each_with_a_callable_names_the_index_and_the_item(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, -2]).each(lambda item: item > 0)
        assert_that(str(exc_info.value)).contains("index 1", "<-2>", "a lambda predicate")

    def test_none_satisfy_with_a_callable_names_the_predicate(self):
        # the callable branch describes through the shared helper, not the matcher protocol, and had no test
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 20]).none_satisfy(lambda item: item > 10)
        assert_that(str(exc_info.value)).contains("lambda").contains("index 1").contains("<20>")


class TestARefusalNamesWhatItRefused:
    """The value in a refusal is the whole diagnostic: without it the reader is told a type is wrong
    and not which one. Every test here matched the wording alone, so the value could have been anything.
    """

    def test_satisfies_names_the_argument(self):
        with pytest.raises(TypeError, match=r"given matcher arg must be a Matcher or a callable, but was <42> \(int\)"):
            assert_that(5).satisfies(42)

    def test_each_names_the_value_it_could_not_walk(self):
        with pytest.raises(TypeError, match=r"val must be iterable, but was <42> \(int\)"):
            assert_that(42).each(match.is_positive())

    def test_each_names_the_argument(self):
        with pytest.raises(TypeError, match=r"given matcher arg must be a Matcher or a callable, but was <42> \(int\)"):
            assert_that([1]).each(42)

    def test_matches_structure_names_the_value(self):
        with pytest.raises(TypeError, match=r"attrs instance, but was <42> \(int\)"):
            assert_that(42).matches_structure({"a": match.is_positive()})

    def test_matches_structure_names_the_spec(self):
        with pytest.raises(TypeError, match=r"given spec arg must be a dict, but was <42> \(int\)"):
            assert_that({"a": 1}).matches_structure(42)


class TestWhichValuesAFailureNames:
    """`actual_provided` and `has_expected` decide whether a report prints the values block at all.

    They cannot be read off `.actual`: a failure that names nothing still reports the builder's value
    there, because that is the default. Only the record says which side the assertion meant.
    """

    @staticmethod
    def _named(fn):
        with pytest.raises(AssertionFailure) as exc_info:
            fn()
        outcome = exc_info.value._outcome
        return outcome.actual_provided, outcome.has_expected

    @pytest.mark.parametrize(
        "case",
        [
            lambda: assert_that(5).satisfies(match.greater_than(10)),
            lambda: assert_that({"a": 1}).all_fields_satisfy(match.greater_than(10)),
            lambda: assert_that({"a": 1}).matches_structure({"a": match.greater_than(10)}),
            lambda: assert_that([1]).any_satisfy(match.greater_than(10)),
            lambda: assert_that([1, 2]).satisfies_exactly(match.is_positive(), match.greater_than(10)),
            lambda: assert_that([1, 2]).satisfies_exactly_in_any_order(match.greater_than(10), match.is_positive()),
            lambda: assert_that([1, 2]).zip_satisfies([1, 99], lambda left, right: left == right),
        ],
        ids=["satisfies", "all_fields_satisfy", "matches_structure", "any_satisfy", "exactly", "any_order", "zip"],
    )
    def test_every_failure_names_both_sides(self, case):
        assert_that(self._named(case)).is_equal_to((True, True))


class TestALengthMismatchCarriesItsOwnPayload:
    """A length mismatch never reaches the pairing walk, so it builds its own values, and every test
    of it read the message and nothing else.
    """

    @staticmethod
    def _payload(fn):
        with pytest.raises(AssertionFailure) as exc_info:
            fn()
        failure = exc_info.value
        outcome = failure._outcome
        return failure.actual, failure.expected, (outcome.actual_provided, outcome.has_expected)

    def test_satisfies_exactly_names_the_value_and_every_matcher(self):
        actual, expected, named = self._payload(
            lambda: assert_that([1]).satisfies_exactly(match.is_positive(), match.greater_than(10))
        )
        assert_that(actual).is_equal_to([1])
        assert_that(expected).is_equal_to(["a positive value", "a value greater than <10>"])
        assert_that(named).is_equal_to((True, True))

    def test_the_any_order_twin_names_them_too(self):
        actual, expected, named = self._payload(
            lambda: assert_that([1]).satisfies_exactly_in_any_order(match.is_positive(), match.greater_than(10))
        )
        assert_that(actual).is_equal_to([1])
        assert_that(expected).is_equal_to(["a positive value", "a value greater than <10>"])
        assert_that(named).is_equal_to((True, True))

    def test_zip_satisfies_names_both_operands(self):
        actual, expected, named = self._payload(
            lambda: assert_that([1, 2]).zip_satisfies([1], lambda left, right: left == right)
        )
        assert_that(actual).is_equal_to([1, 2])
        assert_that(expected).is_equal_to([1])
        assert_that(named).is_equal_to((True, True))

    def test_a_longer_other_is_the_same_failure(self):
        actual, expected, _named = self._payload(
            lambda: assert_that([1]).zip_satisfies([1, 2], lambda left, right: left == right)
        )
        assert_that(actual).is_equal_to([1])
        assert_that(expected).is_equal_to([1, 2])


class TestTheAnyOrderDiffMarksWhichSideIsMissing:
    """An unpaired item and an unpaired matcher are opposite absences, and the marker on each entry is
    what tells them apart in a report: without it both read as an ordinary difference.
    """

    @staticmethod
    def _entries(fn):
        with pytest.raises(AssertionFailure) as exc_info:
            fn()
        return [(entry.path, entry.actual, entry.expected, entry.absent) for entry in exc_info.value.diff.entries]

    def test_an_extra_item_and_a_missing_matcher_are_marked_apart(self):
        entries = self._entries(
            lambda: assert_that([1, 2]).satisfies_exactly_in_any_order(match.greater_than(10), match.is_positive())
        )
        assert_that(entries).is_equal_to(
            [("extra", 2, None, "expected"), ("missing", None, "a value greater than <10>", "actual")]
        )

    def test_two_unpaired_items_each_get_their_own_entry(self):
        entries = self._entries(
            lambda: assert_that([1, 2]).satisfies_exactly_in_any_order(match.greater_than(10), match.greater_than(20))
        )
        assert_that(entries).is_equal_to(
            [
                ("extra", 1, None, "expected"),
                ("extra", 2, None, "expected"),
                ("missing", None, "a value greater than <10>", "actual"),
                ("missing", None, "a value greater than <20>", "actual"),
            ]
        )

    def test_a_probe_that_raised_is_named_beside_its_matcher(self):
        # a plain predicate raises where a matcher answers False, and a raise is what the count is for
        entries = self._entries(
            lambda: assert_that([1, "x"]).satisfies_exactly_in_any_order(
                lambda value: value > 10, lambda value: value > 20
            )
        )
        assert_that([entry[3] for entry in entries]).contains_only("expected", "actual")
        assert_that([entry[2] for entry in entries if entry[2]]).contains(
            "a lambda predicate (probe raised TypeError on 1 item)"
        )


class TestAMatcherIsAskedAboutTheValueUnderTest:
    """Both walks ask `matches()` once to decide whether the slower evaluation is needed at all.

    A matcher of somebody else's making need not tolerate any other value: asking it about `None`
    turns a passing assertion into a TypeError raised from their code.
    """

    class _Positive:
        """Duck-typed, with no `evaluate()` of its own, which is the branch that asks `matches()`."""

        def matches(self, value):
            return value > 0

        def describe(self):
            return "a positive value"

        def describe_mismatch(self, value):
            return f"was {value}"

    def test_satisfies_asks_about_the_value(self):
        assert_that(5).satisfies(self._Positive())

    def test_each_asks_about_each_item(self):
        assert_that([1, 2, 3]).each(self._Positive())
