import collections.abc
import datetime
import inspect
import io
import itertools
import sys
import types
import typing

import pytest

from assertpy2 import AssertionFailure, assert_conforms, assert_that, match, soft_assertions
from assertpy2._engine import _contract
from assertpy2._engine._contract import UncheckableDriftError, _declared_keys, contract_drift, shape, shape_diff
from assertpy2.matchers import (
    EachMatcher,
    IgnoreMatcher,
    IsNonEmptyStringMatcher,
    IsUuidMatcher,
    StructureMatcher,
)


class TestIgnoreMatcher:
    def test_matches_anything(self):
        matcher = match.ignore()
        assert_that(matcher.matches(None)).is_true()
        assert_that(matcher.matches(42)).is_true()
        assert_that(matcher.matches("hello")).is_true()
        assert_that(matcher.matches([1, 2, 3])).is_true()
        assert_that(matcher.matches({})).is_true()

    def test_describe(self):
        assert_that(match.ignore().describe()).is_equal_to("anything (ignored)")

    def test_is_instance(self):
        assert_that(match.ignore()).is_instance_of(IgnoreMatcher)


class TestIsUuidMatcher:
    def test_matches_valid_uuid4(self):
        assert_that(match.is_uuid().matches("550e8400-e29b-41d4-a716-446655440000")).is_true()

    def test_matches_valid_uuid1(self):
        assert_that(match.is_uuid().matches("6ba7b810-9dad-11d1-80b4-00c04fd430c8")).is_true()

    def test_does_not_match_invalid(self):
        assert_that(match.is_uuid().matches("not-a-uuid")).is_false()

    def test_does_not_match_empty(self):
        assert_that(match.is_uuid().matches("")).is_false()

    def test_does_not_match_non_string(self):
        assert_that(match.is_uuid().matches(42)).is_false()
        assert_that(match.is_uuid().matches(None)).is_false()

    def test_describe(self):
        assert_that(match.is_uuid().describe()).is_equal_to("a valid UUID string")

    def test_is_instance(self):
        assert_that(match.is_uuid()).is_instance_of(IsUuidMatcher)


class TestIsNonEmptyStringMatcher:
    def test_matches_non_empty(self):
        assert_that(match.is_non_empty_string().matches("hello")).is_true()
        assert_that(match.is_non_empty_string().matches(" ")).is_true()

    def test_does_not_match_empty(self):
        assert_that(match.is_non_empty_string().matches("")).is_false()

    def test_does_not_match_non_string(self):
        assert_that(match.is_non_empty_string().matches(42)).is_false()
        assert_that(match.is_non_empty_string().matches(None)).is_false()
        assert_that(match.is_non_empty_string().matches(["a"])).is_false()

    def test_describe(self):
        assert_that(match.is_non_empty_string().describe()).is_equal_to("a non-empty string")

    def test_is_instance(self):
        assert_that(match.is_non_empty_string()).is_instance_of(IsNonEmptyStringMatcher)


class TestEachMatcher:
    def test_all_match(self):
        matcher = match.each_item(match.is_positive())
        assert_that(matcher.matches([1, 2, 3])).is_true()

    def test_some_do_not_match(self):
        matcher = match.each_item(match.is_positive())
        assert_that(matcher.matches([1, -2, 3])).is_false()

    def test_empty_iterable(self):
        matcher = match.each_item(match.is_positive())
        assert_that(matcher.matches([])).is_true()

    def test_non_iterable(self):
        matcher = match.each_item(match.is_positive())
        assert_that(matcher.matches(42)).is_false()

    def test_describe(self):
        matcher = match.each_item(match.is_positive())
        assert_that(matcher.describe()).is_equal_to("each item matching a positive value")

    def test_describe_mismatch_with_failing_item(self):
        matcher = match.each_item(match.is_positive())
        result = matcher.describe_mismatch([1, -2, 3])
        assert_that(result).contains("index 1")
        assert_that(result).contains("-2")

    def test_describe_mismatch_non_iterable(self):
        matcher = match.each_item(match.is_positive())
        result = matcher.describe_mismatch(42)
        assert_that(result).contains("not iterable")

    def test_is_instance(self):
        assert_that(match.each_item(match.is_positive())).is_instance_of(EachMatcher)

    def test_composition(self):
        matcher = match.each_item(match.between(1, 10) & match.is_instance_of(int))
        assert_that(matcher.matches([1, 5, 10])).is_true()
        assert_that(matcher.matches([1, 5, 11])).is_false()

    def test_describe_mismatch_all_match(self):
        matcher = match.each_item(match.is_positive())
        assert_that(matcher.describe_mismatch([1, 2, 3])).is_equal_to("was <[1, 2, 3]>")

    def test_describe_mismatch_carries_what_the_item_matcher_found(self):
        """Only the requirement was named, so the field a record failed on was left for the reader to find."""
        matcher = match.each_item(match.structure({"city": "Paris"}))
        assert_that(matcher.describe_mismatch([{"city": "Paris"}, {"city": "Oslo"}])).is_equal_to(
            "item at index 1 <{'city': 'Oslo'}> did not match a mapping matching structure {city: <Paris>} "
            "(at <city>: expected <Paris>, but was <Oslo>)"
        )

    def test_each_item_is_asked_once_for_its_verdict_and_its_reason(self):
        class RefusesOnce:
            def __init__(self):
                self.asked = 0

            def matches(self, value):
                self.asked += 1
                return self.asked > 1

            def describe(self):
                return "asked twice"

            def describe_mismatch(self, value):
                return f"was asked {self.asked} time"

        outcome = match.each_item(RefusesOnce()).evaluate([7])
        assert_that(outcome.matched).is_false()
        assert_that(outcome.mismatch).is_equal_to("item at index 0 <7> did not match asked twice (was asked 1 time)")

    def test_an_item_that_is_its_own_iterator_is_not_read_again_for_a_reason(self):
        """Read again, the remainder was described as the item: `<-3>` at index 0, where `-2` had failed."""
        outcome = match.each_item(match.each_item(match.greater_than(0))).evaluate([iter([1, -2, -3])])
        assert_that(outcome.mismatch).ends_with("did not match each item matching a value greater than <0>")

    def test_an_item_that_refuses_to_be_iterated_still_gets_its_failure_described(self):
        """A closed file answers `iter()` with `ValueError`, which replaced the failure it was asked about."""
        closed = io.StringIO()
        closed.close()
        outcome = match.each_item(match.is_none()).evaluate([closed])
        assert_that(outcome.matched).is_false()
        assert_that(outcome.mismatch).starts_with("item at index 0 <")

    def test_an_endless_item_is_answered_rather_than_read_for_a_reason(self):
        endless = itertools.chain([5], itertools.repeat(0))
        outcome = match.each_item(match.each_item(match.less_than(3))).evaluate([endless])
        assert_that(outcome.matched).is_false()


class TestStructureMatcher:
    def test_basic_match(self):
        matcher = match.structure({"name": match.is_non_empty_string(), "age": match.is_positive()})
        assert_that(matcher.matches({"name": "Alice", "age": 30})).is_true()

    def test_missing_key(self):
        matcher = match.structure({"name": match.is_non_empty_string(), "age": match.is_positive()})
        assert_that(matcher.matches({"name": "Alice"})).is_false()

    def test_value_mismatch(self):
        matcher = match.structure({"age": match.is_positive()})
        assert_that(matcher.matches({"age": -1})).is_false()

    def test_extra_keys_allowed(self):
        matcher = match.structure({"name": match.is_non_empty_string()})
        assert_that(matcher.matches({"name": "Alice", "extra": "field"})).is_true()

    def test_raw_value_equality(self):
        matcher = match.structure({"status": "active", "count": 5})
        assert_that(matcher.matches({"status": "active", "count": 5})).is_true()
        assert_that(matcher.matches({"status": "inactive", "count": 5})).is_false()

    def test_nested_dict(self):
        matcher = match.structure({"user": {"name": match.is_non_empty_string(), "role": "admin"}})
        assert_that(matcher.matches({"user": {"name": "Alice", "role": "admin"}})).is_true()
        assert_that(matcher.matches({"user": {"name": "Alice", "role": "user"}})).is_false()

    def test_nested_not_dict(self):
        matcher = match.structure({"user": {"name": match.is_non_empty_string()}})
        assert_that(matcher.matches({"user": "not a dict"})).is_false()

    def test_non_dict_value(self):
        matcher = match.structure({"a": 1})
        assert_that(matcher.matches("not a dict")).is_false()
        assert_that(matcher.matches(42)).is_false()
        assert_that(matcher.matches(None)).is_false()

    def test_describe(self):
        matcher = match.structure({"name": match.is_non_empty_string(), "age": 30})
        desc = matcher.describe()
        assert_that(desc).contains("name: a non-empty string")
        assert_that(desc).contains("age: <30>")

    def test_describe_nested(self):
        matcher = match.structure({"user": {"name": match.is_non_empty_string()}})
        desc = matcher.describe()
        assert_that(desc).contains("user: {name: a non-empty string}")

    def test_describe_mismatch_missing_key(self):
        matcher = match.structure({"name": match.is_non_empty_string()})
        result = matcher.describe_mismatch({"age": 30})
        assert_that(result).contains("missing key <name>")

    def test_describe_mismatch_value_fail(self):
        matcher = match.structure({"age": match.is_positive()})
        result = matcher.describe_mismatch({"age": -1})
        assert_that(result).contains("at <age>")
        assert_that(result).contains("a positive value")

    def test_describe_mismatch_non_dict(self):
        matcher = match.structure({"a": 1})
        result = matcher.describe_mismatch("not a dict")
        assert_that(result).contains("was not a mapping")

    def test_describe_mismatch_nested_path(self):
        matcher = match.structure({"user": {"name": match.is_non_empty_string()}})
        result = matcher.describe_mismatch({"user": {"name": ""}})
        assert_that(result).contains("user.name")

    def test_nested_structure_matcher_matches(self):
        matcher = match.structure({"address": match.structure({"city": match.equal_to("NYC")})})
        assert_that(matcher.matches({"address": {"city": "NYC"}})).is_true()

    def test_nested_structure_matcher_joined_path(self):
        matcher = match.structure({"address": match.structure({"city": match.equal_to("NYC")})})
        result = matcher.describe_mismatch({"address": {"city": "LA"}})
        assert_that(result).contains("address.city")

    def test_nested_structure_matcher_non_dict(self):
        matcher = match.structure({"address": match.structure({"city": match.equal_to("NYC")})})
        result = matcher.describe_mismatch({"address": "not a dict"})
        assert_that(result).contains("at <address>")

    def test_is_instance(self):
        assert_that(match.structure({"a": 1})).is_instance_of(StructureMatcher)

    def test_with_ignore(self):
        matcher = match.structure({"id": match.ignore(), "name": match.is_non_empty_string()})
        assert_that(matcher.matches({"id": 12345, "name": "Alice"})).is_true()
        assert_that(matcher.matches({"id": None, "name": "Bob"})).is_true()

    def test_with_uuid(self):
        matcher = match.structure({"id": match.is_uuid()})
        assert_that(matcher.matches({"id": "550e8400-e29b-41d4-a716-446655440000"})).is_true()
        assert_that(matcher.matches({"id": "not-uuid"})).is_false()

    def test_with_each_item(self):
        matcher = match.structure({"scores": match.each_item(match.between(0, 100))})
        assert_that(matcher.matches({"scores": [85, 90, 78]})).is_true()
        assert_that(matcher.matches({"scores": [85, 101, 78]})).is_false()

    def test_deeply_nested(self):
        matcher = match.structure({"a": {"b": {"c": match.equal_to(42)}}})
        assert_that(matcher.matches({"a": {"b": {"c": 42}}})).is_true()
        assert_that(matcher.matches({"a": {"b": {"c": 99}}})).is_false()

    def test_describe_mismatch_raw_value(self):
        matcher = match.structure({"status": "active"})
        result = matcher.describe_mismatch({"status": "inactive"})
        assert_that(result).contains("at <status>")
        assert_that(result).contains("expected <active>")
        assert_that(result).contains("was <inactive>")

    def test_describe_mismatch_all_match(self):
        matcher = match.structure({"a": 1})
        assert_that(matcher.describe_mismatch({"a": 1})).is_equal_to("was <{'a': 1}>")

    def test_circular_reference_detected(self):
        circular = {}
        circular["self"] = circular
        spec = {}
        spec["self"] = spec
        matcher = match.structure(spec)
        assert_that(matcher.matches(circular)).is_false()
        assert_that(matcher.describe_mismatch(circular)).contains("circular reference")

    def test_deep_nesting(self):
        value = {"a": 1}
        spec = {"a": 1}
        current_v = value
        current_s = spec
        for _i in range(20):
            inner_v = {"a": 1}
            inner_s = {"a": 1}
            current_v["nested"] = inner_v
            current_s["nested"] = inner_s
            current_v = inner_v
            current_s = inner_s
        matcher = match.structure(spec)
        assert_that(matcher.matches(value)).is_true()

    def test_shared_subobject_across_keys_is_not_a_cycle(self):
        # reuse under sibling keys is a DAG, not a cycle: matches() must scope its visited-set per path
        frag_spec = {"n": match.is_positive()}
        spec = {"a": frag_spec, "b": frag_spec}
        frag_val = {"n": 5}
        value = {"a": frag_val, "b": frag_val}
        assert_that(match.structure(spec).matches(value)).is_true()
        assert_that(value).satisfies(match.structure(spec))


