"""Equality as one decision, reachable from every spelling of it.

The comparison itself was already shared: one walker, one compare config.  What was not shared was the
way in: the recursive mapping comparison and the ignore/include filtering were methods on the builder's
mixin, so a matcher could not use them.  The visible consequence was not a wrong answer but a missing
one: `assert_that(v).is_equal_to(x, tolerance=0.1)` worked and `match.equal_to(x, tolerance=0.1)` raised
`TypeError`, which meant a structural spec could not express "close enough" or "ignore this field" at all.

These tests hold the two spellings together, and hold the core to the behaviour it had before the move.
"""

from __future__ import annotations

import datetime
import decimal
import math
from dataclasses import dataclass

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from assertpy2 import AssertionFailure, assert_that, match
from assertpy2._engine._compare import _CompareConfig
from assertpy2._engine._equality import (
    IncludeKeysMissingError,
    ignore_specs,
    include_specs,
    mapping_differs,
    mapping_shaped,
    values_differ,
)
from assertpy2._engine._membership import missing_items, only_faults, searchable
from assertpy2._engine._ordering import UnorderableError, compare, first_out_of_order, holds
from assertpy2._engine._size import length_of
from assertpy2._engine._text import contains as text_contains
from assertpy2._engine._text import starts_with as text_starts_with
from assertpy2.matchers import _is_matcher


@dataclass
class Reading:
    sensor: str
    value: float


OPTIONS = [
    ("tolerance", {"tolerance": 0.1}, 1.0, 1.05),
    ("tolerance too tight", {"tolerance": 0.001}, 1.0, 1.05),
    ("ignore", {"ignore": "b"}, {"a": 1, "b": 2}, {"a": 1, "b": 99}),
    (
        "ignore nested",
        {"ignore": ("user", "session")},
        {"user": {"id": 1, "session": "x"}},
        {"user": {"id": 1, "session": "y"}},
    ),
    ("include", {"include": "a"}, {"a": 1, "b": 2}, {"a": 1, "b": 99}),
    (
        "include nested",
        {"include": ("user", "id")},
        {"user": {"id": 1, "session": "x"}},
        {"user": {"id": 1, "session": "y"}},
    ),
    ("ignore_null", {"ignore_null": True}, {"a": 1, "b": 2}, {"a": 1, "b": None}),
    ("strict_types", {"strict_types": True}, {"id": 1}, {"id": True}),
    (
        "comparators",
        {"comparators": {str: lambda left, right: left.lower() == right.lower()}},
        {"n": "AB"},
        {"n": "ab"},
    ),
]


