import typing

import pytest

from assertpy2 import AssertionFailure, assert_conforms, assert_that, match, soft_assertions
from assertpy2._engine._contract import _submodel, contract_drift, shape, shape_diff
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
        assert_that(result).contains("was not a dict")

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
        # the same spec and value instances reused under sibling keys form a DAG, not a cycle;
        # matches() must scope its visited-set per path, like collect_mismatches does
        frag_spec = {"n": match.is_positive()}
        spec = {"a": frag_spec, "b": frag_spec}
        frag_val = {"n": 5}
        value = {"a": frag_val, "b": frag_val}
        assert_that(match.structure(spec).matches(value)).is_true()
        assert_that(value).satisfies(match.structure(spec))


class TestCollectMismatches:
    def test_collects_all_failing_fields(self):
        matcher = match.structure({"a": match.is_positive(), "b": match.is_positive(), "c": match.is_positive()})
        result = matcher.collect_mismatches({"a": -1, "b": 5, "c": -3})
        assert_that([entry[0] for entry in result]).is_equal_to(["a", "c"])

    def test_empty_when_all_match(self):
        matcher = match.structure({"a": match.is_positive(), "status": "active"})
        assert_that(matcher.collect_mismatches({"a": 5, "status": "active"})).is_empty()

    def test_nested_structure_matcher_joins_path(self):
        matcher = match.structure({"address": match.structure({"city": match.equal_to("NYC")})})
        result = matcher.collect_mismatches({"address": {"city": "LA"}})
        assert_that(result[0][0]).is_equal_to("address.city")

    def test_missing_key_recorded(self):
        matcher = match.structure({"name": match.is_non_empty_string()})
        path, actual, description = matcher.collect_mismatches({})[0]
        assert_that(path).is_equal_to("name")
        assert_that(repr(actual)).is_equal_to("<missing>")
        assert_that(description).is_equal_to("a non-empty string")

    def test_nested_structure_matcher_against_non_dict(self):
        matcher = match.structure({"user": match.structure({"name": match.is_non_empty_string()})})
        result = matcher.collect_mismatches({"user": "not a dict"})
        assert_that(result[0][0]).is_equal_to("user")

    def test_plain_nested_dict_against_non_dict(self):
        matcher = match.structure({"user": {"name": match.is_non_empty_string()}})
        path, _actual, description = matcher.collect_mismatches({"user": "not a dict"})[0]
        assert_that(path).is_equal_to("user")
        assert_that(description).is_equal_to("a dict")

    def test_plain_nested_dict_recurses(self):
        matcher = match.structure({"user": {"role": "admin"}})
        result = matcher.collect_mismatches({"user": {"role": "guest"}})
        assert_that(result[0][0]).is_equal_to("user.role")

    def test_raw_value_mismatch(self):
        matcher = match.structure({"status": "active"})
        path, actual, description = matcher.collect_mismatches({"status": "inactive"})[0]
        assert_that(path).is_equal_to("status")
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

    def test_nested(self):
        data = {"user": {"name": "Alice", "settings": {"theme": "dark"}}}
        assert_that(data).matches_structure(
            {"user": {"name": match.is_non_empty_string(), "settings": {"theme": "dark"}}}
        )

    def test_non_dict_val(self):
        with pytest.raises(TypeError, match="val must be a dict"):
            assert_that("not a dict").matches_structure({"a": 1})

    def test_non_dict_spec(self):
        with pytest.raises(TypeError, match="given arg must be a dict"):
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
        # mirrors BaseMatcher.__eq__ totality: a predicate that cannot evaluate is "no match"
        with pytest.raises(AssertionError, match="a value equal to"):
            assert_that({"a": _AmbiguousArray()}).matches_structure({"a": match.equal_to(_AmbiguousArray())})

    def test_matcher_that_cannot_evaluate_records_mismatch(self):
        # the non-array face of the same rule: `> 0` on a str raises TypeError -> mismatch, not a crash
        with pytest.raises(AssertionError, match="at <n>"):
            assert_that({"n": "not-a-number"}).matches_structure({"n": match.is_positive()})


