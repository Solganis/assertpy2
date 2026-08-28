"""Equality as one decision, reachable from every spelling of it.

The comparison itself was already shared: one walker, one compare config.  What was not shared was the
way in: the recursive mapping comparison and the ignore/include filtering were methods on the builder's
mixin, so a matcher could not use them.  The visible consequence was not a wrong answer but a missing
one: `assert_that(v).is_equal_to(x, tolerance=0.1)` worked and `match.equal_to(x, tolerance=0.1)` raised
`TypeError`, which meant a structural spec could not express "close enough" or "ignore this field" at all.

These tests hold the two spellings together, and hold the core to the behaviour it had before the move.
"""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import enum
import fractions
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
from assertpy2._engine._introspection import materialized
from assertpy2._engine._membership import (
    _classified,
    _hash_safe,
    has_duplicates,
    missing_items,
    not_contained_in,
    only_faults,
    repeated_items,
    searchable,
)
from assertpy2._engine._ordering import UnorderableError, compare, first_out_of_order, holds
from assertpy2._engine._size import length_of
from assertpy2._engine._text import contains as text_contains
from assertpy2._engine._text import starts_with as text_starts_with
from assertpy2.matchers import _is_matcher


@dataclass
class Reading:
    sensor: str
    value: float


class _ByField:
    """Equality by field, hash by identity: the pair a set cannot answer for.

    Written by hand rather than taken from a library because that is how it appears in real suites, and
    it is the value that decides whether a set may stand in for a walk.
    """

    def __init__(self, value: int) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _ByField) and other.value == self.value

    def __hash__(self) -> int:
        return id(self)


class _NoHash:
    """Inherited equality, but explicitly unhashable, which the type rule alone would not notice."""

    __hash__ = None


class _Counted(int):
    """A subclass that changes neither operation, so it answers exactly as `int` does."""


class _HashesLikeText(int):
    """One operation inherited and the other replaced, which is the disagreement the rule looks for."""

    __hash__ = str.__hash__


class _Status(str, enum.Enum):
    """Spelled with the mixin rather than as `enum.StrEnum`, which arrived in 3.11 and this suite runs 3.10.

    Identical where it matters: both take `__eq__` and `__hash__` from `str`, which is what the rule reads.
    """

    PAID = "paid"
    DUE = "due"