class TestBothSpellingsOfEqualityAnswerAlike:
    @pytest.mark.parametrize(("label", "options", "actual", "expected"), OPTIONS, ids=[case[0] for case in OPTIONS])
    def test_the_matcher_offers_what_the_assertion_offers(self, label, options, actual, expected):
        def by_builder() -> bool:
            try:
                assert_that(actual).is_equal_to(expected, **options)
            except AssertionFailure:
                return False
            return True

        assert_that(match.equal_to(expected, **options).matches(actual)).described_as(label).is_equal_to(by_builder())

    def test_an_option_the_relation_does_not_have_is_refused_by_name(self):
        # the builder already refuses a misspelt option; the matcher used to accept none at all, and a
        # spec author had no way to tell "not supported" from "spelled wrong"
        with pytest.raises(TypeError, match=r"equal_to.*strict_type"):
            match.equal_to(1, strict_type=True)

    def test_a_spec_can_now_say_close_enough(self):
        readings = {"sensor": "t1", "value": 20.03}
        assert_that(readings).matches_structure({"sensor": "t1", "value": match.equal_to(20.0, tolerance=0.1)})

    def test_a_spec_can_now_ignore_a_field(self):
        assert_that({"user": {"id": 1, "seen_at": "now"}}).matches_structure(
            {"user": match.equal_to({"id": 1, "seen_at": "whenever"}, ignore="seen_at")}
        )

    @pytest.mark.parametrize(
        ("options", "expected_note"),
        [
            ({"tolerance": 0.1}, "tolerance=0.1"),
            ({"ignore": "b"}, "ignoring 'b'"),
            ({"include": "a"}, "including 'a'"),
            ({"ignore_null": True}, "ignore_null=True"),
            ({"strict_types": True}, "strict_types=True"),
            ({"comparators": {str: lambda left, right: True}}, "comparators for str"),
        ],
        ids=["tolerance", "ignore", "include", "ignore_null", "strict_types", "comparators"],
    )
    def test_the_configuration_shows_up_in_the_failure(self, options, expected_note):
        """A verdict computed under a configuration has to be reported under it too.

        Otherwise the matcher compares with a tolerance and then says plainly "not equal", and a reader
        asking why a field they thought was tolerated still failed has nothing to read.  The assertion
        already echoes the settings on its own failures; this is the same line for a spec.
        """
        assert_that(match.equal_to({"a": 1, "b": 2}, **options).describe()).contains(expected_note)

    def test_no_configuration_means_no_note(self):
        assert_that(match.equal_to(1).describe()).is_equal_to("a value equal to <1>")

    def test_the_note_reaches_the_message_of_a_real_failure(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"v": 25.0}).matches_structure({"v": match.equal_to(20.0, tolerance=0.1)})
        assert_that(str(failure.value)).contains("tolerance=0.1")

    def test_a_comparator_that_raises_is_not_swallowed_by_either_spelling(self):
        # a comparator is user code like any operator: its own failure is a bug in the test, not a verdict
        def broken(left: object, right: object) -> bool:
            raise TypeError("bug inside comparator")

        with pytest.raises(TypeError, match="bug inside comparator"):
            assert_that({"n": 1}).is_equal_to({"n": 2}, comparators={int: broken})
        with pytest.raises(TypeError, match="bug inside comparator"):
            match.equal_to({"n": 2}, comparators={int: broken}).matches({"n": 1})

    def test_both_spellings_carry_the_same_structured_result(self):
        # the matcher answers a verdict rather than raising, so what it must not do is reach a different
        # verdict than the failure the assertion would have carried
        options = {"tolerance": 0.1}
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"v": 25.0}).is_equal_to({"v": 20.0}, **options)
        assert_that([entry.path for entry in failure.value.diff.entries]).is_equal_to(["v"])
        assert_that(match.equal_to({"v": 20.0}, **options).matches({"v": 25.0})).is_false()

    def test_an_include_naming_an_absent_key_is_a_non_match_rather_than_an_error(self):
        # the builder reports it as a failure in its own wording; a matcher has no wording, and raising
        # from `matches()` would break `==` and the combinators
        assert_that(match.equal_to({"a": 1}, include="missing").matches({"a": 1})).is_false()