class TestModelNestedInsideDict:
    """A model under a plain dict is normalized per level, so it matches specs and keeps leaf paths."""

    def test_model_under_nested_structure_matcher_keeps_leaf_path(self):
        value = {"address": _SpecModel(city="LA")}
        matcher = match.structure({"address": match.structure({"city": match.equal_to("NYC")})})
        result = matcher.collect_mismatches(value)
        assert_that(result[0][0]).is_equal_to("address.city")

    def test_model_under_plain_dict_spec_matches(self):
        value = {"address": _SpecModel(city="NYC")}
        assert_that(match.structure({"address": {"city": "NYC"}}).matches(value)).is_true()

    def test_model_under_plain_dict_spec_keeps_leaf_path(self):
        value = {"address": _SpecModel(city="LA")}
        result = match.structure({"address": {"city": "NYC"}}).collect_mismatches(value)
        assert_that(result[0][0]).is_equal_to("address.city")

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
            "total": 5,  # int for a float field: a JSON number, not drift
            "created": "2020-01-01T00:00:00",  # str for a datetime field: normal JSON, not drift
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
            either: int | str  # union of non-models: not recursed
            note: str

        return Inner, Outer

    def test_non_dict_payload_has_no_drift(self):
        _, outer = self._submodels()
        assert_that(contract_drift(42, outer)).is_empty()

    def test_alias_resolved_tuple_and_union_branches(self):
        _, outer = self._submodels()
        payload = {
            "innerAlias": {"x": 1, "deep": 2},  # sub-model via alias -> recurse
            "pair": [{"x": 1}, {"x": 2, "oops": 9}],  # tuple[Inner, ...] -> per-element recurse
            "either": "ok",  # union of non-models -> skipped
            "note": "n",
        }
        assert_that(sorted(contract_drift(payload, outer))).is_equal_to(["inner.deep", "pair[1].oops"])

    def test_null_submodel_value_is_skipped(self):
        _, outer = self._submodels()
        payload = {"innerAlias": None, "pair": [], "either": 1, "note": "n"}  # sub-model value None -> no recurse
        assert_that(contract_drift(payload, outer)).is_empty()

    def test_submodel_peels_optional_list_and_rejects_non_models(self):
        inner, _ = self._submodels()
        assert_that(_submodel(inner)).is_equal_to(inner)  # bare model
        assert_that(_submodel(inner | None)).is_equal_to(inner)  # optional union arm peeled
        assert_that(_submodel(list[inner])).is_equal_to(inner)  # list[Model] -> element
        assert_that(_submodel(int)).is_none()  # non-model type
        assert_that(_submodel(typing.Any)).is_none()  # non-type annotation
        assert_that(_submodel(int | str)).is_none()  # union of >1 non-None arm

    def test_validation_alias_str_not_flagged(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(validation_alias="userId")

        assert_that(contract_drift({"userId": 1}, Model)).is_empty()

    def test_alias_choices_not_flagged_but_genuine_drift_caught(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import AliasChoices, BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(validation_alias=AliasChoices("uid", "userId"))

        assert_that(contract_drift({"uid": 1}, Model)).is_empty()
        assert_that(contract_drift({"userId": 1}, Model)).is_empty()
        assert_that(contract_drift({"uid": 1, "surprise": 9}, Model)).is_equal_to(["surprise"])

    def test_alias_path_top_level_key_not_flagged(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import AliasPath, BaseModel, Field

        class Model(BaseModel):
            city: str = Field(validation_alias=AliasPath("address", "city"))

        assert_that(contract_drift({"address": {"city": "NYC"}}, Model)).is_empty()

    def test_submodel_resolved_via_validation_alias(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            inner: Inner = Field(validation_alias="innerAlias")

        assert_that(contract_drift({"innerAlias": {"x": 1, "extra": 2}}, Outer)).is_equal_to(["inner.extra"])

    def test_submodel_value_resolution_alias_loop_branches(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import AliasChoices, BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            plain: Inner  # absent from payload, no alias -> empty alias loop
            aliased: Inner = Field(validation_alias=AliasChoices("first", "second"))

        # `plain` missing (no alias to fall back to); `aliased` present under the SECOND choice
        assert_that(contract_drift({"second": {"x": 1, "deep": 9}}, Outer)).is_equal_to(["aliased.deep"])


class TestShape:
    def test_scalar_categories(self):
        assert_that(shape(None)).is_equal_to("null")
        assert_that(shape(True)).is_equal_to("bool")
        assert_that(shape(7)).is_equal_to("number")
        assert_that(shape(7.5)).is_equal_to("number")  # int and float share one category
        assert_that(shape("x")).is_equal_to("str")
        assert_that(shape(b"raw")).is_equal_to("bytes")  # fallback to type name

    def test_dict_and_empty_list(self):
        assert_that(shape({"id": 1, "name": "a"})).is_equal_to({"id": "number", "name": "str"})
        assert_that(shape([])).is_equal_to([])

    def test_list_merges_element_shapes(self):
        assert_that(shape([{"a": 1}, {"a": 2}])).is_equal_to([{"a": "number"}])  # equal element shapes
        assert_that(shape([{"a": 1}, {"b": 2}])).is_equal_to([{"a": "number", "b": "number"}])  # dict union
        assert_that(shape([None, 1])).is_equal_to(["number"])  # null yields to concrete (left)
        assert_that(shape([1, None])).is_equal_to(["number"])  # null yields to concrete (right)
        assert_that(shape([1, "x"])).is_equal_to(["mixed"])  # genuinely different scalars
        assert_that(shape([[], [1]])).is_equal_to([["number"]])  # nested list, empty element merged (left)
        assert_that(shape([[1], []])).is_equal_to([["number"]])  # nested list, empty element merged (right)
        assert_that(shape([[1], ["x"]])).is_equal_to([["mixed"]])  # two non-empty nested lists merged


class TestShapeDiff:
    def test_no_drift_and_null_wildcard(self):
        assert_that(shape_diff({"a": "number"}, {"a": "number"})).is_empty()
        assert_that(shape_diff("null", "str")).is_empty()  # nullable wildcard, either side
        assert_that(shape_diff("str", "null")).is_empty()

    def test_added_removed_nested(self):
        old = {"id": "number", "user": {"name": "str"}}
        new = {"id": "number", "user": {"name": "str", "vip": "bool"}, "extra": "str"}
        assert_that(sorted(shape_diff(old, new))).is_equal_to([("added", "extra", ""), ("added", "user.vip", "")])
        assert_that(shape_diff(new, old)).contains(("removed", "extra", ""), ("removed", "user.vip", ""))

    def test_list_elementwise_and_empty(self):
        assert_that(shape_diff([{"a": "number"}], [{"a": "number", "b": "str"}])).is_equal_to([("added", "[*].b", "")])
        assert_that(shape_diff([], ["str"])).is_empty()  # empty either side: element shape unknown
        assert_that(shape_diff(["str"], [])).is_empty()

    def test_retyped_names_objects_and_lists(self):
        assert_that(shape_diff("number", "str")).is_equal_to([("retyped", "", "number -> str")])
        assert_that(shape_diff({"a": "number"}, "str")).is_equal_to([("retyped", "", "object -> str")])
        assert_that(shape_diff("str", ["number"])).is_equal_to([("retyped", "", "str -> list")])
