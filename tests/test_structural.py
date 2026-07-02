import pytest

from assertpy2 import AssertionFailure, assert_that, match
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