class TestTheCoreItself:
    """The extracted functions, exercised where the public paths cannot reach them cleanly."""

    def test_a_mapping_shape_is_structural_rather_than_nominal(self):
        class Rowlike:
            def keys(self):
                return ["a"]

            def values(self):
                return [1]

            def __getitem__(self, key):
                return 1

            def __iter__(self):
                return iter(["a"])

        assert_that(mapping_shaped(Rowlike())).is_true()
        assert_that(mapping_shaped(Rowlike(), check_values=False)).is_true()
        assert_that(mapping_shaped([1, 2])).is_false()
        assert_that(mapping_shaped(42)).is_false()

    def test_a_cycle_is_answered_rather_than_recursed_into(self):
        """The guard covers the path the core walks itself, which is the one with filtering.

        Two *different* self-referential mappings still reach Python's own `==` when nothing is
        filtered, and that raises `RecursionError` from the interpreter. Measured, not assumed: it did
        so before this core existed too, so the guard is not claimed to be wider than it is.
        """
        left: dict = {"name": "a"}
        right: dict = {"name": "a"}
        left["self"] = left
        right["self"] = right
        assert_that(mapping_differs(left, right, ignore="nothing")).is_false()
        with pytest.raises(RecursionError):
            mapping_differs(left, right, config=_CompareConfig())

    def test_identity_short_circuits_before_equality(self):
        # NaN is the one value where the two disagree, and the walker must not be asked about it twice
        nan = float("nan")
        assert_that(values_differ(nan, nan, None)).is_false()
        assert_that(values_differ(nan, float("nan"), None)).is_true()
        assert_that(math.isnan(nan)).is_true()

    def test_the_mixin_still_answers_for_an_extension_that_calls_it(self):
        # the methods stayed as thin wrappers on purpose: an extension written against
        # `self._normalize_key_specs(...)` keeps working, and the decision behind it is now shared
        builder = assert_that({"a": 1})
        assert_that(builder._normalize_key_specs(["a", "b"], "ignore")).is_equal_to(["a", "b"])
        assert_that(builder._dict_ignore(("a",))).is_equal_to(["a"])
        assert_that(builder._dict_include(("a", "b"))).is_equal_to(["a"])
        assert_that(builder._is_dict_like({"a": 1})).is_true()

    def test_the_two_spec_normalizers_differ_on_purpose(self):
        # a one-element tuple is just a key for ignore; for include a path selects its first segment,
        # and the rest is consumed one level down. Getting this backwards silently broke nested include
        assert_that(ignore_specs(("a",))).is_equal_to(["a"])
        assert_that(ignore_specs(("a", "b"))).is_equal_to([("a", "b")])
        assert_that(include_specs(("a", "b"))).is_equal_to(["a"])

    def test_a_missing_include_key_is_signalled_from_the_depth_it_was_found(self):
        with pytest.raises(IncludeKeysMissingError) as signal:
            mapping_differs({"a": {"b": 1}}, {"a": {"c": 1}}, include=("a", "c"))
        assert_that(signal.value.missing).is_equal_to(["c"])

    def test_a_leaf_takes_the_config_that_applies_to_it(self):
        loose = _CompareConfig(tolerance=0.1)
        assert_that(values_differ(1.0, 1.05, loose)).is_false()
        assert_that(values_differ(1.0, 2.0, loose)).is_true()
        # a set is a leaf to the walker, and strict types have nothing to say about one: asking anyway
        # called two equal sets unequal
        assert_that(values_differ({1, 2}, {1, 2}, _CompareConfig(strict_types=True))).is_false()


class TestMembershipIsOneDecisionToo:
    """The second relation a spec could not express, and the same treatment.

    A spec had `each_item` (every element matches) and `is_in` (the value is one of these), but not the
    plain one: this collection contains that.  Written a second time inside the matcher it would have
    repeated the parts that are easy to get subtly wrong, so it asks the same core `contains()` asks.
    """

    @pytest.mark.parametrize(
        ("label", "value", "items"),
        [
            ("present", [1, 2, 3], (2,)),
            ("absent", [1, 2, 3], (9,)),
            ("several, one missing", [1, 2, 3], (1, 9)),
            ("mapping is searched by key", {"a": 1, "b": 2}, ("a",)),
            ("mapping key absent", {"a": 1}, ("b",)),
            ("string holds a substring", "hello", ("ell",)),
            ("set", {1, 2}, (2,)),
            ("tuple", (1, 2), (3,)),
        ],
    )
    def test_the_matcher_answers_what_the_assertion_answers(self, label, value, items):
        def by_builder() -> bool:
            try:
                assert_that(value).contains(*items)
            except AssertionFailure:
                return False
            return True

        assert_that(match.contains(*items).matches(value)).described_as(label).is_equal_to(by_builder())

    def test_a_matcher_among_the_items_is_satisfied_by_any_element(self):
        # the part that makes membership more than `item in value`: the argument decides for itself,
        # and it is asked of each element rather than compared to the collection
        assert_that(match.contains(match.greater_than(100)).matches([1, 200])).is_true()
        assert_that(match.contains(match.greater_than(100)).matches([1, 2])).is_false()

    def test_a_matcher_without_the_equality_protocol_is_asked_too(self):
        """The built-in matchers also answer `==`, which hides the branch that asks them.

        `match.greater_than(100) in [1, 200]` is true through `__eq__` alone, so dropping the explicit
        matcher check changed nothing for them.  A duck-typed matcher has no such fallback, and it is
        the case that proves the branch is load-bearing.
        """

        class OverAHundred:
            def matches(self, value: object) -> bool:
                return isinstance(value, int) and value > 100

            def describe(self) -> str:
                return "more than 100"

            def describe_mismatch(self, value: object) -> str:
                return f"was {value}"

        duck = OverAHundred()
        assert_that(duck in [1, 200]).described_as("plain membership does not find it").is_false()
        assert_that(match.contains(duck).matches([1, 200])).is_true()
        assert_that(match.contains(duck).matches([1, 2])).is_false()
        assert_that([1, 200]).contains(duck)

    def test_a_value_that_cannot_be_searched_is_a_non_match_rather_than_an_error(self):
        # the builder refuses it by type, because a wrong subject there is a mistake in the test; a
        # matcher feeds `==` and the combinators, where raising would be wrong
        assert_that(match.contains("x").matches(42)).is_false()
        with pytest.raises(TypeError, match=r"^val must be a container or iterable"):
            assert_that(42).contains("x")

    def test_a_one_shot_iterator_is_searched_rather_than_consumed(self):
        assert_that(match.contains(1, 3).matches(iter([1, 2, 3]))).is_true()

    def test_it_says_what_was_missing(self):
        assert_that(match.contains("beta").describe()).is_equal_to("a collection containing 'beta'")
        assert_that(match.contains("beta").describe_mismatch(["a"])).contains("missing 'beta'")
        assert_that(match.contains("beta").describe_mismatch(42)).contains("cannot be searched")

    def test_it_refuses_to_be_built_with_nothing_to_look_for(self):
        # `contains()` with no arguments is a vacuous assertion, and the builder already refuses it
        with pytest.raises(ValueError, match="one or more items"):
            match.contains()