# both halves of the membership rule in one generator: values a set may answer for, and values it may
# not.  Mixing them is what makes the properties below test the classifier rather than the fast path.
# The last three are the subclass half of it: two that a set may answer for although their exact types
# are not on the safe list, and one that inherits equality and hashes by another rule entirely
_MIXED_ELEMENTS = st.one_of(
    st.integers(-5, 5),
    st.text(max_size=2),
    st.none(),
    st.booleans(),
    st.builds(bytearray, st.binary(max_size=2)),
    st.builds(_ByField, st.integers(-2, 2)),
    st.builds(_NoHash),
    st.lists(st.integers(-2, 2), max_size=2),
    st.builds(_Counted, st.integers(-2, 2)),
    st.builds(_HashesLikeText, st.integers(-2, 2)),
    st.sampled_from(_Status),
)


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
        options = {"tolerance": 0.1}
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"v": 25.0}).is_equal_to({"v": 20.0}, **options)
        assert_that([entry.path for entry in failure.value.diff.entries]).is_equal_to(["v"])
        assert_that(match.equal_to({"v": 20.0}, **options).matches({"v": 25.0})).is_false()

    def test_an_include_naming_an_absent_key_is_a_non_match_rather_than_an_error(self):
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
            eval(f"actual {operator} expected")
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

    def test_contains_only_asks_which_items_not_how_many(self):
        """The boundary the matcher guide warns about, pinned so the warning cannot go stale.

        `contains_only` asks that nothing outside the given items is there.  Multiset equality is a
        different question, and the assertion that answers it is `contains_exactly_in_any_order`.
        """
        assert_that(match.contains_only("reader", "reader").matches(["reader"])).is_true()
        assert_that(match.contains_only(1, 2).matches([1, 1, 2])).is_true()
        with pytest.raises(AssertionFailure):
            assert_that([1, 1, 2]).contains_exactly_in_any_order(1, 2)

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
        assert_that(match.contains_only("a").describe_mismatch(42)).contains("cannot be listed")
        assert_that(match.is_subset_of([1]).describe_mismatch(42)).contains("cannot be listed")
        assert_that(match.is_sorted().describe_mismatch(42)).contains("cannot be walked")

    def test_answering_membership_is_not_the_same_as_being_listable(self):
        """`contains` needs only `in`; "only these" and "a subset of" need every element.

        Told apart because they were not: a value with `__contains__` and nothing else satisfied the
        capability check and then met Python's own "object is not iterable" inside the comprehension.
        """

        class MembershipOnly:
            def __contains__(self, item: object) -> bool:
                return item == 1

        value = MembershipOnly()
        assert_that(match.contains(1).matches(value)).described_as("membership is enough").is_true()
        assert_that(match.contains_only(1).matches(value)).described_as("listing is not").is_false()
        assert_that(match.is_subset_of([1]).matches(value)).described_as("listing is not").is_false()
        assert_that(value).contains(1)
        for relation in ("contains_only", "is_subset_of"):
            with pytest.raises(TypeError, match=r"^val must be iterable"):
                getattr(assert_that(value), relation)(1)

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
        assert_that(missing_items(searchable(iter([1, 2, 3])), [1, 3], _is_matcher)).is_empty()

    def test_membership_works_on_unhashable_elements(self):
        assert_that(missing_items([[1], [2]], [[2]], _is_matcher)).is_empty()
        assert_that([{"a": 1}]).contains({"a": 1})

    def test_duplicates_do_not_confuse_membership(self):
        assert_that(missing_items([1, 1, 2], [1, 2], _is_matcher)).is_empty()
        assert_that(only_faults([1, 1, 2], (1, 2))).is_equal_to(([], []))

    def test_membership_keeps_its_answer_when_hashing_and_equality_disagree(self):
        """The case the set shortcut must refuse: equality by field, hash by identity.

        `a in [b]` is True because `==` says so, and `a in {b}` is False because the hashes differ and
        the comparison never happens. Membership here follows `==`, so such a value has to keep the walk.
        """

        wanted, held = _ByField(1), _ByField(1)
        assert_that(held in {wanted, _ByField(2)}).described_as("premise: a set cannot find it").is_false()
        assert_that(missing_items([held], [wanted], _is_matcher)).described_as("membership finds it").is_empty()
        assert_that(only_faults([held], (wanted,))).is_equal_to(([], []))
        assert_that(not_contained_in([held], [wanted])).is_empty()
        assert_that([held]).contains_only(wanted)
        assert_that([held]).is_subset_of([wanted])

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(bytearray(b"a"), id="bytearray: mutable, so unhashable despite looking built-in"),
            pytest.param(_NoHash(), id="identity equality but __hash__ set to None"),
        ],
    )
    def test_a_value_that_cannot_be_hashed_is_answered_rather_than_raised_at(self, value):
        """Both of these once raised `TypeError: cannot use 'bytearray' as a set element`.

        Hashability has to be asked, not assumed from the type looking simple or from equality being the
        inherited one: a class may keep identity equality and still say `__hash__ = None`.
        """
        twin = bytearray(b"a") if isinstance(value, bytearray) else value
        assert_that(only_faults([value], (twin,))).is_equal_to(([], []))
        assert_that(not_contained_in([value], [twin])).is_empty()
        assert_that(missing_items([value], [twin], _is_matcher)).is_empty()
        assert_that(repeated_items([value, twin])).described_as("two equal elements are one repeat").is_length(1)
        assert_that([value]).contains_only(twin)
        assert_that([value]).is_subset_of([twin])
        assert_that([value]).contains(twin)
        assert_that([value]).does_not_contain_duplicates()

    def test_the_shortcut_is_taken_once_the_collections_are_large_enough(self):
        """The other side of the threshold, and the reason it exists at all.

        Small collections keep the walk because deciding to avoid it costs more than the walk. These
        sizes are past that point, so the set path runs, and it has to answer exactly the same thing.
        """
        values, wanted = list(range(60)), tuple(range(60))
        assert_that(only_faults(values, wanted)).is_equal_to(([], []))
        assert_that(only_faults([*values, 999], wanted)).is_equal_to(([999], []))
        assert_that(not_contained_in(values, [*wanted, 999])).is_empty()
        assert_that(missing_items(values, wanted, _is_matcher)).is_empty()

    def test_a_value_without_a_length_is_judged_worth_hashing(self):
        """A collection that can be walked but not sized: the cost of walking it is unknown.

        The core assumes it is not small rather than skipping the shortcut on something that may well be
        huge. Reachable from the public API, since being walkable is all `contains_only` requires.
        """

        class Unsized:
            def __iter__(self):
                return iter(range(60))

        assert_that(only_faults(Unsized(), tuple(range(60)))).is_equal_to(([], []))
        assert_that(Unsized()).contains_only(*range(60))

    def test_the_fast_path_asks_for_one_hash_per_element_and_no_comparisons(self):
        """What the shortcut is actually for, counted rather than assumed.

        A property test proves the answer is the same; it says nothing about the work done to reach it.
        These counters do: the walk would compare every element against every wanted one, and the set
        hashes each element once instead.
        """
        hashes: list[int] = []

        class Counted:
            """No `__eq__` of its own, so equality is identity and the shortcut may hash it."""

            def __init__(self, value: int) -> None:
                self.value = value

            def __hash__(self) -> int:
                hashes.append(self.value)
                return self.value

        def hash_calls_for(size: int) -> int:
            hashes.clear()
            values = [Counted(index) for index in range(size)]
            only_faults(values, tuple(values))
            return len(hashes)

        small, large = hash_calls_for(30), hash_calls_for(60)
        assert_that(large / small).described_as("hash calls when the input doubles").is_close_to(2.0, 0.1)
        assert_that(small / 30).described_as("hash calls per element").is_close_to(4.0, 0.1)

    def test_the_walk_is_kept_where_it_must_be_and_costs_what_it_costs(self):
        comparisons: list[tuple[int, int]] = []

        class ByValue:
            def __init__(self, value: int) -> None:
                self.value = value

            def __eq__(self, other: object) -> bool:
                comparisons.append((self.value, getattr(other, "value", -1)))
                return isinstance(other, ByValue) and other.value == self.value

            __hash__ = None

        values = [ByValue(index) for index in range(6)]
        only_faults(values, tuple(values))
        assert_that(comparisons).described_as("a walk does compare, and that is the price of it").is_not_empty()

    def test_a_one_shot_value_is_walked_once(self):
        seen: list[int] = []

        def counting():
            for index in range(50):
                seen.append(index)
                yield index

        assert_that(only_faults(searchable(counting()), tuple(range(50)))).is_equal_to(([], []))
        assert_that(seen).described_as("elements produced by the generator").is_length(50)

    def test_decimals_take_the_shortcut_and_answer_the_same(self):
        """`Decimal` is on the safe list, so this has to prove the fast path, not just the answer.

        Sizes are past the threshold on purpose: at one element the walk would run whatever the list
        says, and the test would prove nothing about the path it claims to exercise.
        """
        values = [decimal.Decimal(index) for index in range(30)]
        assert_that(_hash_safe(values)).described_as("classified as safe to index").is_true()
        assert_that(_classified(values, tuple(values))).described_as("and worth indexing at this size").is_true()
        assert_that(only_faults(values, tuple(values))).is_equal_to(([], []))
        assert_that(values).contains_only(*values)
        assert_that(values).is_subset_of(values)
        assert_that([*values, values[0]]).contains_duplicates()

    def test_a_subclass_that_changes_neither_operation_takes_the_shortcut(self):
        """The safe list holds exact types, so a subclass used to walk although it answers as its base.

        `IntEnum` and `StrEnum` are the shapes a suite actually carries, a status field most of all.  Four
        thousand of them cost 30 ms on the walk against 0.09 ms indexed, and the answer is the same either
        way because the subclass inherits both operations unchanged.
        """

        class Money(int):
            def __init__(self, *_: object) -> None:
                self.currency = "USD"

        class Status(str, enum.Enum):
            PAID = "paid"
            DUE = "due"

        class Level(enum.IntEnum):
            LOW = 1
            HIGH = 2

        for values in ([Money(index) for index in range(30)], list(Status) * 15, list(Level) * 15):
            assert_that(_hash_safe(values)).described_as(f"{type(values[0]).__name__} is safe to index").is_true()
            assert_that(only_faults(values, tuple(values))).is_equal_to(([], []))
            assert_that(values).contains_only(*values)
            assert_that(values).is_subset_of(values)

        assert_that([*list(Status), Status.PAID]).contains_duplicates()
        assert_that(_hash_safe([Level.LOW, 1, True])).described_as("mixed with the base type").is_true()

    def test_a_subclass_that_replaces_one_operation_stays_on_the_walk(self):
        """Inheriting one of the pair and redefining the other is exactly the disagreement to avoid.

        Asked of the owner of each definition, so all four of these are refused: the first hashes by one
        rule and compares by another, the second compares by its own, the third is not hashable at all
        although its base is, and the fourth had equality assigned onto it after the class body ran.

        That last one is the case the `__eq__` half of the rule exists for, and it takes a patched class
        to build: writing `__eq__` in the body sets `__hash__` to `None` with it, so the hash half already
        refuses those.  Patched, it keeps `int.__hash__` and answers `True` to every comparison, and a set
        keeps two values the walk calls equal.
        """

        class HashesLikeText(int):
            __hash__ = str.__hash__

        class ComparesItsOwnWay(int):
            def __eq__(self, other: object) -> bool:
                return isinstance(other, ComparesItsOwnWay) and int(self) == int(other)

            __hash__ = int.__hash__

        class RefusesToHash(int):
            __hash__ = None  # ty: ignore[invalid-assignment]  # the shape under test

        class Patched(int):
            pass

        def _everything_is_equal(self: object, other: object) -> bool:
            return True

        Patched.__eq__ = _everything_is_equal  # ty: ignore[invalid-assignment]  # the shape under test

        assert_that(Patched(1) == Patched(2)).described_as("the patched comparison").is_true()
        assert_that({Patched(1), Patched(2)}).described_as("a set does not agree with it").is_length(2)

        for kind in (HashesLikeText, ComparesItsOwnWay, RefusesToHash, Patched):
            values = [kind(index) for index in range(30)]
            assert_that(_hash_safe(values)).described_as(f"{kind.__name__} is not safe to index").is_false()

        walked = [ComparesItsOwnWay(index) for index in range(30)]
        assert_that(only_faults(walked, tuple(walked))).is_equal_to(([], []))
        assert_that([*walked, walked[0]]).contains_duplicates()

    def test_fractions_stay_on_the_walk_and_answer_the_same(self):
        """Kept out of the shortcut for import cost, not for correctness, so both have to be shown."""
        values = [fractions.Fraction(index, 3) for index in range(30)]
        assert_that(_hash_safe(values)).described_as("not classified as safe: the list omits Fraction").is_false()
        assert_that(only_faults(values, tuple(values))).is_equal_to(([], []))
        assert_that(values).contains_only(*values)
        assert_that(values).is_subset_of(values)
        assert_that([*values, values[0]]).contains_duplicates()

    def test_a_value_that_refuses_to_hash_despite_its_type_falls_back(self):
        """`Decimal` is on the safe list, and one `Decimal` still refuses to be hashed.

        A signalling NaN is meant to be noticed rather than compared quietly, so it raises on hashing.
        That is a property of the value, invisible to a rule about types, so the set is attempted and the
        walk takes over when it fails.  The sizes are past the threshold, so the fast path really is tried.
        """
        values = [decimal.Decimal("snan")] * 30
        assert_that(only_faults(values, tuple(values))).is_equal_to(([], []))
        assert_that(not_contained_in(values, values)).is_empty()
        assert_that(values).contains_only(*values)
        assert_that(values).is_subset_of(values)

    def test_naming_repeats_of_an_unhashable_value_answers_like_the_shipped_release(self):
        same_object = [decimal.Decimal("snan")] * 30
        assert_that(has_duplicates(same_object)).described_as("one object, thirty times").is_true()
        with pytest.raises(decimal.InvalidOperation):
            repeated_items(same_object)

    def test_a_value_whose_class_cannot_be_hashed_keeps_the_walk(self):
        """The classifier hashes the types, and a metaclass may refuse that.

        The instances compare perfectly well, so refusing to classify has to mean walking rather than
        raising. Found by review: the shortcut turned a plain assertion failure into a `TypeError`.
        """

        class Unhashable(type):
            __hash__ = None

        class Odd(metaclass=Unhashable):
            pass

        values = [Odd() for _ in range(30)]
        others = tuple(Odd() for _ in range(30))
        assert_that(_hash_safe(values)).described_as("cannot be classified, so not safe").is_false()
        assert_that(only_faults(values, others)[0]).is_length(len(values))
        with pytest.raises(AssertionFailure):
            assert_that(values).contains_only(*others)

    def test_a_hash_that_raises_is_not_a_reason_to_stop_answering(self):
        """A shortcut may not introduce an exception the library did not have.

        This class compares by identity, which the rule accepts, and hashes by raising. Before the
        shortcut nothing hashed it and the assertion simply failed; that is what it does again.
        """

        class Angry:
            def __hash__(self) -> int:
                raise ValueError("hashing is a bug in this value")

        values = [Angry() for _ in range(30)]
        assert_that(only_faults(values, tuple(Angry() for _ in range(30)))[0]).is_length(len(values))
        with pytest.raises(AssertionFailure):
            assert_that(values).contains_only(*[Angry() for _ in range(30)])

    def test_indexing_is_all_or_nothing_across_both_sides(self):
        """One side indexed and the other not is how the lookup started raising again.

        Plain decimals index cleanly, a signalling NaN among the wanted items does not, and asking a set
        about it would hash it after all.
        """
        plain = [decimal.Decimal(index) for index in range(30)]
        signalling = [decimal.Decimal("snan")] * 30
        for call in (
            lambda: only_faults(plain, tuple(signalling)),
            lambda: not_contained_in(signalling, plain),
            lambda: missing_items(plain, tuple(signalling), _is_matcher),
        ):
            with pytest.raises(decimal.InvalidOperation):
                call()

    def test_a_raw_one_shot_value_is_materialised_before_it_is_classified(self):
        assert_that(only_faults(iter([1, 2, 3]), (1, 2, 3))).is_equal_to(([], []))
        assert_that(not_contained_in(iter([1, 2]), [1, 2, 3])).is_empty()
        assert_that(missing_items(iter([1, 2, 3]), (1, 3), _is_matcher)).is_empty()

    def test_a_value_that_can_be_walked_twice_is_handed_back_untouched(self):
        values = [1, 2, 3]
        assert_that(materialized(values)).is_same_as(values)

    @pytest.mark.parametrize("shape", ["one shared iterator", "a fresh generator over shared state"])
    def test_a_value_sharing_one_position_is_not_copied(self, shape):
        """The recorded boundary: being its own iterator is not the only way to have one position.

        Both shapes lose what a first walk read, so a matcher asked twice reports the remainder.  What
        is refused is copying anything that merely lacks a length, which turns a Pydantic model into a
        list of its field pairs, and walking one to find out costs the position that is shared.
        """

        class Shared:
            def __init__(self, items):
                self.items = iter(items)

            def __iter__(self):
                return self.items if shape == "one shared iterator" else (item for item in self.items)

        subject = Shared([1, 2, 3])
        assert_that(materialized(subject)).is_same_as(subject)

    def test_a_value_that_is_not_an_iterator_keeps_its_own_shape(self):
        @dataclasses.dataclass
        class FieldPairs:
            id: int

            def __iter__(self):
                return iter(dataclasses.asdict(self).items())

        model = FieldPairs(id=1)
        assert_that(materialized(model)).is_same_as(model)

    def test_user_code_that_raises_during_the_search_is_not_swallowed_by_the_fallback(self):
        """The boundary of the `try`, which is the whole point of where it is drawn.

        Only hashing may be caught, because only hashing is what the shortcut added. A comparison or a
        matcher raising is user code failing, and this library reports that as a bug in the test rather
        than retrying quietly on the walk. A wider `try` would have hidden it and answered anyway.
        """

        class Exploding:
            def matches(self, value: object) -> bool:
                raise RuntimeError("the matcher itself is broken")

            def describe(self) -> str:
                return "an exploding matcher"

            def describe_mismatch(self, value: object) -> str:
                return "boom"

        values = list(range(60))
        with pytest.raises(RuntimeError, match="matcher itself is broken"):
            missing_items(values, (Exploding(),), _is_matcher)
        with pytest.raises(RuntimeError, match="matcher itself is broken"):
            assert_that(values).contains(Exploding())

    def test_an_operator_that_raises_travels_out_of_both_paths(self):
        class Angry:
            def __eq__(self, other: object) -> bool:
                raise ValueError("comparison is a bug in the value, not a verdict")

            __hash__ = None

        with pytest.raises(ValueError, match="bug in the value"):
            only_faults([Angry()], (Angry(),))
        with pytest.raises(ValueError, match="bug in the value"):
            assert_that([Angry()]).contains_only(Angry())

    def test_duplicates_are_found_when_hashing_and_equality_disagree(self):
        """The other half of the disagreement case: the count has to follow `==`, not the hash."""
        first, second = _ByField(1), _ByField(1)
        assert_that(repeated_items([first, second])).is_length(1)
        with pytest.raises(AssertionFailure):
            assert_that([first, second]).does_not_contain_duplicates()
        assert_that([first, second]).contains_duplicates()

    def test_membership_keeps_its_answer_on_values_that_cannot_be_hashed(self):
        assert_that(only_faults([[1], [2]], ([1], [2]))).is_equal_to(([], []))
        assert_that(not_contained_in([{"a": 1}], [{"a": 1}, {"b": 2}])).is_empty()
        assert_that([[1], [2]]).contains_only([1], [2])

    def test_a_matcher_among_the_wanted_items_keeps_the_walk(self):
        """Matchers are hashable, so a set would look them up by hash and answer the wrong thing.

        What the walk answers, and what this pins, is the behaviour the shipped revision had: a matcher
        is "found" because its own `__eq__` accepts the element, so nothing is reported missing.
        """
        assert_that(only_faults([1, 2], (match.greater_than(0), match.greater_than(1)))).is_equal_to(([], []))
        assert_that([5]).contains(match.greater_than(3))

    def test_nan_is_found_by_identity_on_both_paths(self):
        nan = float("nan")
        assert_that(missing_items([nan], [nan], _is_matcher)).described_as("the same object").is_empty()
        assert_that(only_faults([nan], (nan,))).is_equal_to(([], []))
        assert_that(missing_items([float("nan")], [float("nan")], _is_matcher)).described_as(
            "two distinct NaNs stay unequal"
        ).is_length(1)

    def test_membership_still_drains_a_one_shot_value_once(self):
        assert_that(only_faults(searchable(iter([1, 2])), (1, 2))).is_equal_to(([], []))
        assert_that(not_contained_in(searchable(iter([1])), [1, 2])).is_empty()

    def test_duplicates_are_named_once_in_order_of_first_appearance(self):
        assert_that(repeated_items([3, 1, 3, 2, 1, 3])).is_equal_to([3, 1])
        assert_that(repeated_items([1, 2, 3])).is_empty()
        assert_that(repeated_items([1, 1.0, 2])).is_equal_to([1])
        assert_that(repeated_items([[1], [1], [2]])).described_as("unhashable keeps the walk").is_equal_to([[1]])

    @given(
        values=st.lists(_MIXED_ELEMENTS, max_size=12),
        items=st.lists(_MIXED_ELEMENTS, max_size=6),
    )
    @settings(max_examples=300)
    def test_the_shortcut_answers_what_the_walk_answers(self, values, items):
        """The property the whole optimisation rests on, checked against the walk it replaced.

        The elements are deliberately mixed rather than all safe: a generator of integers and strings
        exercises only the fast half and would have missed both ways the classifier was wrong.
        """
        walked_extra = [item for item in values if item not in items]
        walked_missing = [item for item in items if item not in values]
        assert_that(only_faults(values, items)).is_equal_to((walked_extra, walked_missing))
        assert_that(not_contained_in(values, items)).is_equal_to([item for item in values if item not in items])
        assert_that(missing_items(values, items, _is_matcher)).is_equal_to(walked_missing)

    @given(values=st.lists(_MIXED_ELEMENTS, max_size=12))
    @settings(max_examples=300)
    def test_naming_duplicates_answers_what_counting_answered(self, values):
        counted: list[object] = []
        for value in values:
            if values.count(value) > 1 and not any(value == earlier for earlier in counted):
                counted.append(value)
        assert_that(repeated_items(values)).is_equal_to(counted)

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


