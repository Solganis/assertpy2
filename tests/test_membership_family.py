"""Every assertion that looks for something says why the one thing it did not find is not there.

``contains`` said it first.  Its siblings printed the same two values on both sides of a failure: ``Expected <7>
to be in <7, 8>, but was not``, ``did contain <7> and did not contain <7>``.  The law here is that a failure
explains why the condition of the assertion that failed does not hold, in that assertion's own words: ``is_in``
looks for the value among the items given, a subset for its own element in the superset, an entry for the
value its key holds.

Three facts are said, each of the item looked for: it is a NaN, a candidate reads the same and is of another
plain type, a candidate prints the same and their class compares by identity.  Beside them the nearest row is
named where the candidates are rows.

A negation is left out on purpose.  ``does_not_contain`` fails because what it was handed is there, and the
two printing the same is the explanation, not a contradiction.
"""

from __future__ import annotations

import dataclasses

import pytest

from assertpy2 import AssertionFailure, assert_that, match
from assertpy2.assertpy import AssertionBuilder

_ITEM, _ELEMENT = "the item not found", "an element"
_KEY, _A_KEY = "the key not found", "a key"


@dataclasses.dataclass
class User:
    id: int
    name: str


class _Token:
    def __repr__(self) -> str:
        return "token"


def _message(call) -> str:
    with pytest.raises(AssertionFailure) as caught:
        call()
    return caught.value._message


# (assertion, how a candidate and the item not found are handed to it, what it calls the item, and a candidate)
_SIBLINGS = [
    ("contains", lambda candidate, item: assert_that([candidate, 0]).contains(item), _ITEM, _ELEMENT),
    ("contains", lambda candidate, item: assert_that([candidate, 0]).contains(0, item), _ITEM, _ELEMENT),
    ("contains", lambda candidate, item: assert_that({candidate: 1}).contains(item), _KEY, _A_KEY),
    ("contains_key", lambda candidate, item: assert_that({candidate: 1}).contains_key(candidate, item), _KEY, _A_KEY),
    ("contains_only", lambda candidate, item: assert_that([candidate]).contains_only(item), _ITEM, _ELEMENT),
    (
        "contains_only",
        lambda candidate, item: assert_that([candidate, item]).contains_only(candidate),
        "the element not expected",
        "a given item",
    ),
    ("contains_exactly", lambda candidate, item: assert_that([candidate]).contains_exactly(item), _ITEM, _ELEMENT),
    (
        "contains_exactly_in_any_order",
        lambda candidate, item: assert_that([candidate, 0]).contains_exactly_in_any_order(0, item),
        _ITEM,
        _ELEMENT,
    ),
    ("contains_only_once", lambda candidate, item: assert_that([candidate]).contains_only_once(item), _ITEM, _ELEMENT),
    (
        "contains_sequence",
        lambda candidate, item: assert_that([candidate, 0]).contains_sequence(item, 0),
        _ITEM,
        _ELEMENT,
    ),
    (
        "contains_sequence",
        lambda candidate, item: assert_that([0, candidate]).contains_sequence(0, item),
        _ITEM,
        _ELEMENT,
    ),
    (
        "contains_in_order",
        lambda candidate, item: assert_that([0, candidate]).contains_in_order(0, item),
        _ITEM,
        _ELEMENT,
    ),
    ("is_in", lambda candidate, item: assert_that(item).is_in(candidate, 0), "the value", "a given item"),
    (
        "is_subset_of",
        lambda candidate, item: assert_that([item]).is_subset_of([candidate, 0]),
        "the item missing",
        "an item of the superset",
    ),
    (
        "is_subset_of",
        lambda candidate, item: assert_that({"k": item}).is_subset_of({"k": candidate}),
        "the value missing",
        "the value the superset holds under the key",
    ),
    ("contains_value", lambda candidate, item: assert_that({"k": candidate}).contains_value(item), _ITEM, "a value"),
    (
        "contains_entry",
        lambda candidate, item: assert_that({"k": candidate}).contains_entry({"k": item}),
        "the value expected",
        "the value held",
    ),
    ("contains_entry", lambda candidate, item: assert_that({candidate: 1}).contains_entry({item: 1}), _KEY, _A_KEY),
]

# what it was handed is there, and that is why it failed
_NEGATIONS = {
    "does_not_contain",
    "does_not_contain_key",
    "does_not_contain_value",
    "does_not_contain_entry",
    "does_not_contain_duplicates",
    "does_not_contain_error",
    "contains_none_of",
    "is_not_in",
}
# nothing was handed in to look for
_ASKS_ABOUT_THE_VALUE_ALONE = {"contains_duplicates"}
# text looked for in text, or a class among errors: two that print the same are the same
_HANDED_NO_VALUE_TO_MISTAKE = {"contains_ignoring_case", "contains_any_of", "contains_bytes", "contains_error"}