class TestOrderingIsOneDecisionAsWell:
    """The comparison is an operator; the rule around it was written twice.

    A builder listed types and then tried the operator, a matcher tried the operator and answered False.
    Two spellings of one rule is how the text matchers drifted apart on bytes, so both now ask the same
    core and keep only what is genuinely theirs: what to do when the answer is "cannot be ordered".
    """

    @pytest.mark.parametrize(
        ("label", "actual", "expected", "relation"),
        [
            ("less", 1, 2, "lt"),
            ("greater", 2, 1, "gt"),
            ("equal under le", 1, 1, "le"),
            ("equal under ge", 1, 1, "ge"),
            ("int against float", 1, 1.0, "le"),
            ("strings", "a", "b", "lt"),
            ("dates", datetime.date(2026, 1, 1), datetime.date(2026, 6, 1), "lt"),
        ],
    )
    def test_the_relation_answers_what_python_answers(self, label, actual, expected, relation):
        operator = {"lt": "<", "le": "<=", "gt": ">", "ge": ">="}[relation]
        assert_that(holds(actual, expected, relation)).described_as(label).is_equal_to(
            eval(f"actual {operator} expected")  # the point is to hold the core to Python itself
        )

    @pytest.mark.parametrize(
        ("label", "actual", "expected", "kind"),
        [
            ("complex has no ordering", 1j, 0, "value"),
            ("a date wants a date", datetime.date(2026, 1, 1), 5, "kind"),
            ("a number wants a number", 1, "a", "kind"),
            ("the operator refuses the pair", object(), object(), "pair"),
        ],
    )
    def test_an_unorderable_pair_says_why(self, label, actual, expected, kind):
        with pytest.raises(UnorderableError) as unordered:
            compare(actual, expected)
        assert_that(unordered.value.kind).described_as(label).is_equal_to(kind)

    def test_a_nan_outside_the_builtin_types_is_answered_the_same(self):
        """The fast path covers `float`; the rule behind it has to hold for the rest too.

        A `numpy.float64` NaN goes the long way round, where "neither smaller nor larger" would read as
        "equal" and make `le`/`ge` true. It is the only case that reaches that guard now that plain
        floats short-circuit, so it is what keeps the guard honest.
        """
        numpy = pytest.importorskip("numpy")
        nan = numpy.float64("nan")
        assert_that(holds(nan, nan, "le")).is_false()
        assert_that(holds(nan, nan, "ge")).is_false()
        assert_that(holds(nan, nan, "lt")).is_false()

    def test_nan_is_neither_less_nor_greater_nor_equal(self):
        # `compare` answers 0 because neither side is smaller, and that is the one place where "not
        # less, not greater" must not become "equal": `le`/`ge` stay false
        nan = float("nan")
        assert_that(holds(nan, nan, "le")).is_false()
        assert_that(holds(nan, nan, "ge")).is_false()
        assert_that(holds(nan, 1, "lt")).is_false()

    def test_both_spellings_treat_an_unorderable_pair_their_own_way(self):
        # the difference in strictness is deliberate: a wrong subject in an assertion is a mistake in
        # the test, while a matcher feeds `==` and the combinators, where raising would be wrong
        assert_that(match.greater_than(1).matches("a")).is_false()
        with pytest.raises(TypeError, match=r"^given other arg must be a number"):
            assert_that(1).is_greater_than("a")

    def test_a_broken_operator_still_travels_out_of_the_core(self):
        class BrokenOrder:
            def __lt__(self, other: object) -> bool:
                raise TypeError("bug inside __lt__")

            def __gt__(self, other: object) -> bool:
                raise TypeError("bug inside __lt__")

        with pytest.raises(TypeError, match="bug inside __lt__"):
            compare(BrokenOrder(), BrokenOrder())