class TestAMatcherLooksAtItsValueOnce:
    """The verdict and the reason come from one walk, and every consumer asks for them together.

    Two walks are wrong in two different ways. Over a one-shot value the second sees the remains of the
    first, so the message named items that were there and missed the ones that were not. Over any value
    it runs the user's `key` or comparator again, which is a side effect nobody asked for.
    """

    @pytest.mark.parametrize(
        ("label", "matcher", "expected"),
        [
            ("contains", match.contains(9), "missing 9"),
            ("contains_only", match.contains_only(1, 2), "also had 3"),
            ("is_subset_of", match.is_subset_of([1, 2]), "3 outside it"),
            ("is_sorted", match.is_sorted(), "out of order at index 0"),
        ],
    )
    def test_the_reason_is_right_on_a_one_shot_value(self, label, matcher, expected):
        source = {"contains": [1, 2], "contains_only": [1, 3], "is_subset_of": [3], "is_sorted": [2, 1]}[label]
        result = matcher.evaluate(iter(source))
        assert_that(result.matched).described_as(label).is_false()
        assert_that(result.mismatch).described_as(label).contains(expected)

    def test_a_key_runs_once_per_element_through_the_public_surface(self):
        calls: list[int] = []

        def key(value: int) -> int:
            calls.append(value)
            return value

        with pytest.raises(AssertionFailure):
            assert_that([2, 1]).satisfies(match.is_sorted(key=key))
        assert_that(calls).is_equal_to([2, 1])

    def test_a_key_runs_once_per_element_inside_each(self):
        calls: list[int] = []

        def key(value: int) -> int:
            calls.append(value)
            return value

        with pytest.raises(AssertionFailure):
            assert_that([[2, 1]]).each(match.is_sorted(key=key))
        assert_that(calls).is_equal_to([2, 1])

    def test_an_iterator_as_a_leaf_of_a_structure_keeps_its_reason(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"rows": iter([2, 1])}).matches_structure({"rows": match.is_sorted()})
        assert_that(str(failure.value)).contains("out of order at index 0")

    def test_a_single_walk_matcher_that_passes_inside_a_structure(self):
        assert_that({"rows": [1, 2, 3]}).matches_structure({"rows": match.is_sorted()})
        assert_that({"tags": ["a", "b"]}).matches_structure({"tags": match.contains("a")})

    def test_the_matcher_still_answers_the_same_way_twice(self):
        matcher = match.is_sorted()
        assert_that(matcher.matches([1, 2])).is_true()
        assert_that(matcher.matches([2, 1])).is_false()
        assert_that(matcher.matches([1, 2])).is_true()