def _texts(mismatches):
    """A mismatch list with its paths rendered, which is the half these tests are about."""
    return [(path.text, actual, description) for path, actual, description in mismatches]


class TestCollectMismatches:
    def test_collects_all_failing_fields(self):
        matcher = match.structure({"a": match.is_positive(), "b": match.is_positive(), "c": match.is_positive()})
        result = matcher.collect_mismatches({"a": -1, "b": 5, "c": -3})
        assert_that([entry[0].text for entry in result]).is_equal_to(["a", "c"])

    def test_empty_when_all_match(self):
        matcher = match.structure({"a": match.is_positive(), "status": "active"})
        assert_that(matcher.collect_mismatches({"a": 5, "status": "active"})).is_empty()

    def test_nested_structure_matcher_joins_path(self):
        matcher = match.structure({"address": match.structure({"city": match.equal_to("NYC")})})
        result = matcher.collect_mismatches({"address": {"city": "LA"}})
        assert_that(result[0][0].text).is_equal_to("address.city")

    def test_missing_key_recorded(self):
        matcher = match.structure({"name": match.is_non_empty_string()})
        path, actual, description = matcher.collect_mismatches({})[0]
        assert_that(path.text).is_equal_to("name")
        assert_that(repr(actual)).is_equal_to("<missing>")
        assert_that(description).is_equal_to("a non-empty string")

    def test_nested_structure_matcher_against_non_dict(self):
        matcher = match.structure({"user": match.structure({"name": match.is_non_empty_string()})})
        result = matcher.collect_mismatches({"user": "not a dict"})
        assert_that(result[0][0].text).is_equal_to("user")

    def test_plain_nested_dict_against_non_dict(self):
        matcher = match.structure({"user": {"name": match.is_non_empty_string()}})
        path, _actual, description = matcher.collect_mismatches({"user": "not a dict"})[0]
        assert_that(path.text).is_equal_to("user")
        assert_that(description).is_equal_to("a mapping")

    def test_plain_nested_dict_recurses(self):
        matcher = match.structure({"user": {"role": "admin"}})
        result = matcher.collect_mismatches({"user": {"role": "guest"}})
        assert_that(result[0][0].text).is_equal_to("user.role")

    def test_raw_value_mismatch(self):
        matcher = match.structure({"status": "active"})
        path, actual, description = matcher.collect_mismatches({"status": "inactive"})[0]
        assert_that(path.text).is_equal_to("status")
        assert_that(actual).is_equal_to("inactive")
        assert_that(description).is_equal_to("<active>")

    def test_circular_reference(self):
        circular = {}
        circular["self"] = circular
        spec = {}
        spec["self"] = spec
        result = match.structure(spec).collect_mismatches(circular)
        assert_that(result[0][1]).is_equal_to("<circular ref>")


class TestMatchesStructureMethod:
    def test_basic(self):
        user = {"name": "Alice", "age": 30}
        assert_that(user).matches_structure({"name": match.is_non_empty_string(), "age": match.between(18, 120)})

    def test_failure_missing_key(self):
        with pytest.raises(AssertionError, match="missing key"):
            assert_that({"name": "Alice"}).matches_structure(
                {"name": match.is_non_empty_string(), "email": match.is_non_empty_string()}
            )

    def test_failure_value_mismatch(self):
        with pytest.raises(AssertionError, match="at <age>"):
            assert_that({"age": -5}).matches_structure({"age": match.is_positive()})

    def test_the_mismatch_names_the_offending_value(self):
        # every assertion matched on the path, so the detail was free to describe None and name only the key
        with pytest.raises(AssertionError) as failure:
            assert_that({"age": 10}).matches_structure({"age": match.greater_than(18)})
        assert_that(str(failure.value)).contains("but was <10>").does_not_contain("but was <None>")

    def test_nested(self):
        data = {"user": {"name": "Alice", "settings": {"theme": "dark"}}}
        assert_that(data).matches_structure(
            {"user": {"name": match.is_non_empty_string(), "settings": {"theme": "dark"}}}
        )

    def test_non_dict_val(self):
        with pytest.raises(TypeError, match="val must be a mapping"):
            assert_that("not a dict").matches_structure({"a": 1})

    def test_non_dict_spec(self):
        with pytest.raises(TypeError, match="given spec arg must be a dict"):
            assert_that({"a": 1}).matches_structure("not a dict")

    def test_chaining(self):
        data = {"name": "Alice", "age": 30}
        assert_that(data).matches_structure({"name": match.is_non_empty_string()}).contains_key("age")

    def test_with_uuid_and_ignore(self):
        response = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "created_at": "2024-01-01T00:00:00Z",
            "name": "Test",
        }
        assert_that(response).matches_structure(
            {
                "id": match.is_uuid(),
                "created_at": match.ignore(),
                "name": match.equal_to("Test"),
            }
        )

    def test_error_message_contains_structure_description(self):
        with pytest.raises(AssertionError, match="to match structure"):
            assert_that({"x": 1}).matches_structure({"x": match.is_non_empty_string()})

    def test_failure_attaches_structured_diff(self):
        value = {"role": "guest", "address": {"city": "LA"}}
        try:
            assert_that(value).matches_structure(
                {"role": match.is_in("admin", "user"), "address": match.structure({"city": match.equal_to("NYC")})}
            )
        except AssertionFailure as exc:
            assert_that(exc.diff.kind).is_equal_to("match")
            assert_that([entry.path for entry in exc.diff.entries]).contains("role", "address.city")
            assert_that(exc.actual).is_equal_to(value)
            assert_that(exc.expected).is_not_none()
        else:
            raise AssertionError("expected AssertionFailure") from None


class _SpecModel:
    """Duck-types a pydantic v2 model (exposes a recursive model_dump()) for the dependency-free
    structural-matching tests.  __eq__ is left at the object default on purpose, so
    ``model == match.structure(...)`` falls back to the matcher's reflected __eq__, exactly as real
    pydantic, whose __eq__ returns NotImplemented for non-model operands.
    """

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def model_dump(self):
        return {
            key: value.model_dump() if isinstance(value, _SpecModel) else value for key, value in self.__dict__.items()
        }