class TestTheRelationsASpecCouldNotExpress:
    """Three relations the builder has always had and a structural spec could not say at all.

    Each is the same decision the assertion reaches, asked of the same core: the point of the move is
    that there is no second implementation to drift, not that a matcher was added.
    """

    @pytest.mark.parametrize(
        ("label", "value", "items"),
        [
            ("exactly these", [1, 2], (1, 2)),
            ("one extra", [1, 2, 3], (1, 2)),
            ("one missing", [1], (1, 2)),
            ("order does not matter", [2, 1], (1, 2)),
            ("duplicates are still only these", [1, 1, 2], (1, 2)),
        ],
    )
    def test_contains_only_answers_what_the_assertion_answers(self, label, value, items):
        def by_builder() -> bool:
            try:
                assert_that(value).contains_only(*items)
            except AssertionFailure:
                return False
            return True

        assert_that(match.contains_only(*items).matches(value)).described_as(label).is_equal_to(by_builder())

    @pytest.mark.parametrize(
        ("label", "value", "superset"),
        [
            ("proper subset", [1, 2], [1, 2, 3]),
            ("equal sets", [1, 2], [1, 2]),
            ("one outside", [1, 9], [1, 2]),
            ("empty is a subset of anything", [], [1]),
        ],
    )
    def test_is_subset_of_answers_what_the_assertion_answers(self, label, value, superset):
        def by_builder() -> bool:
            try:
                assert_that(value).is_subset_of(*superset)
            except AssertionFailure:
                return False
            return True

        assert_that(match.is_subset_of(superset).matches(value)).described_as(label).is_equal_to(by_builder())

    @pytest.mark.parametrize(
        ("label", "value", "reverse"),
        [
            ("ascending", [1, 2, 3], False),
            ("out of order", [1, 3, 2], False),
            ("descending under reverse", [3, 2, 1], True),
            ("ascending under reverse", [1, 2, 3], True),
            ("equal neighbours are sorted", [1, 1, 2], False),
            ("single element", [1], False),
        ],
    )
    def test_is_sorted_answers_what_the_assertion_answers(self, label, value, reverse):
        def by_builder() -> bool:
            try:
                assert_that(value).is_sorted(reverse=reverse)
            except AssertionFailure:
                return False
            return True

        assert_that(match.is_sorted(reverse=reverse).matches(value)).described_as(label).is_equal_to(by_builder())

    def test_is_sorted_takes_a_key_the_same_way(self):
        rows = [{"n": 1}, {"n": 2}]
        assert_that(rows).is_sorted(key=lambda row: row["n"])
        assert_that(match.is_sorted(key=lambda row: row["n"]).matches(rows)).is_true()

    def test_they_say_what_was_wrong(self):
        assert_that(match.contains_only("a", "b").describe()).is_equal_to("a collection containing only 'a', 'b'")
        assert_that(match.contains_only("a").describe_mismatch(["a", "b"])).contains("also had 'b'")
        assert_that(match.contains_only("a", "b").describe_mismatch(["a"])).contains("lacked 'b'")
        assert_that(match.is_subset_of([1]).describe_mismatch([1, 9])).contains("9 outside it")
        assert_that(match.is_sorted().describe_mismatch([3, 1])).contains("out of order at index 0")
        assert_that(match.is_sorted().describe()).is_equal_to("a collection sorted in order")
        assert_that(match.is_sorted(reverse=True).describe()).is_equal_to("a collection sorted in reverse")
        assert_that(match.is_subset_of([1]).describe()).contains("all appear in")

    def test_a_value_they_cannot_walk_is_a_non_match(self):
        assert_that(match.contains_only("a").matches(42)).is_false()
        assert_that(match.is_subset_of([1]).matches(42)).is_false()
        assert_that(match.is_sorted().matches(42)).is_false()
        assert_that(match.contains_only("a").describe_mismatch(42)).contains("cannot be searched")
        assert_that(match.is_subset_of([1]).describe_mismatch(42)).contains("cannot be searched")
        assert_that(match.is_sorted().describe_mismatch(42)).contains("cannot be walked")

    def test_elements_that_cannot_be_ordered_are_not_sorted(self):
        assert_that(match.is_sorted().matches([1, "a"])).is_false()

    def test_the_assertion_refuses_the_same_collection_in_its_own_words(self):
        # the two halves of the same rule again: a matcher answers, an assertion refuses. What must not
        # happen is Python's "'<' not supported between instances of 'str' and 'int'" reaching the
        # reader, which is about the operator and names neither the assertion nor its value
        with pytest.raises(TypeError, match=r"^val must be a collection whose items can be ordered"):
            assert_that([1, "a"]).is_sorted()

    def test_a_broken_operator_still_travels_out_of_is_sorted(self):
        class BrokenOrder:
            def __lt__(self, other: object) -> bool:
                raise TypeError("bug inside __lt__")

            def __gt__(self, other: object) -> bool:
                raise TypeError("bug inside __lt__")

        with pytest.raises(TypeError, match="bug inside __lt__"):
            match.is_sorted().matches([BrokenOrder(), BrokenOrder()])

    @pytest.mark.parametrize("factory", [match.contains, match.contains_only, match.is_subset_of])
    def test_they_refuse_to_be_built_with_nothing(self, factory):
        with pytest.raises(ValueError, match="one or more items"):
            factory()