_SITUATIONS = {
    "another type": (7, "7", "{held} reads the same as {sought} and is of another type: int, not str"),
    "a NaN": (float("nan"), float("nan"), "{sought} is a NaN, and one NaN is not equal to another"),
    "identity": (
        _Token(),
        _Token(),
        "{held} prints the same as {sought}, and their class leaves __eq__ to object, which compares by identity",
    ),
}


class TestEverySiblingSaysWhy:
    @pytest.mark.parametrize("situation", _SITUATIONS)
    @pytest.mark.parametrize(
        ("ask", "sought", "held"),
        [sibling[1:] for sibling in _SIBLINGS],
        ids=[f"{name} #{index}" for index, (name, *_) in enumerate(_SIBLINGS)],
    )
    def test_in_its_own_words_on_a_line_of_its_own(self, ask, sought, held, situation):
        candidate, item, line = _SITUATIONS[situation]
        lines = _message(lambda: ask(candidate, item)).splitlines()
        assert_that(lines).is_length(2)
        assert_that(lines[1]).is_equal_to(line.format(sought=sought, held=held))

    def test_every_assertion_named_as_one_of_the_family_is_decided_about(self):
        # by name, on the builder itself, whichever mixin it comes from: one named otherwise is not seen here
        named = {
            name
            for name in dir(AssertionBuilder)
            if not name.startswith("_") and ("contain" in name or name in {"is_in", "is_not_in", "is_subset_of"})
        }
        said = {name for name, *_ in _SIBLINGS}
        silent = _NEGATIONS | _ASKS_ABOUT_THE_VALUE_ALONE | _HANDED_NO_VALUE_TO_MISTAKE
        assert_that(said & silent).is_empty()
        assert_that(named).is_equal_to(said | silent)

    @pytest.mark.parametrize(
        "ask",
        [
            lambda: assert_that([1]).contains_only_once(float("nan"), "1"),
            lambda: assert_that([1]).contains_only("1", float("nan")),
            lambda: assert_that({"a": 7}).contains_entry({"a": "7"}, {"b": 1}),
            lambda: assert_that({"a": 7}).contains_value("7", float("nan")),
            lambda: assert_that(["7", float("nan")]).is_subset_of([7, 0]),
            lambda: assert_that({"a": "7", "b": 1}).is_subset_of({"a": 7}),
            lambda: assert_that([7, "x"]).contains_exactly("7", "y"),
        ],
    )
    def test_several_not_found_get_nothing_each_would_need_its_own(self, ask):
        assert_that(_message(ask).splitlines()).is_length(1)
        assert_that(_message(ask)).does_not_contain("Closest").does_not_contain("holds").does_not_contain("no key")

    def test_an_item_the_collection_holds_out_of_place_is_not_said_to_be_missing(self):
        message = _message(lambda: assert_that([7, "7"]).contains_sequence("7", 7))
        assert_that(message).is_equal_to(
            "Expected <[7, '7']> to contain sequence <'7', 7>, but did not. The longest run that matched was <7>."
        )
        message = _message(lambda: assert_that(["7", 0, 7]).contains_in_order(0, "7"))
        assert_that(message).is_equal_to(
            "Expected <['7', 0, 7]> to contain <0, '7'> in order, but <7> did not follow after <0>."
        )

    def test_a_collection_that_cannot_be_searched_again_costs_only_the_line(self):
        class Once:
            asked = 0

            def __eq__(self, other: object) -> bool:
                Once.asked += 1
                if Once.asked > 1:
                    raise RuntimeError("asked twice")
                return False

            __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

            def __repr__(self) -> str:
                return "once"

        message = _message(lambda: assert_that([Once()]).contains_in_order(float("nan")))
        assert_that(message).is_equal_to("Expected <[once]> to contain <nan> in order, but <nan> did not follow.")
        assert_that(Once.asked).is_equal_to(2)

    def test_a_matcher_is_no_item(self):
        message = _message(lambda: assert_that([1.0]).contains_only(match.is_instance_of(str)))
        assert_that(message.splitlines()).is_length(1)