class TestStructureMatcherOnModel:
    """Structural matching accepts pydantic-style models (model_dump()), via duck-type without the dep."""

    def test_matches_structure_on_model(self):
        user = _SpecModel(id=1, name="Alice")
        assert_that(user).matches_structure({"id": match.is_positive(), "name": match.is_non_empty_string()})

    def test_matches_structure_on_model_failure(self):
        user = _SpecModel(id=-1, name="Alice")
        with pytest.raises(AssertionError, match="at <id>"):
            assert_that(user).matches_structure({"id": match.is_positive()})

    def test_matches_structure_on_nested_model(self):
        user = _SpecModel(id=1, address=_SpecModel(city="NYC"))
        assert_that(user).matches_structure({"id": match.is_positive(), "address": {"city": match.equal_to("NYC")}})

    def test_satisfies_structure_on_model(self):
        user = _SpecModel(id=1, name="Alice")
        assert_that(user).satisfies(match.structure({"id": match.is_positive()}))

    def test_each_structure_over_models(self):
        users = [_SpecModel(id=1), _SpecModel(id=2)]
        assert_that(users).each(match.structure({"id": match.is_positive()}))

    def test_model_equals_structure_matcher(self):
        user = _SpecModel(id=1, name="Alice")
        spec = match.structure({"id": match.is_positive(), "name": match.is_non_empty_string()})
        assert_that(user == spec).is_true()

    def test_model_not_equals_structure_matcher_on_mismatch(self):
        user = _SpecModel(id=-1)
        assert_that(user == match.structure({"id": match.is_positive()})).is_false()

    def test_matcher_matches_model_directly(self):
        matcher = match.structure({"id": match.is_positive()})
        assert_that(matcher.matches(_SpecModel(id=5))).is_true()

    def test_describe_mismatch_on_model(self):
        matcher = match.structure({"id": match.is_positive()})
        assert_that(matcher.describe_mismatch(_SpecModel(id=-1))).contains("at <id>")

    def test_real_pydantic_model(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Address(BaseModel):
            city: str

        class User(BaseModel):
            id: int
            name: str
            address: Address

        user = User(id=1, name="Alice", address=Address(city="NYC"))
        assert_that(user).matches_structure(
            {"id": match.is_positive(), "name": match.is_non_empty_string(), "address": {"city": match.equal_to("NYC")}}
        )
        assert_that(user).satisfies(match.structure({"id": match.is_positive()}))
        assert_that(user == match.structure({"id": match.is_positive()})).is_true()
        with pytest.raises(AssertionError, match="at <id>"):
            assert_that(User(id=-1, name="Bob", address=Address(city="LA"))).matches_structure(
                {"id": match.is_positive()}
            )


class _AmbiguousArray:
    """Array-like: element-wise ``==`` whose truth value is ambiguous (an ndarray stand-in)."""

    def __array__(self):
        return None

    def __eq__(self, other):
        return self

    def __bool__(self):
        raise ValueError("ambiguous")

    __hash__ = object.__hash__


class TestArrayLeavesInStructure:
    def test_raw_array_leaf_raises_actionable_error(self):
        with pytest.raises(TypeError, match="matches_structure"):
            assert_that({"a": _AmbiguousArray()}).matches_structure({"a": _AmbiguousArray()})

    def test_matcher_wrapped_array_leaf_records_mismatch(self):
        with pytest.raises(AssertionError, match="a value equal to"):
            assert_that({"a": _AmbiguousArray()}).matches_structure({"a": match.equal_to(_AmbiguousArray())})

    def test_matcher_that_cannot_evaluate_records_mismatch(self):
        with pytest.raises(AssertionError, match="at <n>"):
            assert_that({"n": "not-a-number"}).matches_structure({"n": match.is_positive()})


class TestModelNestedInsideDict:
    """A model under a plain dict is normalized per level, so it matches specs and keeps leaf paths."""

    def test_model_under_nested_structure_matcher_keeps_leaf_path(self):
        value = {"address": _SpecModel(city="LA")}
        matcher = match.structure({"address": match.structure({"city": match.equal_to("NYC")})})
        result = matcher.collect_mismatches(value)
        assert_that(result[0][0].text).is_equal_to("address.city")

    def test_model_under_plain_dict_spec_matches(self):
        value = {"address": _SpecModel(city="NYC")}
        assert_that(match.structure({"address": {"city": "NYC"}}).matches(value)).is_true()

    def test_model_under_plain_dict_spec_keeps_leaf_path(self):
        value = {"address": _SpecModel(city="LA")}
        result = match.structure({"address": {"city": "NYC"}}).collect_mismatches(value)
        assert_that(result[0][0].text).is_equal_to("address.city")

    def test_matches_structure_failure_shows_model_leaf_path(self):
        with pytest.raises(AssertionError, match=r"at <address\.city>"):
            assert_that({"address": _SpecModel(city="LA")}).matches_structure(
                {"address": match.structure({"city": "NYC"})}
            )


class TestAssertConforms:
    @staticmethod
    def _order_model():
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Order(BaseModel):
            id: int
            total: float
            currency: str = "USD"

        return Order

    def test_valid_continues_over_validated_model(self):
        order_cls = self._order_model()
        result = assert_conforms({"id": 1, "total": 4.2}, order_cls)
        assert_that(result.val).is_instance_of(order_cls)

    def test_coerces_and_defaults(self):
        order_cls = self._order_model()
        validated = assert_conforms({"id": "7", "total": 4.2}, order_cls).value
        assert_that(validated.id).is_equal_to(7)
        assert_that(validated.currency).is_equal_to("USD")

    def test_capstone_value_chain(self):
        order_cls = self._order_model()
        order = assert_conforms({"id": 1, "total": 4.2}, order_cls).value
        assert_that(order.total).is_greater_than(0)

    def test_invalid_fails_with_validation_errors(self):
        order_cls = self._order_model()
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms({"id": "notint", "total": "x"}, order_cls)
        assert_that(str(exc_info.value)).contains("conform to <Order>").contains("int_parsing")
        assert_that(exc_info.value.actual).is_equal_to({"id": "notint", "total": "x"})
        assert_that(exc_info.value.expected).is_equal_to(order_cls)
        # pydantic's ValidationError text is already in the message, so it must not also head the traceback
        assert_that(exc_info.value.__suppress_context__).is_true()

    def test_invalid_item_fails_without_chaining_pydantic(self):
        order_cls = self._order_model()
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms([{"id": "notint", "total": "x"}], order_cls, each=True)
        assert_that(exc_info.value.__suppress_context__).is_true()

    def test_description_is_prepended_on_failure(self):
        order_cls = self._order_model()
        with pytest.raises(AssertionError, match=r"^\[order payload\]"):
            assert_conforms({"id": "notint"}, order_cls, "order payload")

    def test_non_pydantic_type_raises_typeerror(self):
        with pytest.raises(TypeError, match="pydantic v2 model"):
            assert_conforms({}, dict)

    def test_non_type_arg_raises_typeerror(self):
        with pytest.raises(TypeError, match="pydantic v2 model"):
            assert_conforms({}, "not a type")

    def test_soft_collects_failure(self):
        order_cls = self._order_model()
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            assert_conforms({"id": "bad", "total": "x"}, order_cls)


class TestAssertConformsExact:
    @staticmethod
    def _models():
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from datetime import datetime

        from pydantic import BaseModel

        class Customer(BaseModel):
            name: str

        class Item(BaseModel):
            sku: str

        class Order(BaseModel):
            id: int
            total: float
            created: datetime
            customer: Customer
            items: list[Item]

        return Order

    @staticmethod
    def _clean():
        return {
            "id": 1,
            "total": 5,
            "created": "2020-01-01T00:00:00",
            "customer": {"name": "Ann"},
            "items": [{"sku": "A"}, {"sku": "B"}],
        }

    def test_exact_clean_passes_without_coercion_noise(self):
        order_cls = self._models()
        assert_that(conforms_val := assert_conforms(self._clean(), order_cls, exact=True).value).is_not_none()
        assert_that(conforms_val.id).is_equal_to(1)

    def test_default_lenient_ignores_extra_fields(self):
        order_cls = self._models()
        grew = {**self._clean(), "promo_code": "X"}
        assert_that(assert_conforms(grew, order_cls).value).is_instance_of(order_cls)

    def test_exact_top_level_drift_fails(self):
        order_cls = self._models()
        grew = {**self._clean(), "promo_code": "X"}
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms(grew, order_cls, exact=True)
        assert_that(str(exc_info.value)).contains("conform exactly").contains("promo_code")
        assert_that(exc_info.value.actual).is_equal_to(grew)
        assert_that(exc_info.value.expected).is_equal_to(order_cls)

    def test_exact_nested_and_list_drift_paths(self):
        order_cls = self._models()
        payload = self._clean()
        payload["customer"] = {"name": "Ann", "vip": True}
        payload["items"] = [{"sku": "A"}, {"sku": "B", "gift_wrap": True}]
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms(payload, order_cls, exact=True)
        message = str(exc_info.value)
        assert_that(message).contains("customer.vip").contains("items[1].gift_wrap")

    def test_exact_alias_not_flagged(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, Field

        class Aliased(BaseModel):
            user_id: int = Field(alias="userId")

        assert_that(assert_conforms({"userId": 1}, Aliased, exact=True).value.user_id).is_equal_to(1)

    def test_exact_respects_extra_allow_config(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, ConfigDict

        class Loose(BaseModel):
            model_config = ConfigDict(extra="allow")
            id: int

        assert_that(assert_conforms({"id": 1, "anything": 2}, Loose, exact=True).value.id).is_equal_to(1)

    def test_exact_soft_collects_drift(self):
        order_cls = self._models()
        grew = {**self._clean(), "promo_code": "X"}
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            assert_conforms(grew, order_cls, exact=True)

    def test_validation_error_precedes_drift(self):
        order_cls = self._models()
        broken = {**self._clean(), "id": "notint", "surprise": 1}
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms(broken, order_cls, exact=True)
        assert_that(str(exc_info.value)).contains("did not").does_not_contain("conform exactly")

    def test_each_validates_every_item_of_a_list_endpoint(self):
        order_cls = self._models()
        result = assert_conforms([self._clean(), self._clean()], order_cls, each=True)
        assert_that(result.val).is_length(2)
        assert_that(result.val[0]).is_instance_of(order_cls)

    def test_each_reports_the_failing_item_index(self):
        order_cls = self._models()
        payloads = [self._clean(), {**self._clean(), "id": "notint"}]
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms(payloads, order_cls, each=True)
        assert_that(str(exc_info.value)).contains("item [1]").contains("to conform")
        assert_that(exc_info.value.actual).is_equal_to(payloads)
        assert_that(exc_info.value.expected).is_equal_to(order_cls)

    def test_each_exact_drift_carries_the_element_index(self):
        order_cls = self._models()
        payloads = [self._clean(), {**self._clean(), "promo": "X"}]
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms(payloads, order_cls, each=True, exact=True)
        assert_that(str(exc_info.value)).contains("[1].promo")
        assert_that(exc_info.value.actual).is_equal_to(payloads)
        assert_that(exc_info.value.expected).is_equal_to(order_cls)

    def test_each_exact_clean_list_passes(self):
        order_cls = self._models()
        result = assert_conforms([self._clean(), self._clean()], order_cls, each=True, exact=True)
        assert_that(result.val).is_length(2)

    def test_each_accepts_a_tuple_and_an_empty_payload(self):
        order_cls = self._models()
        assert_that(assert_conforms((), order_cls, each=True).val).is_equal_to([])

    def test_each_requires_a_list_or_tuple_payload(self):
        order_cls = self._models()
        with pytest.raises(TypeError) as exc_info:
            assert_conforms(self._clean(), order_cls, each=True)
        assert_that(str(exc_info.value)).contains("list or tuple")

    def test_each_soft_collects_the_item_failure(self):
        order_cls = self._models()
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_conforms([{**self._clean(), "id": "x"}], order_cls, each=True)
        assert_that(str(exc_info.value)).contains("item [0]")


def _drift(payload, model):
    """What `assert_conforms(..., exact=True)` reports: the payload walked beside the instance it validated into."""
    return contract_drift(payload, model.model_validate(payload))


class TestContractDrift:
    """Unit coverage of the drift walker's branches."""

    @staticmethod
    def _submodels():
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            inner: Inner = Field(alias="innerAlias")
            pair: tuple[Inner, ...]
            either: int | str
            note: str

        return Inner, Outer

    def test_a_payload_of_another_shape_is_refused_only_where_a_key_could_hide(self, monkeypatch):
        inner, _ = self._submodels()
        with pytest.raises(UncheckableDriftError, match="holds a list where a model was built"):
            contract_drift([{"x": 1}], inner(x=1))
        itself: list[object] = []
        itself.append(itself)
        for keyless in (42, None, [1, 2], itself, "not json", b"[1]", inner(x=1)):
            assert_that(contract_drift(keyless, inner(x=1))).described_as(repr(keyless)).is_empty()

        # how deep the decoder goes before RecursionError depends on the platform's stack
        def too_deep(text):
            raise RecursionError

        monkeypatch.setattr(_contract, "json", types.SimpleNamespace(loads=too_deep))
        with pytest.raises(UncheckableDriftError, match="holds a str where a model was built"):
            contract_drift("[[[", inner(x=1))

    def test_alias_resolved_tuple_and_union_branches(self):
        _, outer = self._submodels()
        payload = {
            "innerAlias": {"x": 1, "deep": 2},
            "pair": [{"x": 1}, {"x": 2, "oops": 9}],
            "either": "ok",
            "note": "n",
        }
        assert_that(sorted(_drift(payload, outer))).is_equal_to(["inner.deep", "pair[1].oops"])

    def test_null_submodel_value_is_skipped(self):
        inner_model, _ = self._submodels()
        from pydantic import BaseModel

        class Holder(BaseModel):
            inner: inner_model | None

        assert_that(_drift({"inner": None}, Holder)).is_empty()

    def test_validation_alias_str_not_flagged(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(validation_alias="userId")

        assert_that(_drift({"userId": 1}, Model)).is_empty()

    def test_alias_choices_not_flagged_but_genuine_drift_caught(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import AliasChoices, BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(validation_alias=AliasChoices("uid", "userId"))

        assert_that(_drift({"uid": 1}, Model)).is_empty()
        assert_that(_drift({"userId": 1}, Model)).is_empty()
        assert_that(_drift({"uid": 1, "surprise": 9}, Model)).is_equal_to(["surprise"])

    def test_alias_path_top_level_key_not_flagged(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import AliasPath, BaseModel, Field

        class Model(BaseModel):
            city: str = Field(validation_alias=AliasPath("address", "city"))

        assert_that(_drift({"address": {"city": "NYC"}}, Model)).is_empty()

    def test_submodel_resolved_via_validation_alias(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            inner: Inner = Field(validation_alias="innerAlias")

        assert_that(_drift({"innerAlias": {"x": 1, "extra": 2}}, Outer)).is_equal_to(["inner.extra"])

    def test_submodel_value_resolution_alias_loop_branches(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import AliasChoices, BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            plain: Inner | None = None
            aliased: Inner = Field(validation_alias=AliasChoices("first", "second"))

        assert_that(_drift({"second": {"x": 1, "deep": 9}}, Outer)).is_equal_to(["aliased.deep"])


class TestShape:
    def test_scalar_categories(self):
        assert_that(shape(None)).is_equal_to("null")
        assert_that(shape(True)).is_equal_to("bool")
        assert_that(shape(7)).is_equal_to("number")
        assert_that(shape(7.5)).is_equal_to("number")
        assert_that(shape("x")).is_equal_to("str")
        assert_that(shape(b"raw")).is_equal_to("bytes")

    def test_dict_and_empty_list(self):
        assert_that(shape({"id": 1, "name": "a"})).is_equal_to({"id": "number", "name": "str"})
        assert_that(shape([])).is_equal_to([])

    def test_list_merges_element_shapes(self):
        assert_that(shape([{"a": 1}, {"a": 2}])).is_equal_to([{"a": "number"}])
        assert_that(shape([{"a": 1}, {"b": 2}])).is_equal_to([{"a": "number", "b": "number"}])
        assert_that(shape([None, 1])).is_equal_to(["number"])
        assert_that(shape([1, None])).is_equal_to(["number"])
        assert_that(shape([1, "x"])).is_equal_to(["mixed"])
        assert_that(shape([[], [1]])).is_equal_to([["number"]])
        assert_that(shape([[1], []])).is_equal_to([["number"]])
        assert_that(shape([[1], ["x"]])).is_equal_to([["mixed"]])

    def test_nested_dict_elements_are_merged_key_by_key(self):
        # `[[1], ["x"]]` answers "mixed" either way; dict elements merge into a union rather than collapsing
        assert_that(shape([[{"a": 1}], [{"b": 2}]])).is_equal_to([[{"a": "number", "b": "number"}]])

    def test_a_self_referential_list_is_marked_not_followed(self):
        # the seen-set has to reach list elements too, or this recurses until the interpreter gives up
        cyclic = [1]
        cyclic.append(cyclic)
        assert_that(shape(cyclic)).is_equal_to(["mixed"])

    def test_a_self_referential_dict_keeps_the_marker(self):
        # a list merges the marker into "mixed", so a dict is the only place it reaches the stored shape
        cyclic = {"a": 1}
        cyclic["self"] = cyclic
        assert_that(shape(cyclic)).is_equal_to({"a": "number", "self": "<circular ref>"})


class TestShapeDiff:
    def test_no_drift_and_null_wildcard(self):
        assert_that(shape_diff({"a": "number"}, {"a": "number"})).is_empty()
        assert_that(shape_diff("null", "str")).is_empty()
        assert_that(shape_diff("str", "null")).is_empty()

    def test_added_removed_nested(self):
        old = {"id": "number", "user": {"name": "str"}}
        new = {"id": "number", "user": {"name": "str", "vip": "bool"}, "extra": "str"}
        assert_that(sorted(shape_diff(old, new))).is_equal_to([("added", "extra", ""), ("added", "user.vip", "")])
        assert_that(shape_diff(new, old)).contains(("removed", "extra", ""), ("removed", "user.vip", ""))

    def test_list_elementwise_and_empty(self):
        assert_that(shape_diff([{"a": "number"}], [{"a": "number", "b": "str"}])).is_equal_to([("added", "[*].b", "")])
        assert_that(shape_diff([], ["str"])).is_empty()
        assert_that(shape_diff(["str"], [])).is_empty()

    def test_retyped_names_objects_and_lists(self):
        assert_that(shape_diff("number", "str")).is_equal_to([("retyped", "", "number -> str")])
        assert_that(shape_diff({"a": "number"}, "str")).is_equal_to([("retyped", "", "object -> str")])
        assert_that(shape_diff("str", ["number"])).is_equal_to([("retyped", "", "str -> list")])


class TestContractFailuresCarryPaths:
    """A validation failure exposes the same structured channel every other comparison does."""

    @staticmethod
    def _models():
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Address(BaseModel):
            city: str
            zip: str

        class User(BaseModel):
            id: int
            address: Address

        return User

    def test_paths_and_inputs_reach_the_diff(self):
        user_cls = self._models()
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms({"id": "seven", "address": {"city": "Paris"}}, user_cls)
        diff = exc_info.value.diff
        assert_that(diff.kind).is_equal_to("match")
        assert_that([entry.path for entry in diff.entries]).contains("id", "address.zip")
        assert_that(next(entry for entry in diff.entries if entry.path == "id").actual).is_equal_to("seven")

    def test_each_names_the_element_that_failed(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Item(BaseModel):
            sku: str
            qty: int

        with pytest.raises(AssertionError) as exc_info:
            assert_conforms([{"sku": "A", "qty": 2}, {"sku": "B", "qty": "two"}], Item, each=True)
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["[1].qty"])


class TestAliasResolution:
    """Every top-level key a field can arrive under.  `Field(alias=...)` fills `validation_alias` too,
    so a model built that way exercises both collectors at once and cannot tell them apart: breaking
    either one still leaves the other supplying the key.  These separate them, and cover the two alias
    objects nothing reached before."""

    def test_a_serialization_only_alias_is_not_declared(self):
        # `serialization_alias` renames a field on the way out, and pydantic will not accept it as input
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(serialization_alias="userId")

        assert_that(_declared_keys(Model)).is_equal_to({"user_id"})

    def test_a_validation_only_alias_is_declared(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(validation_alias="incoming_id")

        assert_that(_declared_keys(Model)).contains("incoming_id")

    def test_every_choice_of_an_alias_choices_is_declared(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import AliasChoices, BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(validation_alias=AliasChoices("userId", "user-id", "uid"))

        assert_that(_declared_keys(Model)).contains("userId", "user-id", "uid")

    def test_an_alias_path_declares_the_key_it_consumes(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import AliasPath, BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(validation_alias=AliasPath("meta", "id"))

        assert_that(_declared_keys(Model)).contains("meta")
        assert_that(_drift({"meta": {"id": 1}}, Model)).is_empty()


class TestSubmodelAnnotations:
    def test_an_optional_submodel_is_still_walked(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Inner(BaseModel):
            a: int

        class Outer(BaseModel):
            inner: Inner | None = None

        assert_that(_drift({"inner": {"a": 1, "extra": 2}}, Outer)).is_equal_to(["inner.extra"])


class TestDriftFollowsWhatPydanticBuilt:
    """The payload is walked beside the instance it validated into, so each nested model is checked where pydantic put
    one: the member of a union it chose, the element types of a tuple, the values of a dict, and the full path of an
    `AliasPath`.  Read off the annotation, a union or a dict of models was never entered and extras inside it passed,
    and an `AliasPath` was followed one segment only."""

    @staticmethod
    def _cases():
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import AliasPath, BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator
        from typing_extensions import TypedDict

        class A(BaseModel):
            model_config = ConfigDict(frozen=True)
            kind: typing.Literal["a"] = "a"
            x: int

        class B(BaseModel):
            kind: typing.Literal["b"] = "b"
            y: int

        class Rows(RootModel[list[A]]):
            pass

        def holding(annotation, **extra):
            return type("Holder", (BaseModel,), {"__annotations__": {"f": annotation}, **extra})

        class Wrapped(BaseModel):
            sub: A = Field(validation_alias=AliasPath("wrap", "inner"))

        class Indexed(BaseModel):
            first: A = Field(validation_alias=AliasPath("items", 0))
            last: A = Field(validation_alias=AliasPath("items", -1))

        class EmptyAlias(BaseModel):
            sub: A = Field(validation_alias="")

        class IntKeyed(BaseModel):
            sub: A = Field(validation_alias=AliasPath("wrap", 0))

        class ByName(BaseModel):
            model_config = ConfigDict(populate_by_name=True)
            sub: A = Field(alias="theSub")

        class Extras(BaseModel):
            model_config = ConfigDict(extra="allow")
            __pydantic_extra__: dict[str, A]

        class Stamped(BaseModel):
            model_config = ConfigDict(extra="allow")
            x: int

            @model_validator(mode="after")
            def stamped(self):
                self.stamp = 1
                return self

        class AliasOnly(BaseModel):
            model_config = ConfigDict(populate_by_name=True, validate_by_alias=True, validate_by_name=False)
            sub: A = Field(default_factory=lambda: A(x=0), alias="theSub")

        class Shape(TypedDict):
            a: A
            b: int

        class Unreached(BaseModel):
            past: A | None = Field(None, validation_alias=AliasPath("items", 5))
            keyed: A | None = Field(None, validation_alias=AliasPath("items", "k"))

        class Frozen(BaseModel):
            f: dict[str, A]

            @field_validator("f")
            @classmethod
            def frozen(cls, value):
                return types.MappingProxyType(value)

        extra = {"x": 1, "extra": 2}
        discriminated = typing.Annotated[A | B, Field(discriminator="kind")]
        cases = {
            "union": (holding(A | B), {"f": extra}, ["f.extra"]),
            "union, the other member": (holding(A | B), {"f": {"y": 1, "extra": 2}}, ["f.extra"]),
            "dict of models": (holding(dict[str, A]), {"f": {"k": extra}}, ["f.k.extra"]),
            "dict with a coerced key": (holding(dict[int, A]), {"f": {"1": extra}}, ["f.1.extra"]),
            "list of a union": (holding(list[A | B]), {"f": [extra]}, ["f[0].extra"]),
            "tuple, clean": (holding(tuple[A, B]), {"f": [{"x": 1}, {"y": 2}]}, []),
            "tuple, extra in its second type": (
                holding(tuple[A, B]),
                {"f": [{"x": 1}, {"y": 2, "extra": 3}]},
                ["f[1].extra"],
            ),
            "discriminated union": (holding(discriminated), {"f": {"kind": "b", "y": 1, "extra": 2}}, ["f.extra"]),
            "dict of lists": (holding(dict[str, list[A]]), {"f": {"k": [extra]}}, ["f.k[0].extra"]),
            "root model": (Rows, [extra], ["[0].extra"]),
            "root model as a field": (holding(Rows), {"f": [extra]}, ["f[0].extra"]),
            "alias path, clean": (Wrapped, {"wrap": {"inner": {"x": 1}}}, []),
            "alias path, extra": (Wrapped, {"wrap": {"inner": extra}}, ["sub.extra"]),
            "alias path by index": (Indexed, {"items": [{"x": 1}, extra]}, ["last.extra"]),
            "a name allowed beside the alias": (ByName, {"sub": extra}, ["sub.extra"]),
            "list of lists": (holding(list[list[A]]), {"f": [[extra]]}, ["f[0][0].extra"]),
            "an empty alias": (EmptyAlias, {"": extra}, ["sub.extra"]),
            "alias path by dict key": (IntKeyed, {"wrap": {0: extra}}, ["sub.extra"]),
            "a typed dict it reorders": (holding(Shape), {"f": {"b": 1, "a": extra}}, ["f.a.extra"]),
            "a deque for a list": (holding(list[A]), {"f": collections.deque([extra])}, ["f[0].extra"]),
            "a dict's values for a list": (holding(list[A]), {"f": {"k": extra}.values()}, ["f[0].extra"]),
            "a mapping proxy for a model": (holding(A), {"f": types.MappingProxyType(extra)}, ["f.extra"]),
            "a mapping proxy for a dict": (
                holding(dict[str, A]),
                {"f": types.MappingProxyType({"k": extra})},
                ["f.k.extra"],
            ),
            "a mapping proxy as the payload": (holding(A), types.MappingProxyType({"f": extra}), ["f.extra"]),
            "alias path by index into a deque": (
                Indexed,
                {"items": collections.deque([{"x": 1}, extra])},
                ["last.extra"],
            ),
            "alias path through a bare getitem": (Indexed, {"items": _Indexed([{"x": 1}, extra])}, ["last.extra"]),
            "alias path by key through a bare getitem": (Wrapped, {"wrap": _Indexed({"inner": extra})}, ["sub.extra"]),
            "a name the config refuses over populate_by_name": (AliasOnly, {"sub": extra}, []),
            "a sequence kept as a deque": (
                holding(collections.abc.Sequence[A]),
                {"f": collections.deque([extra])},
                ["f[0].extra"],
            ),
            "a dict a validator froze": (Frozen, {"f": {"k": extra}}, ["f.k.extra"]),
            "a declaration naming two lists": (
                holding(list[dict[str, A]] | list[int]),
                {"f": [{"k": extra}]},
                ["f[0].k.extra"],
            ),
            "alias paths reaching nothing": (Unreached, {"items": [extra]}, []),
            "alias paths into text": (Unreached, {"items": "text"}, []),
            "alias path through a bytes subclass": (Wrapped, {"wrap": _ByteItems(b"x")}, ["sub.extra"]),
            "a typed extra": (Extras, {"added": extra}, ["added.extra"]),
            "an extra a validator set": (Stamped, {"x": 1}, []),
        }
        try:
            EmptyAlias.model_validate({"": {"x": 1}})
        except ValueError:
            del cases["an empty alias"]  # an older pydantic takes an empty alias for no alias
        return cases

    def test_each_nested_model_is_checked_where_pydantic_put_it(self):
        found = {label: sorted(_drift(payload, model)) for label, (model, payload, _) in self._cases().items()}
        assert_that(found).is_equal_to({label: expected for label, (_, _, expected) in self._cases().items()})

    def test_a_name_the_config_does_not_read_is_not_followed(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            sub: Inner = Field(alias="theSub")

        # pydantic read `theSub` and ignored `sub`, so what `sub` holds is not the model that was built
        assert_that(_drift({"theSub": {"x": 1}, "sub": {"x": 1, "extra": 2}}, Outer)).is_empty()

    def test_a_config_reading_names_only_is_followed_by_name(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import ConfigDict as _Config

        if "validate_by_name" not in _Config.__annotations__:
            pytest.skip(reason="validate_by_name arrived in pydantic 2.11")
        from pydantic import BaseModel, ConfigDict, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            model_config = ConfigDict(validate_by_alias=False, validate_by_name=True)
            sub: Inner | None = Field(alias="theSub")

        # pydantic read the `None` under the name, so what the ignored alias holds is not the model that was built
        assert_that(_drift({"sub": None, "theSub": {"x": 1, "extra": 2}}, Outer)).is_empty()
        assert_that(_drift({"sub": {"x": 1, "extra": 2}}, Outer)).is_equal_to(["sub.extra"])

    def test_the_assertion_reports_what_the_walk_finds(self):
        model, payload, _ = self._cases()["union"]
        with pytest.raises(AssertionError) as caught:
            assert_conforms(payload, model, exact=True)
        assert_that(str(caught.value)).contains("['f.extra']")
        model, payload, _ = self._cases()["alias path, clean"]
        assert_that(assert_conforms(payload, model, exact=True).value.sub.x).is_equal_to(1)

    def test_a_model_is_read_once_and_the_reading_kept(self, monkeypatch):
        model, payload, expected = self._cases()["alias path, extra"]
        read = []
        original = _contract._field_sources
        monkeypatch.setattr(_contract, "_READS", {})
        monkeypatch.setattr(_contract, "_field_sources", lambda *args: read.append(args[0]) or original(*args))
        assert_that(_drift(payload, model)).is_equal_to(expected)
        first = list(read)
        assert_that(_drift(payload, model)).is_equal_to(expected)
        assert_that(read).is_equal_to(first).contains("sub")
        assert_that(_contract._READS).contains_key(model)

    def test_a_rebuilt_model_is_read_again(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import ConfigDict as _Config

        if "validate_by_name" not in _Config.__annotations__:
            pytest.skip(reason="validate_by_name arrived in pydantic 2.11")
        from pydantic import BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            sub: Inner | None = Field(default=None, alias="theSub")

        payload = {"sub": {"x": 1, "extra": 2}}
        assert_that(_drift(payload, Outer)).is_empty()
        Outer.model_config["validate_by_alias"] = False
        Outer.model_config["validate_by_name"] = True
        Outer.model_rebuild(force=True)
        assert_that(_drift(payload, Outer)).is_equal_to(["sub.extra"])

    def test_a_payload_holding_itself_is_walked_once(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Loose(BaseModel):
            f: typing.Any

        looped: dict = {}
        looped["f"] = looped
        assert_that(assert_conforms(looped, Loose, exact=True).value.f).is_same_as(looped)

    def test_a_model_a_validator_made_hold_itself_is_walked_once(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, model_validator

        class Selfish(BaseModel):
            f: typing.Optional["Selfish"] | typing.Any

            @model_validator(mode="after")
            def holding_itself(self):
                self.f = self
                return self

        looped: dict = {}
        looped["f"] = looped
        conformed = assert_conforms(looped, Selfish, exact=True).value
        assert_that(conformed.f).is_same_as(conformed)

    def test_a_full_record_of_models_still_answers_a_new_one(self, monkeypatch):
        model, payload, expected = self._cases()["union"]
        full = dict.fromkeys(range(256))
        monkeypatch.setattr(_contract, "_READS", full)
        assert_that(_drift(payload, model)).is_equal_to(expected)
        assert_that(full).is_length(256)

    def test_each_item_of_a_root_model_is_named_by_its_own_index(self):
        model, _, _ = self._cases()["root model"]
        with pytest.raises(AssertionError) as caught:
            assert_conforms([[{"x": 1}], [{"x": 1, "extra": 2}]], model, each=True, exact=True)
        assert_that(str(caught.value)).contains("['[1][0].extra']")

    def test_each_item_is_walked_beside_its_own_instance(self):
        model, _, _ = self._cases()["union"]
        with pytest.raises(AssertionError) as caught:
            assert_conforms([{"f": {"x": 1}}, {"f": {"y": 1, "extra": 2}}], model, each=True, exact=True)
        assert_that(str(caught.value)).contains("['[1].f.extra']")


class _Indexed:
    """Indexed through `__getitem__` alone, as an `AliasPath` step may read it."""

    def __init__(self, items):
        self.items = items

    def __getitem__(self, index):
        return self.items[index]


class _ByteItems(bytes):
    """Bytes whose own `__getitem__` answers any step, which pydantic's alias reading asks."""

    def __getitem__(self, key):
        return {"x": 1, "extra": 2}


_T = typing.TypeVar("_T")


class _Rows:
    """Iterable, and neither a collection nor an iterator."""

    def __iter__(self):
        yield {"x": 1, "extra": 2}


class TestExactnessRefusesWhatItCannotPair:
    """Where no reading pairs a part of the payload with the model built from it, `exact=True` fails and says where,
    rather than pass it unread or read it against the wrong model."""

    @staticmethod
    def _models():
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, ConfigDict, Json, RootModel, field_validator, model_validator

        class A(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: int

        class B(BaseModel):
            model_config = ConfigDict(frozen=True)
            y: int

        def holding(annotation):
            return type("Holder", (BaseModel,), {"__annotations__": {"f": annotation}})

        class Filtered(BaseModel):
            f: list[A]

            @field_validator("f", mode="before")
            @classmethod
            def without_nulls(cls, value):
                return [item for item in value if item is not None]

        class Wrapped(BaseModel):
            f: list[A]

            @field_validator("f", mode="before")
            @classmethod
            def listed(cls, value):
                return value if isinstance(value, list) else [value]

        class Money(BaseModel):
            amount: int
            currency: str

            @model_validator(mode="before")
            @classmethod
            def spelled(cls, value):
                if isinstance(value, str):
                    amount, currency = value.split()
                    return {"amount": amount, "currency": currency}
                if isinstance(value, list):
                    return dict(zip(("amount", "currency"), value, strict=True))
                return value

        class WrappedSet(BaseModel):
            f: set[A]

            @field_validator("f", mode="before")
            @classmethod
            def listed(cls, value):
                return value if isinstance(value, list) else [value]

        class Wide(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: int
            z: int

        class FilteredUnion(BaseModel):
            f: list[Wide | A]

            @field_validator("f", mode="before")
            @classmethod
            def without_nulls(cls, value):
                return [item for item in value if item is not None]

        class Entry(BaseModel):
            model_config = ConfigDict(frozen=True)
            id: int

            def __eq__(self, other):
                return isinstance(other, Entry) and self.id == other.id

            def __hash__(self):
                return hash(self.id)

        class Narrow(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: int

        class Broad(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: int
            extra: int = 0

        class First(Entry):
            tag: typing.Literal[1]
            child: Narrow

        class Last(Entry):
            tag: int
            child: Broad

        class Envelope(BaseModel, typing.Generic[_T]):
            model_config = ConfigDict(frozen=True)
            event: _T

        class Batch(BaseModel):
            f: set[Envelope[First] | Envelope[Last]]

        class Entries(BaseModel):
            f: set[First | Last]

        class Dated(BaseModel):
            model_config = ConfigDict(frozen=True, strict=True)
            d: datetime.date

        class Expanded(BaseModel):
            f: list[A]

            @field_validator("f", mode="before")
            @classmethod
            def expanded(cls, value):
                return value if isinstance(value, list) else [value, *value.get("more", [])]

        class Renamed(BaseModel):
            f: list[A]

            @field_validator("f", mode="before")
            @classmethod
            def renamed(cls, value):
                return [{"x": item["X"]} for item in value if item]

        class Priced(BaseModel):
            f: list[Money]

            @field_validator("f", mode="before")
            @classmethod
            def without_blanks(cls, value):
                return [item for item in value if item]

        class Paired(BaseModel):
            f: dict[str, A]

            @field_validator("f", mode="before")
            @classmethod
            def from_pairs(cls, value):
                return dict(value) if isinstance(value, list) else value

        return {
            "A": A,
            "B": B,
            "holding": holding,
            "Filtered": Filtered,
            "Wrapped": Wrapped,
            "Json": Json,
            "Money": Money,
            "Priced": Priced,
            "Paired": Paired,
            "RootModel": RootModel,
            "Renamed": Renamed,
            "WrappedSet": WrappedSet,
            "FilteredUnion": FilteredUnion,
            "Dated": Dated,
            "Entries": Entries,
            "Batch": Batch,
            "Expanded": Expanded,
        }

    def _refusal(self, payload, model, **options):
        with pytest.raises(AssertionError) as caught:
            assert_conforms(payload, model, exact=True, **options)
        return str(caught.value).split(", but ", 1)[1]

    def test_each_part_it_cannot_pair_is_named_with_the_reason(self):
        models = self._models()
        a, b, holding, json_of = models["A"], models["B"], models["holding"], models["Json"]
        found = {
            "a set mixing model classes": self._refusal({"f": [{"x": 1}, {"y": 1}]}, holding(set[a | b])),
            "an item its class refuses alone": self._refusal({"f": [None, {"X": 1}]}, models["Renamed"]),
            "an object expanded into several": self._refusal(
                {"f": {"x": 1, "more": [{"x": 2, "extra": 3}]}}, models["Expanded"]
            ),
            "a set merging generic specializations": self._refusal(
                {
                    "f": [
                        {"event": {"id": 1, "tag": 2, "child": {"x": 1}}},
                        {"event": {"id": 1, "tag": 1, "child": {"x": 1, "extra": 2}}},
                    ]
                },
                models["Batch"],
            ),
            "a set merging classes through its own equality": self._refusal(
                {"f": [{"id": 1, "tag": 2, "child": {"x": 1}}, {"id": 1, "tag": 1, "child": {"x": 1, "extra": 2}}]},
                models["Entries"],
            ),
            "a filtered list of mixed classes": self._refusal(
                {"f": [None, {"x": 1}, {"x": 2, "z": 3}]}, models["FilteredUnion"]
            ),
            "merged keys of models": self._refusal({"f": {"01": {"x": 1}, "1": {"x": 2}}}, holding(dict[int, a])),
            "merged model keys with model values": self._refusal(
                {"f": {'{"x": 1, "extra": 2}': {"x": 1}, '{"x": 1}': {"x": 2}}}, holding(dict[json_of[a], a])
            ),
            "merged keys of lists": self._refusal(
                {"f": {"01": [{"x": 1}], "1": [{"x": 2, "extra": 3}]}}, holding(dict[int, list[a]])
            ),
            "a mapping from a list": self._refusal({"f": [["k", {"x": 1}]]}, models["Paired"]),
            "model keys merged": self._refusal({"f": {'{"x": 1}': 1, '{"x":1}': 2}}, holding(dict[json_of[a], int])),
            "a generator read up": self._refusal({"f": (item for item in [{"x": 1}])}, holding(list[a])),
            "an iterable that is no collection": self._refusal({"f": _Rows()}, holding(list[a])),
            "a lazy iterable": self._refusal({"f": [{"x": 1, "extra": 2}]}, holding(collections.abc.Iterable[a])),
            "merged keys of lazy iterables": self._refusal(
                {"f": {"01": [{"x": 1}], "1": [{"x": 2, "extra": 3}]}},
                holding(dict[int, collections.abc.Iterable[a]]),
            ),
        }
        cannot = "<f> cannot be checked: "
        merged = f"{cannot}validation changed its size, 2 keys became 1"
        unordered = f"{cannot}a set keeps no order to pair its items with the models they became"
        assert_that(found).is_equal_to(
            {
                "a set mixing model classes": unordered,
                "an item its class refuses alone": f"{cannot}validation changed its length, 2 items became 1",
                "an object expanded into several": f"{cannot}the payload holds a dict where a sequence was built",
                "a set merging classes through its own equality": unordered,
                "a set merging generic specializations": unordered,
                "a filtered list of mixed classes": f"{cannot}validation changed its length, 3 items became 2",
                "merged keys of models": merged,
                "merged model keys with model values": merged,
                "merged keys of lists": merged,
                "a mapping from a list": f"{cannot}the payload holds a list where a mapping was built",
                "model keys merged": merged,
                "a generator read up": f"{cannot}the payload holds a generator where a sequence was built",
                "an iterable that is no collection": f"{cannot}the payload holds a _Rows where a sequence was built",
                "a lazy iterable": f"{cannot}validation is lazy here and builds the models only as the value is read",
                "merged keys of lazy iterables": merged,
            }
        )

    def test_an_item_validated_again_runs_its_validators_once_more(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, ConfigDict, model_validator

        runs = []

        class Tag(BaseModel):
            model_config = ConfigDict(frozen=True)
            name: str

            @model_validator(mode="before")
            @classmethod
            def counted(cls, value):
                runs.append(value["name"])
                return value

        class Tagged(BaseModel):
            tags: set[Tag]

        assert_conforms({"tags": [{"name": "a"}, {"name": "b"}]}, Tagged, exact=True)
        assert_that(runs).is_equal_to(["a", "b", "a", "b"])

    def test_a_filtered_list_is_checked_as_the_payload_sent_it(self):
        """An item the validator dropped is checked too: the contract is the payload's, not what was kept."""
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, field_validator

        class Plain(BaseModel):
            x: int

        class Live(BaseModel):
            items: list[Plain]

            @field_validator("items", mode="before")
            @classmethod
            def without_deleted(cls, value):
                return [item for item in value if not item.get("deleted")]

        found = self._refusal({"items": [{"x": 1, "deleted": True}, {"x": 2}]}, Live)
        assert_that(found).is_equal_to(
            "it carries 1 undeclared field(s) the model does not declare: ['items[0].deleted']"
        )

    def test_a_container_validation_emptied_is_checked_by_the_classes_its_field_declares(self):
        """With no item left to tell what the dropped ones became, the raw items are validated again as the field's
        declared type and what that builds is read; items pydantic will not build that type from, and anything below
        a choice the skipped validators could have steered, are left unread."""
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, Json, RootModel, field_validator
        from pydantic_core import core_schema
        from typing_extensions import TypeAliasType

        class A(BaseModel):
            x: int

        class B(BaseModel):
            y: int

        class Loose(BaseModel):
            x: int
            z: int = 0

        class Stringly(BaseModel):
            x: str
            y: int

        class FrozenA(BaseModel, frozen=True):
            x: int

        class FrozenB(BaseModel, frozen=True):
            y: int

        def emptying(annotation, mode="before"):
            class Emptied(BaseModel):
                f: annotation

                @field_validator("f", mode=mode)
                @classmethod
                def emptied(cls, value):
                    return [] if mode == "before" else type(value)()

            return Emptied

        def inner_emptied(annotation):
            class InnerEmptied(BaseModel):
                f: annotation

                @field_validator("f", mode="before")
                @classmethod
                def empty_inner(cls, value):
                    return [[] for _ in value]

            return InnerEmptied

        class EmptiedValues(BaseModel):
            f: dict[str, typing.Annotated[list[A], BeforeValidator(lambda value: [])]]

        class Wider(A):
            y: int

        class Widened(BaseModel):
            f: list[A]

            @field_validator("f", mode="before")
            @classmethod
            def widened(cls, value):
                return [Wider.model_validate(item) for item in value]

            @field_validator("f", mode="after")
            @classmethod
            def empty(cls, value):
                return []

        class Holder(BaseModel):
            x: int
            g: A | B

        class Normalized(BaseModel):
            f: list[A | Stringly]

            @field_validator("f", mode="before")
            @classmethod
            def normalize(cls, value):
                return [dict(item, x=f"{item['x']}!") for item in value]

            @field_validator("f", mode="after")
            @classmethod
            def empty(cls, value):
                return []

        class StrictTuple(BaseModel):
            model_config = ConfigDict(strict=True)
            f: tuple[A, ...]

            @field_validator("f", mode="before")
            @classmethod
            def as_tuple(cls, value):
                return tuple(value)

            @field_validator("f", mode="after")
            @classmethod
            def empty(cls, value):
                return ()

        class ValuesOrList(BaseModel):
            f: dict[str, typing.Annotated[list[A], BeforeValidator(lambda value: [])]] | list[B]

        class OptionalEmptied(BaseModel):
            f: typing.Annotated[list[A], BeforeValidator(lambda value: [])] | None

        class Tags(frozenset):
            @classmethod
            def __get_pydantic_core_schema__(cls, source, handler):
                return core_schema.no_info_after_validator_function(
                    cls, core_schema.frozenset_schema(handler.generate_schema(FrozenA))
                )

        class Nested(BaseModel):
            f: list[list[A]]

            @field_validator("f", mode="before")
            @classmethod
            def empty_inner(cls, value):
                return [[] for _ in value]

        class Rows(RootModel[list[A]]):
            @field_validator("root", mode="before")
            @classmethod
            def emptied(cls, value):
                return []

        extra = {"x": 1, "extra": 2}
        found = {
            "a list": self._refusal({"f": [extra]}, emptying(list[A])),
            "a set": self._refusal({"f": [extra]}, emptying(set[A])),
            "an optional annotated list": self._refusal(
                {"f": [extra]}, emptying(typing.Annotated[list[A], "meta"] | None)
            ),
            "a tuple of any length": self._refusal({"f": [extra]}, emptying(tuple[A, ...])),
            "an object sent alone": self._refusal({"f": extra}, emptying(list[A])),
            "a root model": self._refusal([extra], Rows),
            "a list emptied inside a list": self._refusal({"f": [[extra]]}, Nested),
            "an item beside a None the list does not take": self._refusal({"f": [None, extra]}, emptying(list[A])),
            "a list emptied as a dict value": self._refusal({"f": {"k": [extra]}}, EmptiedValues),
            "a list of JSON text": self._refusal({"f": ['{"x": 1, "extra": 2}']}, emptying(list[Json[A]])),
            "an optional annotated list of lists": self._refusal(
                {"f": [[extra]]}, inner_emptied(typing.Annotated[list[list[A]], "meta"] | None)
            ),
            "a fixed tuple of lists": self._refusal(
                {"f": [[{"x": 1}], [{"y": 1, "extra": 2}]]}, inner_emptied(tuple[list[A], list[B]])
            ),
            "a fixed tuple with a number first": self._refusal(
                {"f": [1, extra]}, emptying(tuple[int, A], mode="after")
            ),
            "a list optional, emptied by its own validator": self._refusal({"f": [extra]}, OptionalEmptied),
            "a set of its own kind": self._refusal({"f": [{"x": 1}, extra]}, emptying(Tags, mode="after")),
            "a fixed tuple emptied after validation": self._refusal(
                {"f": [{"x": 1}, {"x": 2, "z": 3, "extra": 4}]}, emptying(tuple[A, Loose], mode="after")
            ),
            "a None dropped beside it": self._refusal({"f": [None, extra]}, emptying(list[A | None])),
            "a subclass the skipped validator built, against the declared class": self._refusal(
                {"f": [{"x": 1, "y": 2}]}, Widened
            ),
            "a choice inside the model": self._refusal(
                {"f": [{"x": 1, "g": {"y": 1, "extra": 2}, "top": 3}]}, emptying(list[Holder])
            ),
        }
        carries = "it carries 1 undeclared field(s) the model does not declare: "
        assert_that(found).is_equal_to(
            {
                "a list": f"{carries}['f[0].extra']",
                "a set": f"{carries}['f[0].extra']",
                "an optional annotated list": f"{carries}['f[0].extra']",
                "a tuple of any length": f"{carries}['f[0].extra']",
                "an object sent alone": f"{carries}['f.extra']",
                "a root model": f"{carries}['[0].extra']",
                "a list emptied inside a list": f"{carries}['f[0][0].extra']",
                "an item beside a None the list does not take": f"{carries}['f[1].extra']",
                "a list emptied as a dict value": f"{carries}['f.k[0].extra']",
                "a list of JSON text": f"{carries}['f[0].extra']",
                "an optional annotated list of lists": f"{carries}['f[0][0].extra']",
                "a fixed tuple of lists": f"{carries}['f[1][0].extra']",
                "a fixed tuple with a number first": f"{carries}['f[1].extra']",
                "a list optional, emptied by its own validator": f"{carries}['f[0].extra']",
                "a set of its own kind": f"{carries}['f[1].extra']",
                "a fixed tuple emptied after validation": f"{carries}['f[1].extra']",
                "a None dropped beside it": f"{carries}['f[1].extra']",
                "a subclass the skipped validator built, against the declared class": f"{carries}['f[0].y']",
                "a choice inside the model": f"{carries}['f[0].top']",
            }
        )
        clean = [
            (emptying(list[A]), {"f": [{"x": 1}]}),
            (emptying(list[A | dict[str, int]]), {"f": [{"k": 1}]}),
            (emptying(typing.Any), {"f": [extra]}),
            (emptying(list[A | Loose]), {"f": [{"x": 1}]}),
            (emptying(list[A] | tuple[A, ...]), {"f": [{"x": 1}]}),
            (emptying(tuple[A, Loose], mode="after"), {"f": [{"x": 1}, {"x": 2, "z": 3}]}),
            (emptying(list[A] | tuple[B, ...], mode="after"), {"f": [{"y": 1}]}),
            (emptying(tuple[int, A] | list[dict[str, int]], mode="after"), {"f": [0, {"x": 1}]}),
            (emptying(set[FrozenA] | list[B], mode="after"), {"f": [{"y": 1}]}),
            (OptionalEmptied, {"f": [{"x": 1}]}),
            (emptying(Tags, mode="after"), {"f": [{"x": 1}, {"x": 2}]}),
            (emptying(list[A | int]), {"f": [{"x": "bad", "extra": 2}]}),
            (emptying(list[A]), {"f": [{"X": 1}]}),
            (emptying(tuple[A, ...]), {"f": [{"X": 1}]}),
            (emptying(list[A | None]), {"f": [{"X": 1}]}),
            (emptying(list[A | B]), {"f": [{"y": 1, "extra": 2}]}),
            (emptying(list[A] | tuple[A, ...]), {"f": [extra]}),
            (inner_emptied(list[list[A]] | tuple[list[A], ...]), {"f": [[extra]]}),
            (emptying(tuple[int, A] | list[dict[str, int]], mode="after"), {"f": [0, extra]}),
            (emptying(set[FrozenA] | list[B], mode="after"), {"f": [{"y": 1, "extra": 2}]}),
            (emptying(set[FrozenA] | set[FrozenB], mode="after"), {"f": [extra]}),
            (emptying(list[A] | list[B], mode="after"), {"f": [extra]}),
            (Normalized, {"f": [{"x": 1, "y": 2}]}),
            (ValuesOrList, {"f": {"k": [extra]}}),
            (StrictTuple, {"f": [{"x": 1}]}),
            (StrictTuple, {"f": [extra]}),
        ]
        rows = TypeAliasType("Rows", typing.Annotated[list[A], BeforeValidator(lambda value: [])])
        choice = TypeAliasType("Choice", A | Stringly)
        try:
            aliased, chosen = emptying(rows, mode="after"), emptying(list[choice])
        # pydantic before 2.5 builds no schema for a named alias
        except TypeError:
            aliased = chosen = None
        if aliased is not None:
            clean += [(aliased, {"f": [{"x": 1}]}), (aliased, {"f": [extra]}), (chosen, {"f": [extra]})]
        if "union_mode" in inspect.signature(Field).parameters:
            first = typing.Annotated[dict[str, int] | A, Field(union_mode="left_to_right")]
            clean.append((emptying(list[first], mode="after"), {"f": [extra]}))
            if "coerce_numbers_to_str" in ConfigDict.__annotations__:
                as_text = typing.Annotated[dict[str, str] | A, Field(union_mode="left_to_right")]

                class Coerced(BaseModel):
                    model_config = ConfigDict(coerce_numbers_to_str=True)
                    f: list[as_text]

                    @field_validator("f")
                    @classmethod
                    def emptied(cls, value):
                        return []

                clean.append((Coerced, {"f": [extra]}))
        for model, payload in clean:
            assert_conforms(payload, model, exact=True)

    def test_a_recursive_model_emptied_at_every_level_is_checked_at_every_level(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, field_validator

        class Node(BaseModel):
            children: list["Node"] = []

            @field_validator("children", mode="before")
            @classmethod
            def pruned(cls, value):
                return []

        payload = {"children": [{"children": [{"junk": 1}]}]}
        # pydantic 2.0 keeps the self-reference as text in the field's annotation, which no replay can resolve
        if isinstance(typing.get_args(Node.model_fields["children"].annotation)[0], str):
            assert_conforms(payload, Node, exact=True)
        else:
            assert_that(self._refusal(payload, Node)).is_equal_to(
                "it carries 1 undeclared field(s) the model does not declare: ['children[0].children[0].junk']"
            )

    def test_items_dropped_beside_plain_survivors_are_left_unread_or_refused(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, ConfigDict, field_validator

        class A(BaseModel):
            x: int

        class Duck:
            model_fields: typing.ClassVar[dict] = {}

        class Kept(BaseModel):
            f: list[A | dict[str, int]]

            @field_validator("f", mode="before")
            @classmethod
            def without_x(cls, value):
                return [item for item in value if "x" not in item]

        class Ducks(BaseModel):
            model_config = ConfigDict(arbitrary_types_allowed=True)
            f: list[Duck]

            @field_validator("f", mode="before")
            @classmethod
            def emptied(cls, value):
                return []

        class DuckSurvivors(BaseModel):
            model_config = ConfigDict(arbitrary_types_allowed=True)
            f: list[Duck]

            @field_validator("f", mode="before")
            @classmethod
            def ducked(cls, value):
                return [Duck() for item in value if item]

        assert_conforms({"f": [{"x": 1, "extra": "text"}, {"k": 1}]}, Kept, exact=True)
        assert_conforms({"f": [{"a": 1}]}, Ducks, exact=True)
        refused = self._refusal({"f": [{"a": 1}, None]}, DuckSurvivors)
        assert_that(refused).is_equal_to("<f> cannot be checked: validation changed its length, 2 items became 1")

    def test_an_emptied_container_is_answered_with_full_records_and_left_unread_without_pydantic(self, monkeypatch):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, field_validator

        class A(BaseModel):
            x: int

        class Emptied(BaseModel):
            f: list[A]
            g: dict[str, A] = {}

            @field_validator("f", mode="before")
            @classmethod
            def emptied(cls, value):
                return []

        declared, adapters = dict.fromkeys(range(1024)), dict.fromkeys(range(256))
        monkeypatch.setattr(_contract, "_DECLARED", declared)
        monkeypatch.setattr(_contract, "_ADAPTERS", adapters)
        found = self._refusal({"f": [{"x": 1, "extra": 2}], "g": {"k": {"x": 1}}}, Emptied)
        assert_that(found).is_equal_to("it carries 1 undeclared field(s) the model does not declare: ['f[0].extra']")
        assert_that((len(declared), len(adapters))).is_equal_to((1024, 256))

        def refusing(annotation, config=None):
            raise TypeError(annotation)

        stub = types.SimpleNamespace(TypeAdapter=refusing, ValidationError=sys.modules["pydantic"].ValidationError)
        monkeypatch.setitem(sys.modules, "pydantic", stub)
        assert_conforms({"f": [{"x": 1, "extra": 2}]}, Emptied, exact=True)
        monkeypatch.setitem(sys.modules, "pydantic", None)
        assert_conforms({"f": [{"x": 1, "extra": 2}]}, Emptied, exact=True)

    def test_a_replay_that_builds_no_matching_sequence_is_left_unread(self, monkeypatch):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, field_validator

        class A(BaseModel):
            x: int

        class Emptied(BaseModel):
            f: list[A]

            @field_validator("f", mode="before")
            @classmethod
            def emptied(cls, value):
                return []

        monkeypatch.setattr(
            _contract, "_adapter", lambda declared: types.SimpleNamespace(validate_python=lambda items: 42)
        )
        assert_conforms({"f": [{"x": 1, "extra": 2}]}, Emptied, exact=True)

    def test_items_of_one_model_class_are_validated_again_and_json_text_is_read(self):
        """Clean, each shape passes; with an undeclared field, the field is named where the raw item held it."""
        models = self._models()
        a, holding, json_of, dated = models["A"], models["holding"], models["Json"], models["Dated"]
        cases = {
            "a set of models": (holding(set[a]), [{"x": 1}], [{"x": 1}, {"x": 1, "extra": 2}], "f[1].extra"),
            "a strict model read from JSON in a set": (
                holding(set[json_of[dated]]),
                ['{"d": "2026-09-30"}'],
                ['{"d": "2026-09-30", "extra": 2}'],
                "f[0].extra",
            ),
            "a filtered list": (models["Filtered"], [None, {"x": 1}], [None, {"x": 1, "extra": 2}], "f[1].extra"),
            "an object wrapped into a list": (models["Wrapped"], {"x": 1}, {"x": 1, "extra": 2}, "f.extra"),
            "an object wrapped into a set": (models["WrappedSet"], {"x": 1}, {"x": 1, "extra": 2}, "f.extra"),
            "a model read from text": (holding(json_of[a]), '{"x": 1}', '{"x": 1, "extra": 2}', "f.extra"),
            "models read from bytes": (
                holding(json_of[list[a]]),
                b'[{"x": 1}]',
                b'[{"x": 1, "extra": 2}]',
                "f[0].extra",
            ),
            "JSON text in a set": (holding(set[json_of[a]]), ['{"x": 1}'], ['{"x": 1, "extra": 2}'], "f[0].extra"),
            "a model built from a key": (
                holding(dict[json_of[a], int]),
                {'{"x": 1}': 1},
                {'{"x": 1, "extra": 2}': 1},
                "f.extra",
            ),
            "a model read from JSON twice": (
                holding(json_of[models["RootModel"][json_of[a]]]),
                '"{\\"x\\": 1}"',
                '"{\\"x\\": 1, \\"extra\\": 2}"',
                "f.extra",
            ),
        }
        for model, good, _, _ in cases.values():
            assert_conforms({"f": good}, model, exact=True)
        found = {name: self._refusal({"f": bad}, model) for name, (model, _, bad, _) in cases.items()}
        assert_that(found).is_equal_to(
            {
                name: f"it carries 1 undeclared field(s) the model does not declare: ['{where}']"
                for name, (_, _, _, where) in cases.items()
            }
        )

    def test_each_item_names_its_own_refusal(self):
        models = self._models()
        refusal = self._refusal([{"f": []}, {"f": [None, {"X": 1}]}], models["Renamed"], each=True)
        assert_that(refusal).is_equal_to("<[1].f> cannot be checked: validation changed its length, 2 items became 1")

    def test_what_holds_no_model_is_not_refused(self):
        models = self._models()
        a, holding = models["A"], models["holding"]
        merged = assert_conforms({"f": {"01": 1, "1": 2}}, holding(dict[int, a | int]), exact=True)
        assert_that(merged.value.f).is_length(1)
        assert_that(assert_conforms({"f": [1, 1, 2]}, holding(set[a | int]), exact=True).value.f).is_length(2)
        assert_that(assert_conforms({"f": [1, 2]}, holding(list[a | float]), exact=True).value.f).is_equal_to(
            [1.0, 2.0]
        )
        assert_that(assert_conforms({"f": "a,b"}, holding(str), exact=True).value.f).is_equal_to("a,b")

    def test_a_model_built_from_what_holds_no_key_is_not_refused(self):
        models = self._models()
        holding = models["holding"]
        for spelled in ("10 USD", [10, "USD"]):
            conformed = assert_conforms({"f": spelled}, holding(models["Money"]), exact=True)
            assert_that(conformed.value.f.amount).is_equal_to(10)
        filtered = assert_conforms({"f": ["1 A", "", "2 B"]}, models["Priced"], exact=True)
        assert_that(filtered.value.f).is_length(2)

    def test_a_model_given_instead_of_its_data_has_nothing_to_refuse(self):
        models = self._models()
        a = models["A"]
        assert_that(assert_conforms({"f": a(x=1)}, models["holding"](a), exact=True).value.f.x).is_equal_to(1)
        assert_that(assert_conforms({"f": a(x=1)}, models["Wrapped"], exact=True).value.f).is_length(1)
        assert_that(assert_conforms({"f": a(x=1)}, models["WrappedSet"], exact=True).value.f).is_length(1)
        assert_that(assert_conforms({"f": [["k", a(x=1)]]}, models["Paired"], exact=True).value.f).contains_key("k")
        lazy = assert_conforms({"f": [a(x=1)]}, models["holding"](collections.abc.Iterable[a]), exact=True)
        assert_that(list(lazy.value.f)).is_length(1)

    def test_a_validator_reordering_at_equal_length_is_read_by_position(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, field_validator

        class A(BaseModel):
            x: int

        class B(BaseModel):
            y: int

        class Reversed(BaseModel):
            f: list[A | B]

            @field_validator("f", mode="before")
            @classmethod
            def backwards(cls, value):
                return list(reversed(value))

        found = self._refusal({"f": [{"x": 1}, {"y": 2}]}, Reversed)
        assert_that(found).is_equal_to(
            "it carries 2 undeclared field(s) the model does not declare: ['f[0].x', 'f[1].y']"
        )

    def test_a_nesting_deeper_than_the_walk_follows_is_refused(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, field_validator

        class A(BaseModel):
            x: int

        class Rewrapped(BaseModel):
            f: A | list[typing.Any]

            @field_validator("f", mode="before")
            @classmethod
            def rewrapped(cls, value):
                depth = 0
                while isinstance(value, list):
                    depth, value = depth + 1, value[0]
                for _ in range(depth):
                    value = [value]
                return value

        deep: object = 0
        for _ in range(5_000):
            deep = [deep]
        found = self._refusal({"f": deep}, Rewrapped)
        assert_that(found).is_equal_to("<the payload> cannot be checked: it nests deeper than the walk can follow")


class TestExactnessWalksOnlyWhatCanHoldAModel:
    """A field whose type is made of plain parts, and a part pydantic kept as the payload's own object, hold nothing
    built from the payload, so `exact=True` does not walk them: a 300 by 300 grid of floats walked item by item cost
    forty times its validation, and a deep list under `Any` overflowed the stack."""

    @staticmethod
    def _model():
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class A(BaseModel):
            x: int

        return A

    def test_which_types_can_hold_a_model(self):
        model = self._model()
        from pydantic import Json

        class Point(typing.NamedTuple):
            a: model

        class Shape(typing.TypedDict):
            a: model

        plain = {
            "a bare list": list,
            "a grid": list[list[float]],
            "a JSON object": dict[str, typing.Any],
            "a list of objects": list[object],
            "an iterable of ints": collections.abc.Iterable[int],
            "a tuple of ints": tuple[int, ...],
            "a literal": typing.Literal[1, "a"],
            "an annotated list": typing.Annotated[list[int], "meta"],
            "optional text": str | None,
            "an abstract mapping": collections.abc.Mapping[str, collections.abc.Sequence[bytes]],
        }
        holding = {
            "Any": typing.Any,
            "object": object,
            "optional Any": typing.Annotated[typing.Any | None, "meta"],
            "a model": model,
            "an optional model": model | None,
            "a model read from JSON": Json[model],
            "a model deep inside": dict[str, list[tuple[int, model]]],
            "a named tuple": Point,
            "a typed dict": Shape,
            "a type variable": typing.TypeVar("T"),
            "an unresolved name": "A",
        }
        verdicts = {name: _contract._may_hold_model(annotation) for name, annotation in {**plain, **holding}.items()}
        assert_that(verdicts).is_equal_to({**dict.fromkeys(plain, False), **dict.fromkeys(holding, True)})

    def test_json_text_inside_json_text_is_read_to_the_end(self):
        twice = '"{\\"x\\": 1}"'
        assert_that(_contract._holds([twice], _contract._is_mapping, read_text=True)).is_true()

    def test_a_field_that_cannot_hold_a_model_is_not_walked(self, monkeypatch):
        a = self._model()
        from pydantic import BaseModel, RootModel

        class Grid(BaseModel):
            cells: list[list[float]]
            tags: list[str]
            sub: a

        walked = []
        walk = _contract._value_drift
        monkeypatch.setattr(_contract, "_value_drift", lambda *args: walked.append(args[2]) or walk(*args))
        assert_conforms({"cells": [[1.0, 2.0]], "tags": ["t"], "sub": {"x": 1}}, Grid, exact=True)
        assert_conforms([[1.0, 2.0]], RootModel[list[list[float]]], exact=True)
        assert_that(walked).is_equal_to(["sub"])

    def test_a_deep_part_kept_as_given_is_not_walked(self):
        a = self._model()
        deep: object = 0
        for _ in range(5_000):
            deep = [deep]
        loose = type("Loose", (a.__base__,), {"__annotations__": {"f": typing.Any}})
        either = type("Either", (a.__base__,), {"__annotations__": {"f": a | list[typing.Any]}})
        for model in (loose, either):
            assert_that(assert_conforms({"f": deep}, model, exact=True).value.f).is_length(1)

    def test_a_model_a_validator_put_under_any_is_walked(self):
        a = self._model()
        from pydantic import BaseModel, field_validator

        class Built(BaseModel):
            f: typing.Any

            @field_validator("f", mode="before")
            @classmethod
            def built(cls, value):
                return a.model_validate(value)

        assert_that(_drift({"f": {"x": 1, "extra": 2}}, Built)).is_equal_to(["f.extra"])


class TestAliasesOnDuckTypedModels:
    """pydantic mirrors `Field(alias=...)` into `validation_alias`, so on a pydantic model the two
    collectors always agree and neither can be tested apart from the other.  Duck-typed models can
    carry one without the other, which is what the two `getattr` defaults exist for."""

    @staticmethod
    def _model(**field_attrs):
        info = type("DuckField", (), {"annotation": int, **field_attrs})()
        return type("DuckModel", (), {"model_fields": {"id": info}})

    def test_a_serialization_alias_alone_is_declared(self):
        model = self._model(alias="ID", validation_alias=None)
        assert_that(_declared_keys(model)).is_equal_to({"id", "ID"})

    def test_a_validation_alias_alone_is_declared(self):
        model = self._model(alias=None, validation_alias="incoming")
        assert_that(_declared_keys(model)).is_equal_to({"id", "incoming"})

    def test_a_field_carrying_neither_attribute_is_accepted(self):
        assert_that(_declared_keys(self._model())).is_equal_to({"id"})


class TestDriftOnDuckTypedModels:
    """The module is duck-typed on ``model_fields`` and never imports pydantic, so a class exposing
    that attribute without pydantic's ``model_config`` is a supported input, not a broken one."""

    def test_a_model_without_model_config_reports_drift(self):
        class DuckField:
            alias = None
            validation_alias = None
            annotation = int

        class DuckModel:
            model_fields: typing.ClassVar = {"id": DuckField()}

        assert_that(contract_drift({"id": 1, "surprise": 2}, DuckModel())).is_equal_to(["surprise"])


class TestStructureWalkPathsAndCycles:
    """The walk builds a dotted path as it descends and refuses to follow a cycle.  Every mismatch
    below was reachable but unasserted, so the path could be built wrong, the cycle guard keyed on one
    side, or a `continue` turned into a `break`, without a test noticing."""

    def test_a_cycle_on_both_sides_is_marked_not_followed(self):
        value = {"a": 1}
        value["self"] = value
        spec = {"a": 1}
        spec["self"] = spec
        assert_that(_texts(StructureMatcher(spec).collect_mismatches(value))).is_equal_to(
            [("self", "<circular ref>", "<circular ref>")]
        )

    def test_a_missing_nested_key_carries_its_full_path(self):
        mismatches = StructureMatcher({"a": {"b": 1}}).collect_mismatches({"a": {}})
        assert_that([path.text for path, _, _ in mismatches]).is_equal_to(["a.b"])

    def test_every_missing_key_is_reported_not_just_the_first(self):
        # the loop continues past a missing key; breaking instead would report one and hide the rest
        mismatches = StructureMatcher({"a": 1, "b": 2}).collect_mismatches({})
        assert_that([path.text for path, _, _ in mismatches]).is_equal_to(["a", "b"])

    def test_a_non_dict_where_a_dict_was_specified_reports_the_value(self):
        assert_that(_texts(StructureMatcher({"a": {"b": 1}}).collect_mismatches({"a": 5}))).is_equal_to(
            [("a", 5, "a mapping")]
        )

    def test_a_matcher_whose_probe_raises_counts_as_a_mismatch(self):
        class Boom:
            def __eq__(self, other):
                raise TypeError("boom")

            __hash__ = object.__hash__

        boom = Boom()
        mismatches = StructureMatcher({"a": match.greater_than(1)}).collect_mismatches({"a": boom})
        assert_that([(path.text, expected) for path, _, expected in mismatches]).is_equal_to(
            [("a", "a value greater than <1>")]
        )
        assert_that(mismatches[0][1]).is_same_as(boom)

    def test_a_cycle_needs_both_sides_to_repeat(self):
        # keyed on the pair: on one side alone, a spec revisiting a value under a different sub-spec stops looking
        inner = {"n": 1}
        value = {"a": inner, "b": inner}
        mismatches = StructureMatcher({"a": {"n": 1}, "b": {"n": 2}}).collect_mismatches(value)
        assert_that([path.text for path, _, _ in mismatches]).is_equal_to(["b.n"])

    def test_a_value_revisited_against_a_different_sub_spec_is_still_compared(self):
        # keyed on the pair. On the value alone, a cyclic payload against a finite spec reports a false
        # circular reference the second time a sub-value comes up, and the real mismatch is never reached.
        inner = {"n": 1}
        inner["a"] = inner
        mismatches = StructureMatcher({"a": {"a": {"n": 2}}}).collect_mismatches({"a": inner})
        assert_that(_texts(mismatches)).is_equal_to([("a.a.n", 1, "<2>")])

    def test_the_mismatch_detail_comes_from_the_matcher(self):
        # wording that differs from the generic "was <...>", or the two branches would render identically
        described = StructureMatcher({"a": match.is_even()}).describe_mismatch({"a": "x"})
        assert_that(described).is_equal_to(
            "at <a>: expected an even integer, but was <'x'> of type <str>, not an integer"
        )


class TestMatchesStructureAcceptsAnyMapping:
    """Every other dict assertion accepts a mapping that is not a `dict` subclass; this one refused
    them.  `MappingProxyType`, a `collections.abc.Mapping`, and 3.15's `frozendict` all landed on the
    same `isinstance(..., dict)` gate while `is_equal_to` and `contains_key` walked them happily."""

    class _Mapping(collections.abc.Mapping):
        def __init__(self, data):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
            return len(self._data)

    def test_a_mapping_proxy_is_matched(self):
        assert_that(types.MappingProxyType({"a": 1})).matches_structure({"a": match.is_positive()})

    def test_a_custom_mapping_is_matched(self):
        assert_that(self._Mapping({"a": 1})).matches_structure({"a": match.is_positive()})

    def test_a_nested_mapping_is_walked(self):
        value = types.MappingProxyType({"outer": self._Mapping({"inner": 1})})
        assert_that(value).matches_structure({"outer": {"inner": match.is_positive()}})

    def test_a_mismatch_inside_a_mapping_keeps_its_path(self):
        value = types.MappingProxyType({"outer": self._Mapping({"inner": -1})})
        mismatches = StructureMatcher({"outer": {"inner": match.is_positive()}}).collect_mismatches(value)
        assert_that([path.text for path, _, _ in mismatches]).is_equal_to(["outer.inner"])

    def test_a_non_mapping_is_still_refused(self):
        with pytest.raises(TypeError, match="mapping, a pydantic-style model, or an attrs instance"):
            assert_that([1, 2]).matches_structure({"a": 1})

    def test_the_matcher_form_declines_a_non_mapping(self):
        assert_that(match.structure({"a": 1}).matches(5)).is_false()