class TestStrictNeverTurnsUnequalIntoEqual:
    """`strict_types=True` may reject more pairs than plain equality. It may not accept more.

    It did: `assert_that(nan).is_equal_to(nan)` failed and the same call with the flag passed, because
    the strict path short-circuited on identity before asking `__eq__` at all.  The shortcut is right
    *inside* a container, where Python gives it for free (`[nan] == [nan]` is true when both elements are
    the same object), and wrong at the root, where there is no container to inherit it from.
    """

    class NotReflexive:
        """A value that is not equal to itself, the way `nan` is, without being a number."""

        def __eq__(self, other: object) -> bool:
            return False

        __hash__ = None  # ty: ignore[invalid-assignment]  # deliberately unhashable

    @staticmethod
    def _passes(value: object, expected: object, **options: object) -> bool:
        try:
            assert_that(value).is_equal_to(expected, **options)
        except AssertionFailure:
            return False
        return True

    def test_the_same_nan_is_unequal_to_itself_in_both_modes(self):
        nan = float("nan")
        assert_that(self._passes(nan, nan)).described_as("plain").is_false()
        assert_that(self._passes(nan, nan, strict_types=True)).described_as("strict").is_false()

    def test_two_different_nans_are_unequal_in_both_modes(self):
        assert_that(self._passes(float("nan"), float("nan"))).is_false()
        assert_that(self._passes(float("nan"), float("nan"), strict_types=True)).is_false()

    def test_a_decimal_nan_behaves_the_same(self):
        quiet = decimal.Decimal("NaN")
        assert_that(self._passes(quiet, quiet)).is_false()
        assert_that(self._passes(quiet, quiet, strict_types=True)).is_false()

    def test_a_shared_nan_inside_containers_stays_equal(self):
        # Python's own container comparison says these are equal, and the flag must not change that
        nan = float("nan")
        assert_that([nan] == [nan]).described_as("python itself").is_true()
        assert_that(self._passes([nan], [nan])).described_as("plain").is_true()
        assert_that(self._passes([nan], [nan], strict_types=True)).described_as("strict").is_true()
        assert_that(self._passes({"v": nan}, {"v": nan}, strict_types=True)).described_as("mapping").is_true()

    def test_two_different_nans_inside_containers_stay_unequal(self):
        assert_that(self._passes([float("nan")], [float("nan")])).is_false()
        assert_that(self._passes([float("nan")], [float("nan")], strict_types=True)).is_false()

    def test_a_value_that_is_not_equal_to_itself_is_treated_the_same(self):
        odd = self.NotReflexive()
        assert_that(self._passes(odd, odd)).described_as("plain").is_false()
        assert_that(self._passes(odd, odd, strict_types=True)).described_as("strict").is_false()
        assert_that(self._passes([odd], [odd], strict_types=True)).described_as("inside a list").is_true()

    def test_the_matcher_keeps_the_same_invariant(self):
        nan = float("nan")
        assert_that(match.equal_to(nan, strict_types=True).matches(nan)).is_false()
        assert_that(match.equal_to([nan], strict_types=True).matches([nan])).is_true()

    @given(
        left=st.one_of(st.integers(), st.floats(allow_nan=True), st.text(max_size=5), st.booleans()),
        right=st.one_of(st.integers(), st.floats(allow_nan=True), st.text(max_size=5), st.booleans()),
    )
    @settings(deadline=None)
    def test_strict_implies_plain_for_any_pair(self, left, right):
        """The property behind all of the above, over generated pairs rather than chosen ones."""
        if self._passes(left, right, strict_types=True):
            assert_that(self._passes(left, right)).described_as(f"{left!r} vs {right!r}").is_true()