class TestTheNearestRow:
    ROWS = (User(1, "ann"), User(2, "bob"))

    def test_of_the_items_given_for_a_value_that_is_in_none(self):
        message = _message(lambda: assert_that(User(2, "rob")).is_in(*self.ROWS))
        assert_that(message).is_equal_to(
            "Expected <User(id=2, name='rob')> to be in <User(id=1, name='ann'), User(id=2, name='bob')>, but was not."
            " Closest item <User(id=2, name='bob')> differs at .name ('rob' != 'bob')."
        )

    def test_of_the_superset_for_the_element_it_lacks(self):
        message = _message(lambda: assert_that([User(2, "rob")]).is_subset_of(list(self.ROWS)))
        assert_that(message).ends_with(
            "but <User(id=2, name='rob')> was missing."
            " Closest item <User(id=2, name='bob')> differs at .name ('rob' != 'bob')."
        )

    def test_of_the_values_of_a_dict(self):
        message = _message(lambda: assert_that({"first": User(2, "bob")}).contains_value(User(2, "rob")))
        assert_that(message).ends_with(" Closest value <User(id=2, name='bob')> differs at .name ('bob' != 'rob').")

    def test_for_the_one_item_not_found_among_several_asked_for(self):
        message = _message(lambda: assert_that(list(self.ROWS)).contains(User(1, "ann"), User(2, "rob")))
        assert_that(message).ends_with(
            "but did not contain <User(id=2, name='rob')>."
            " Closest element <User(id=2, name='bob')> differs at .name ('bob' != 'rob')."
        )

    @pytest.mark.parametrize("asked", ["contains_only", "contains_exactly", "contains_exactly_in_any_order"])
    def test_among_the_elements_nobody_asked_for_before_any_other(self, asked):
        # `bo` is as near to `rob` as `bob` is, and it was asked for: what stands in for `rob` is `bob`
        held = [User(2, "bo"), User(2, "bob")]
        message = _message(lambda: getattr(assert_that(held), asked)(User(2, "bo"), User(2, "rob")))
        assert_that(message).contains(
            " Closest unexpected element <User(id=2, name='bob')> differs at .name ('bob' != 'rob')."
        )

    def test_a_key_one_side_lacks_is_said_to_be_missing_and_not_none(self):
        message = _message(lambda: assert_that([{"id": 2}]).contains({"id": 2, "name": None}))
        assert_that(message).ends_with(" Closest element <{'id': 2}> differs at name (<missing> != None).")
        message = _message(lambda: assert_that([{"id": 2, "name": None}]).contains({"id": 2}))
        assert_that(message).ends_with(
            " Closest element <{'id': 2, 'name': None}> differs at name (None != <missing>)."
        )

    def test_among_every_element_where_none_is_left_over(self):
        message = _message(lambda: assert_that([User(2, "bob")]).contains_only(User(2, "bob"), User(2, "rob")))
        assert_that(message).ends_with(" Closest element <User(id=2, name='bob')> differs at .name ('bob' != 'rob').")
        message = _message(lambda: assert_that([User(2, "bob")]).contains_only_once(User(2, "rob")))
        assert_that(message).ends_with(" Closest element <User(id=2, name='bob')> differs at .name ('bob' != 'rob').")

    def test_an_order_that_differs_names_no_row(self):
        message = _message(lambda: assert_that([1, 2]).contains_exactly(2, 1))
        assert_that(message).is_equal_to(
            "Expected <[1, 2]> to contain exactly <2, 1>, but did not. Same items, but the order differs at index 0."
        )


class TestContainsOnly:
    def test_the_element_it_has_and_the_item_it_lacks_are_told_apart_where_they_print_the_same(self):
        message = _message(lambda: assert_that([7, 8]).contains_only("7", 8))
        assert_that(message.splitlines()).is_equal_to(
            [
                "Expected <[7, 8]> to contain only <'7', 8>, but did contain <7:int> and did not contain <7:str>.",
                "an element reads the same as the item not found and is of another type: int, not str",
            ]
        )

    def test_two_that_print_otherwise_are_printed_as_they_were(self):
        message = _message(lambda: assert_that([7, 8]).contains_only(8, 9))
        assert_that(message).is_equal_to(
            "Expected <[7, 8]> to contain only <8, 9>, but did contain <7> and did not contain <9>."
        )

    def test_several_on_one_side_are_printed_as_a_list(self):
        message = _message(lambda: assert_that([1, 2, 3]).contains_only(3, 4))
        assert_that(message).is_equal_to(
            "Expected <[1, 2, 3]> to contain only <3, 4>, but did contain <1, 2> and did not contain <4>."
        )

    def test_an_element_nobody_asked_for_has_no_nearest_item(self):
        message = _message(lambda: assert_that([User(2, "bob"), User(2, "rob")]).contains_only(User(2, "bob")))
        assert_that(message).ends_with("but did contain <User(id=2, name='rob')>.")

    def test_the_line_looks_among_every_element_and_not_the_left_over_alone(self):
        message = _message(lambda: assert_that([7, 0]).contains_only(7, "7"))
        assert_that(message.splitlines()).is_equal_to(
            [
                "Expected <[7, 0]> to contain only <7, '7'>, but did contain <0> and did not contain <7>.",
                "an element reads the same as the item not found and is of another type: int, not str",
            ]
        )

    def test_an_element_nobody_asked_for_beside_an_item_that_reads_the_same(self):
        message = _message(lambda: assert_that([7, "7"]).contains_only(7))
        assert_that(message.splitlines()).is_equal_to(
            [
                "Expected <[7, '7']> to contain only <7>, but did contain <7>.",
                "a given item reads the same as the element not expected and is of another type: int, not str",
            ]
        )