class TestTheCoresUnderTheAwkwardCases:
    """The cases a chosen-example test does not think of, listed by review and measured here."""

    def test_a_key_is_computed_once_per_element(self):
        # a key can be expensive or have a side effect; recomputing the left-hand side of every pair
        # doubled the calls
        calls = []

        def counting(item: int) -> int:
            calls.append(item)
            return item

        first_out_of_order([1, 2, 3, 4], key=counting)
        assert_that(calls).is_length(4)

    def test_a_length_is_read_once(self):
        calls = []

        class CountingLength:
            def __len__(self) -> int:
                calls.append(1)
                return 3

        length_of(CountingLength())
        assert_that(calls).is_length(1)

    def test_membership_drains_a_one_shot_iterator_before_searching_it(self):
        # searched once per wanted item, so a generator would be empty by the second question
        assert_that(missing_items(searchable(iter([1, 2, 3])), [1, 3], _is_matcher)).is_empty()

    def test_membership_works_on_unhashable_elements(self):
        # `in` on a list is a linear scan, so unhashable elements are fine; a set-based shortcut here
        # would have raised instead
        assert_that(missing_items([[1], [2]], [[2]], _is_matcher)).is_empty()
        assert_that([{"a": 1}]).contains({"a": 1})

    def test_duplicates_do_not_confuse_membership(self):
        assert_that(missing_items([1, 1, 2], [1, 2], _is_matcher)).is_empty()
        assert_that(only_faults([1, 1, 2], (1, 2))).is_equal_to(([], []))

    def test_text_relations_accept_subclasses_of_their_types(self):
        class Name(str):
            pass

        class Raw(bytes):
            pass

        assert_that(text_contains(Name("hello"), "ell")).is_true()
        assert_that(text_starts_with(Name("hello"), "he")).is_true()
        assert_that(text_contains(Raw(b"hello"), b"ell")).is_true()
        assert_that(text_contains(bytearray(b"hello"), b"ell")).is_true()

    def test_a_tuple_of_prefixes_is_not_accepted_by_either_spelling(self):
        """`str.startswith` takes a tuple; this relation does not, and did not before the move.

        Recorded rather than fixed: accepting it would make the matcher answer a question the assertion
        refuses, which is the drift this core exists to prevent. Widening both is a separate decision.
        """
        assert_that(text_starts_with("hello", ("he", "xx"))).is_false()
        with pytest.raises(TypeError, match=r"^given prefix arg must be a string"):
            assert_that("hello").starts_with(("he", "xx"))

    def test_a_length_that_is_negative_is_pythons_own_error(self):
        class Negative:
            def __len__(self) -> int:
                return -1  # noqa: PLE0303  # the invalid length is exactly what is measured

        with pytest.raises(ValueError, match="__len__"):
            length_of(Negative())


class TestAMatcherIsASpecificationAndAnswersTheSameWayTwice:
    """A matcher is built once and used many times, often against several values in a row.

    The four new ones take a collection as their expected operand, and a collection handed in as a
    generator is gone after the first question.  Drained at construction, so the second call reaches the
    same verdict as the first: anything else makes a spec silently depend on how often it was used.
    """

    @pytest.mark.parametrize(
        ("label", "build", "value"),
        [
            ("contains", lambda: match.contains(1, 2), [1, 2, 3]),
            ("contains_only", lambda: match.contains_only(1, 2), [1, 2]),
            ("is_subset_of from a list", lambda: match.is_subset_of([1, 2, 3]), [1, 2]),
            ("is_subset_of from items", lambda: match.is_subset_of(1, 2, 3), [1, 2]),
            ("is_sorted", lambda: match.is_sorted(), [1, 2, 3]),
            ("equal_to with options", lambda: match.equal_to({"a": 1}, ignore="b"), {"a": 1, "b": 9}),
        ],
    )
    def test_three_calls_give_the_same_answer(self, label, build, value):
        matcher = build()
        verdicts = [matcher.matches(value) for _ in range(3)]
        assert_that(set(verdicts)).described_as(label).is_length(1)

    def test_a_generator_as_the_expected_operand_is_drained_once(self):
        # the case that failed: the first call consumed the superset and the second said "no" about a
        # value it had just accepted
        constraint = match.is_subset_of(iter([1, 2, 3]))
        assert_that(constraint.matches([1])).described_as("first").is_true()
        assert_that(constraint.matches([1])).described_as("second").is_true()
        assert_that(constraint.matches([2, 3])).described_as("third, other value").is_true()

    def test_an_ordinary_collection_stays_a_live_view(self):
        """Copy only what has to be copied.

        `equal_to` keeps its expected value rather than a snapshot of it, and a membership matcher does
        the same: a list handed in stays the same list.  Only a one-shot iterator is drained, because
        there is no other way for it to answer twice.  Saying "a matcher is a specification" does not
        settle this, so it is measured.
        """
        known = [1]
        constraint = match.is_subset_of(known)
        assert_that(constraint.matches([1])).described_as("before").is_true()
        known.append(2)
        assert_that(constraint.matches([2])).described_as("after the list grew").is_true()

    def test_a_one_shot_iterator_is_the_only_thing_copied(self):
        drained = match.is_subset_of(iter([1, 2]))
        assert_that(drained.matches([1])).is_true()
        assert_that(drained.matches([2])).described_as("still answers, from the copy").is_true()

    def test_the_description_survives_being_asked_twice(self):
        constraint = match.is_subset_of(iter([1, 2]))
        assert_that(constraint.describe()).is_equal_to(constraint.describe())

    def test_one_matcher_serves_several_values(self):
        constraint = match.contains("beta")
        assert_that(["alpha", "beta"]).satisfies(constraint)
        assert_that({"beta": 1}).satisfies(constraint)
        assert_that("a beta release").satisfies(constraint)


class TestTheNewMatchersAcceptTheCollectionsPeopleActuallyHave:
    """Binding the element to the collection must not make the annotation narrower than the runtime.

    `Iterable` is covariant and `Matcher` is contravariant, so the combination is easy to get wrong in
    the strict direction: a `list[object]` or a `list[Base]` holding a `Derived` is ordinary code, and a
    checker refusing it would be a regression dressed as a type improvement.  Runtime is asserted here;
    the static half of the same cases lives in `tests/typing_cases.py`, where three checkers read them.
    """

    class Base:
        pass

    class Derived(Base):
        pass

    def test_a_heterogeneous_collection_is_searched_by_one_of_its_types(self):
        mixed: list[int | str] = [1, "x"]
        assert_that(mixed).satisfies(match.contains("x"))
        assert_that(mixed).satisfies(match.contains_only(1, "x"))

    def test_a_collection_of_object_is_searched_by_a_concrete_value(self):
        wide: list[object] = [1, "x"]
        assert_that(wide).satisfies(match.contains("x"))
        assert_that(wide).satisfies(match.is_subset_of([1, "x", 2.0]))

    def test_a_collection_of_a_base_class_is_searched_by_a_subclass_instance(self):
        item = self.Derived()
        values: list[TestTheNewMatchersAcceptTheCollectionsPeopleActuallyHave.Base] = [item]
        assert_that(values).satisfies(match.contains(item))
        assert_that(values).satisfies(match.is_subset_of(values))