class TestCountedItIsOneShortOfAnItemItHas:
    """``contains_exactly`` counts.  One ``"7"`` short of two, the collection still has ``"7"``: "not found" is
    false of it, and so is "not expected" of one too many."""

    @pytest.mark.parametrize(
        "ask",
        [
            lambda: assert_that([7, "7"]).contains_exactly(7, "7", "7"),
            lambda: assert_that([7, "7"]).contains_exactly_in_any_order("7", "7", 7),
            lambda: assert_that([7, "7", "7"]).contains_exactly(7, "7"),
            lambda: assert_that([7, "7", "7"]).contains_exactly_in_any_order("7", 7),
            lambda: assert_that([User(1, "ann"), User(1, "bob")]).contains_exactly(
                User(1, "ann"), User(1, "bob"), User(1, "bob")
            ),
        ],
    )
    def test_nothing_is_said_of_it(self, ask):
        message = _message(ask)
        assert_that(message.splitlines()).is_length(1)
        assert_that(message).ends_with("but did not.")

    def test_a_collection_that_cannot_be_searched_again_is_taken_to_hold_it(self):
        class Once:
            asked = 0

            def __eq__(self, other: object) -> bool:
                Once.asked += 1
                if Once.asked > 1:
                    raise RuntimeError("asked twice")
                return False

            __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

            def __repr__(self) -> str:
                return "once"

        message = _message(lambda: assert_that([Once()]).contains_exactly_in_any_order(float("nan")))
        assert_that(message).is_equal_to("Expected <[once]> to contain exactly <nan> in any order, but did not.")
        assert_that(Once.asked).is_equal_to(2)


class TestAnEntryNotFound:
    def test_values_that_cannot_be_read_again_cost_only_what_is_said_of_them(self):
        class Once(dict):
            asked = 0

            def values(self):
                Once.asked += 1
                if Once.asked > 1:
                    raise RuntimeError("asked twice")
                return super().values()

        message = _message(lambda: assert_that(Once(a=7)).contains_value("7"))
        assert_that(message).is_equal_to("Expected <{'a': 7}> to contain values <7>, but did not contain <7>.")
        assert_that(Once.asked).is_equal_to(2)

    def test_says_what_its_key_holds(self):
        message = _message(lambda: assert_that({"status": "inactive", "n": 1}).contains_entry(status="active"))
        assert_that(message).is_equal_to(
            "Expected <{'status': 'inactive', 'n': 1}> to contain entries <{'status': 'active'}>,"
            " but did not contain <{'status': 'active'}>. Key <status> holds <'inactive'>."
        )

    def test_says_the_key_is_not_there(self):
        message = _message(lambda: assert_that({"a": 1}).contains_entry(b=1))
        assert_that(message).ends_with("but did not contain <{'b': 1}>. There is no key <b>.")

    def test_and_why_the_value_held_is_not_the_one_expected(self):
        message = _message(lambda: assert_that({"id": 7, "n": 1}).contains_entry({"id": "7"}))
        assert_that(message.splitlines()).is_equal_to(
            [
                "Expected <{'id': 7, 'n': 1}> to contain entries <{'id': '7'}>, but did not contain <{'id': '7'}>."
                " Key <id> holds <7>.",
                "the value held reads the same as the value expected and is of another type: int, not str",
            ]
        )

    def test_a_mapping_that_cannot_be_read_again_costs_only_the_sentence(self):
        class Once(dict):
            asked = 0

            def __contains__(self, key: object) -> bool:
                self.asked += 1
                if self.asked > 1:
                    raise RuntimeError("asked twice")
                return False

        message = _message(lambda: assert_that(Once(a=1)).contains_entry(b=1))
        assert_that(message).is_equal_to(
            "Expected <{'a': 1}> to contain entries <{'b': 1}>, but did not contain <{'b': 1}>."
        )

    def test_a_pair_whose_key_no_superset_has_is_missing_for_that(self):
        message = _message(lambda: assert_that({"a": float("nan")}).is_subset_of({"b": 1}))
        assert_that(message.splitlines()).is_length(1)

    def test_a_superset_that_cannot_be_read_again_costs_only_the_line(self):
        class Once:
            asked = 0

            def __hash__(self) -> int:
                return 1

            def __eq__(self, other: object) -> bool:
                Once.asked += 1
                if Once.asked > 1:
                    raise RuntimeError("asked twice")
                return False

        nan = float("nan")
        message = _message(lambda: assert_that({Once(): nan}).is_subset_of({Once(): nan}))
        assert_that(message.splitlines()).is_length(1)
        assert_that(Once.asked).is_equal_to(2)
